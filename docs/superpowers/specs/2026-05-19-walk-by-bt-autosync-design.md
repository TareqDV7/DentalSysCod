# Walk-by Bluetooth autosync — design

## Goal

When the doctor enters BT range of their paired clinic PC while offline, the phone should sync silently — no UI taps, no prompts. First time, the system pairs (auto-issued `device_token`); every time after that, it just syncs. The doctor never thinks about transports.

## Why

`ConnectivitySyncService._btAutoTimer` (lib/services/connectivity_sync_service.dart:164) is a `Timer.periodic(30s)` started by `startBluetoothAutoLoop()` and only lives while the app is foreground. Each tick (`_btAutoTick`, lines 174–193) skips itself when (a) no bonded MAC, (b) BT toggle off, (c) BT permissions revoked, (d) **LAN reachable**, or (e) **cloud reachable** — so it only actually fires when the phone is offline and a bonded peer exists. That is exactly the walk-by trigger condition.

The "walk by + sync" flow needs that ticker alive while the app is **backgrounded** — currently it dies the moment Android sleeps the app. Auto-pair on first connect already works (commit `0dfdbf7`); `BluetoothSyncService.runOneSyncCycle` is atomic (pair-then-sync, with self-heal on revoked token, covered by `bluetooth_sync_service_test.dart`). The only missing piece is **"keep `_btAutoTimer` ticking while the app is backgrounded."**

## Constraints (decided in brainstorming, 2026-05-19)

| | |
|---|---|
| App-state assumption | App is alive (foreground or backgrounded). Killed / swiped from recents on aggressive OEMs is **out of scope** — doctor opens app once per workday. |
| Cadence | 30 s background ticks — same as foreground. |
| Notification | Low-importance dismissible "Clinic sync active". |
| Boot auto-restart | Not in v1. |
| iOS | Not in v1 (BT-SPP is Android-only). |
| OEM battery savers | Stock-Android behavior only; OEM allowlist prompts deferred. |

## Architecture

### Isolate split

- **Sync isolate** (background, owned by `flutter_background_service`): hosts the new `BackgroundSyncService` wrapper + an instance of `ConnectivitySyncService` whose `_btAutoTimer` lives here + `BluetoothSyncService` + `LocalStorageService` + its own `DatabaseService` and `ApiClient` instances.
- **UI isolate** (foreground): keeps the widget tree, `Provider`/`AppState`, on-foreground LAN/cloud sync logic (unchanged), and a thin proxy that subscribes to events from the sync isolate. **The BT auto-loop no longer runs here** — that's the whole change.

LAN and cloud sync paths (initial-launch sync, manual sync, connectivity-change triggers) stay where they are. The scope of this design is **specifically the BT fallback Timer that handles walk-by**, not a rewrite of the rest of the sync layer.

### `BackgroundSyncService` (new, thin wrapper)

`lib/services/background_sync_service.dart`:

- `start()` — calls `FlutterBackgroundService.configure(...)` and `.startService()`. Idempotent (no-op if already running).
- `stop()` — stops the service (disables BT autosync feature entirely; users get the manual fallback only).
- `forceSync()` — emits `force_sync` event on the channel. Manual "Sync now" button uses this.
- `onSyncEvent` stream — exposes `sync_started` + `sync_finished` events for the UI to render the status card.

The service's `onStart` handler (runs in the sync isolate) instantiates `ConnectivitySyncService` and calls `startBluetoothAutoLoop()` — the same call `AppState` makes today, just from a different isolate. Each tick of `_btAutoTick`:

1. Runs the existing guards (bonded MAC, BT enabled, permissions, LAN reachable, cloud reachable) — unchanged.
2. If guards pass, emits `sync_started {via: "bt"}` on the channel.
3. Calls `syncViaBluetooth(mac)` (which runs `BluetoothSyncService.runOneSyncCycle`).
4. Saves `lastSyncAt` / `lastError` to `LocalStorageService`, emits `sync_finished {via, ok, lastSyncAt, error?}`.

`force_sync` event handler triggers one extra `_btAutoTick()` out-of-schedule. Manual "Sync now" button uses this path.

### UI surface

| Today | After |
|---|---|
| Settings → BT Sync card with primary "Sync now" button | Settings → BT Sync card with three states: **Off** / **Active · last sync N min ago** / **Syncing now…**. "Sync now" demoted to an inner "Advanced" row, still functional. |
| No background notification | Persistent low-importance "Clinic sync active" while the service runs. |
| `_btAutoTimer` lives in UI isolate, dies on background | `_btAutoTimer` lives in the sync isolate, survives backgrounding. UI isolate observes via events. |

User-facing wording stays "Sync" — confirmed there are no "Export" / "Import" strings in the current UI (verified via grep across `lib/`), so no terminology audit is needed.

### Boundary crossings (3, via `FlutterBackgroundService` event channels)

1. **Sync → UI**: `sync_started {via}` and `sync_finished {via, ok, lastSyncAt, error?}`. `AppState` listens, updates the card.
2. **UI → Sync (settings)**: enable toggle / peer / COM port writes go through `LocalStorageService`; UI fires `settings_changed` event. Sync isolate re-reads its config on the next tick (cheap, in-memory cached afterwards).
3. **UI → Sync (manual)**: "Sync now" → `force_sync` event → out-of-schedule cycle → `sync_finished` event back.

### DB concurrency

Sqflite WAL handles the two-isolate writer model. UI writes go through the existing `is_synced=0` + tombstone flow (already in place from Phase 0); sync isolate reads pending, pushes, marks synced. **No new correctness risk** — the race window is the same as today's single-isolate two-thread model.

## Files

**New:**
- `clinic_mobile_app/lib/services/background_sync_service.dart` — the wrapper. ~150 LOC.
- `clinic_mobile_app/test/background_sync_service_test.dart` — unit tests for the wrapper.

**Modified (surgical):**
- `clinic_mobile_app/lib/main.dart` — call `BackgroundSyncService.start()` after `AppState` init.
- `clinic_mobile_app/lib/state/app_state.dart` — subscribe to `sync_started` / `sync_finished` events; expose `lastSyncAt`, `lastSyncError`, `isSyncing` to UI.
- `clinic_mobile_app/lib/services/connectivity_sync_service.dart` — extract the Timer logic so the sync isolate can host it. Behavior identical; just moves who constructs the Timer.
- `clinic_mobile_app/lib/screens/settings_screen.dart` — BT Sync card collapses to the three-state UX. "Sync now" demoted to Advanced row.
- `clinic_mobile_app/android/app/src/main/AndroidManifest.xml` — declare `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_DATA_SYNC` permission + foreground service type.
- `clinic_mobile_app/pubspec.yaml` — `flutter_background_service` already declared; verify version is current (>= 5.x).

**Not touched:**
- Server (`dental_clinic.py`, `bt_sync_server` thread, `paired_devices` table, `op:bt_pair` handler) — protocol unchanged.
- `bt_session_client.dart`, `bluetooth_sync_service.dart` internals.
- All other sync services (LAN / cloud / internet sync) other than the Timer host change.

## Edge cases (handled, listing for completeness)

| Case | Behavior |
|---|---|
| BT off on phone | `BluetoothSyncService.runOneSyncCycle` returns early with `error: "bluetooth disabled"`. Tick records it; UI shows red banner. |
| No bonded peer configured | BT branch skips silently — no error spam. |
| Peer in range but PC asleep | SPP connect fails fast (~3–5 s), tick records error, retries in 30 s. |
| Stale `device_token` (server revoke / DB reset) | `runOneSyncCycle` self-heals — one re-pair attempt on `unauthorized`. Covered by existing test. |
| Two phones bonded to same PC | Each gets its own token via `paired_devices(device_id)` PK. No collision. |
| WiFi flapping | `_btAutoTick` re-evaluates LAN/cloud reachability each tick. If WiFi briefly comes back, the next tick skips BT; when it drops again, BT resumes. No flapping concern at 30 s cadence. |
| Background service killed by OEM saver | Out of scope for v1. Documented limitation in README. |
| App swiped from recents | Foreground notification protects on stock Android. On aggressive OEMs (Xiaomi / Huawei / Samsung), service may die — same out-of-scope note. |

## Testing

### Unit (new)

`background_sync_service_test.dart` (~4–6 cases):
- `start()` is idempotent — calling twice doesn't double-start.
- `forceSync()` emits the `force_sync` channel event.
- `onSyncEvent` stream forwards `sync_started` + `sync_finished` events.
- `settings_changed` event causes sync isolate to re-read settings on next tick (mocked `LocalStorageService`).

### Existing tests

Unchanged — protocol, codec, session driver, `ConnectivitySyncService`, all stay. Expected count: 27 → ~33 flutter tests; 157 pytest unchanged.

### Hardware smoke (extends the existing v1.0.0 gate)

1. **Backgrounded tick**: open app, send to recents, leave for 5 min. Observe server's `bt_last_sync_at` advancing on the same 30 s cadence as foreground. **PASS criterion**: at least 8 ticks land within 5 min.
2. **First-time walk-by**: kill app, fresh-install, OS-bond phone+PC, open app once (service starts), background it, turn WiFi + cellular off, sit next to PC. **PASS criterion**: within 60 s, server log shows `bt_pair` op followed by `sync_export` / `sync_import` ops. `paired_devices` table gains one row.
3. **Subsequent walk-by**: same setup but `device_token` already issued. **PASS criterion**: no `bt_pair` op, just `sync_export` / `sync_import`. Round-trip < 10 s.
4. **Settings change while backgrounded**: change BT peer in app UI, send to recents, observe next tick uses the new peer (verify via server's `paired_devices.device_id`).
5. **Foreground notification**: visible after `start()`, low-importance (no sound / vibrate), dismissible by swipe, reappears on next service start.
6. **Token revoke self-heal**: while backgrounded, delete the row from `paired_devices` on the server. Next tick: `unauthorized` → automatic re-pair → sync continues. Verify by tailing server log for the sequence `unauthorized → bt_pair → sync_export`.

## Out of scope (explicit deferrals)

- `BOOT_COMPLETED` auto-restart of the service after phone reboot. Doctor opens app once per workday — sufficient for v1.
- OEM-specific battery-saver allowlist prompts (Xiaomi / Huawei / Samsung). Document as known limitation in README.
- iOS — BT-SPP is Android-only; iOS would need a BLE redesign.
- Adaptive cadence (slow ticks when LAN works, fast when BT-only). Optimization for v1.1 if battery feedback warrants.
- Telemetry / battery accounting for the always-on tick.

## Verification of done

- `flutter analyze` clean.
- All existing pytest + flutter unit tests still pass.
- New `background_sync_service_test.dart` tests pass.
- Hardware smoke (6 scenarios above) passes on at least one Android 12+ device.
- README updated: (a) walk-by behavior described in the Mobile blurb, (b) parity-invariants list extended if a new invariant emerges from the UI changes, (c) Files section lists the new service.
