# Phase 4 — Bluetooth sync (desktop ↔ mobile) design

**Status:** approved 2026-05-14
**Scope:** add Bluetooth as an automatic fallback transport between the Flutter mobile app and the Windows desktop `dental_clinic.py` server, replacing the existing BLE stub. Smartwatch-style: pair once, then sync runs automatically whenever the phone is in range AND Wi-Fi/cloud are unreachable.

---

## 1. Architecture & data flow

```
┌─────────────────────────────────────────┐
│  DESKTOP (Windows, dental_clinic.py)    │
│                                          │
│  ┌────────────┐    ┌──────────────────┐ │
│  │ Flask app  │    │ BT-SPP server    │ │
│  │ (TCP 5000) │    │ thread (pyserial)│ │
│  └─────┬──────┘    └────────┬─────────┘ │
│        │      shared SQLite │           │
│        └──────────┬─────────┘           │
│                   ▼                      │
│              dental_clinic.db            │
└─────────────────────────────────────────┘
                    ▲
        BT-RFCOMM ──┤ length-prefixed JSON
                    │  framed messages
                    ▼
┌─────────────────────────────────────────┐
│  PHONE (Flutter / Android)              │
│                                          │
│  ┌─────────────────────────────────┐    │
│  │ ForegroundService                │    │
│  │  • watches BT adapter            │    │
│  │  • every 30 s when idle:         │    │
│  │     try connect to bonded MAC    │    │
│  │  • on connect → run sync         │    │
│  │  • on success → idle 30 s        │    │
│  └────────────┬────────────────────┘    │
│               │ flutter_bluetooth_serial │
│               ▼                          │
│       local SQLite (sqflite)             │
└─────────────────────────────────────────┘
```

**Key principle:** BT is a *second transport* for the existing sync — not a new sync model. The desktop BT server thread accepts framed JSON requests and dispatches to **the same Python helpers** `/api/sync/*` already uses (`_collect_sync_export`, `_apply_sync_import`). The phone speaks the same `{tables, tombstones}` envelope it already sends over HTTP.

**Position in the transport chooser:** still last priority. The phone's `ConnectivitySyncService` keeps the chain `LAN → cloud → BT`. The BT loop fires automatically every 30 s **only when LAN and cloud are both unreachable** — wasted work otherwise (LWW makes it safe but pointless).

---

## 2. Desktop side: BT server in `dental_clinic.py`

A new daemon thread, parallel to the existing `cloud_sync_worker()`. Production runs only (skipped when `CLOUD_MODE=1` or `debug_mode`).

```python
def bt_sync_server():
    while True:
        port = read_app_setting('bt_sync_com_port')   # e.g. "COM5"
        enabled = read_app_setting('bt_sync_enabled') == '1'
        if not enabled or not port:
            time.sleep(30); continue
        try:
            with serial.Serial(port, baudrate=115200, timeout=1.0) as ser:
                _bt_serve_session(ser)
        except serial.SerialException:
            time.sleep(15)
```

The thread re-reads its settings every loop iteration, so toggles in the UI take effect within ~30 s without restart.

**Settings UX (web portal, local server only — hidden on cloud node):**
- New **Settings → Bluetooth Sync** card.
  - Enable toggle (writes `app_settings.bt_sync_enabled`).
  - COM port dropdown populated by `serial.tools.list_ports.comports()` filtered to entries whose description contains "Bluetooth".
  - "Pair a phone" button — opens `ms-settings:bluetooth` on Windows so the user can bond the phone normally. After bonding, Windows auto-assigns an outgoing/incoming COM port that appears in the dropdown.
  - Status line: "Listening on COM5 · last sync 3 min ago" / "Not paired" / "COM5 busy".

**Endpoints:**
- `GET /api/bt/status` → `{enabled, com_port, last_sync_at, last_error, available_ports: [...]}`.
- `POST /api/bt/configure` → `{enabled, com_port}` (writes `app_settings`).
- Both require staff login (mirrors backup endpoints).

**Auth on the wire:** first framed message is `{"op":"hello","device_token":"..."}`. Desktop verifies the token against the existing `paired_devices` table (same table the LAN sync uses). Mismatch → `{"error":"unauthorized"}` and close.

**Concurrency:** one client at a time. pyserial blocking reads in a daemon thread. No locking required — SQLite is WAL-mode.

**Dependencies:**
- Add `pyserial>=3.5` to `requirements.txt`.
- Add `pyserial` (and `serial.tools.list_ports`) to `DentalClinicApp.spec` `hiddenimports`.

---

## 3. Phone side: BT client + auto-reconnect loop

Replace the `flutter_blue_plus` stub with `flutter_bluetooth_serial`. The auto-reconnect lives in an Android foreground service so it survives backgrounding.

```dart
while (_running) {
  if (_lanOrCloudJustSynced())  { await sleep(30s); continue; }
  if (await _bluetoothOff())    { await sleep(30s); continue; }
  try {
    final conn = await BluetoothConnection.toAddress(bondedMac).timeout(10s);
    await _syncSession(conn);    // hello → sync_export → sync_import → close
  } catch (_) { /* not in range / desktop not listening — fine, try again */ }
  await sleep(30s);
}
```

**Why 30 s and not always-connected:** a held-open BT-SPP socket costs ~5-10× standby battery vs. brief connect-sync-disconnect cycles. 30 s gives <1 min "feels-instant" after coming into range. Cadence is configurable in settings.

**Fallback gating:** before each tick, check if `_storage.getLocalUrl()` is reachable OR cloud is reachable. If either, skip the BT attempt for this tick.

**Foreground service plumbing:**
- Package: `flutter_background_service`.
- Persistent Android notification: "DentaCare · Bluetooth sync".
- `AndroidManifest.xml` permissions to add: `BLUETOOTH_CONNECT` (API 31+), `FOREGROUND_SERVICE`, `POST_NOTIFICATIONS` (API 33+).
- On first enable, prompt user to whitelist battery optimization.

**Settings UX on phone (new card under "Cloud Account"):**
- Enable toggle.
- "Pick clinic PC" button → opens bonded-device picker (`FlutterBluetoothSerial.instance.getBondedDevices()`). Selection saves MAC + label to secure storage as `bt_bonded_mac` / `bt_bonded_label`.
- Status line: "Connected · last sync 1 min ago" / "Not in range" / "Bluetooth off".

**Dependencies:**
- Replace `flutter_blue_plus` with `flutter_bluetooth_serial` in `pubspec.yaml`.
- Add `flutter_background_service`.
- Existing `flutter_secure_storage` reused for MAC persistence.

---

## 4. Pairing UX (one-time setup, both sides)

1. **Desktop side, once:** Staff opens **Settings → Bluetooth Sync** → enables → picks the COM port that Windows assigned to the phone.
2. **Windows pairing, once:** If Windows hasn't bonded the phone yet, the Settings card has a "Pair a phone" button that opens `ms-settings:bluetooth`. After bonding, Windows auto-assigns the COM port and the dropdown picks it up.
3. **Phone pairing, once:** Phone-side Settings has a "Pick clinic PC" button listing `bondedDevices()`. If the desktop isn't in the list, the user pairs it via Android Bluetooth menu first, then taps the desktop entry.
4. **From then on: nothing.** The phone's background loop reconnects whenever the desktop's BT is on and they're in range; the desktop's server thread accepts.

**Failure modes the UX makes clear:**
- Desktop: "COM5 not available" → "Re-pair the phone in Windows Bluetooth settings."
- Phone: "Clinic PC out of range" → silent (Wi-Fi works); visible badge when user opens the app.

---

## 5. Wire protocol

**Framing:** 4-byte big-endian unsigned length + UTF-8 JSON payload. Per-frame cap **4 MB** (guardrail; deltas are usually a few KB).

```
┌────────────────┬──────────────────────────┐
│ 4-byte length  │ JSON payload (UTF-8)     │
└────────────────┴──────────────────────────┘
```

**Three ops; every response is `{"ok":true,...}` or `{"error":"..."}`:**

```jsonc
// 1. hello — always first; auth
→ {"op":"hello","device_token":"...","client_version":"1.0.0"}
← {"ok":true,"server_version":"1.0.0"}
← {"error":"unauthorized"}             // closes connection

// 2. sync_export — phone pulls server delta
→ {"op":"sync_export","since":"2026-05-14T12:00:00"|null}
← {"ok":true,"tables":{...},"tombstones":[...],"generated_at":"2026-05-14T15:23:00"}

// 3. sync_import — phone pushes its delta
→ {"op":"sync_import","tables":{...},"tombstones":[...]}
← {"ok":true,"applied":42,"skipped":3}
```

**Session lifecycle:** connect → `hello` → `sync_export` → apply locally → `sync_import` → disconnect. One round-trip, no keep-alive. Mirrors the HTTP sync flow exactly.

**Reuses existing helpers (zero duplicated logic):**
- Desktop `sync_export` dispatch → `_collect_sync_export(since)` (same function `/api/sync/export` uses).
- Desktop `sync_import` dispatch → `_apply_sync_import(payload)` (same as `/api/sync/import`).
- Token auth → `paired_devices` table lookup, same as the HTTP path.

**Why these choices:**
- Length-prefix > newline-delimited because tombstone payloads can contain newlines.
- Single round-trip > multiplexed streams because BT-SPP is naturally request/response and our sync model already fits.
- Same envelope as `/api/sync/*` so the phone's `internet_sync_service.dart` can be lifted with only the transport swapped.

---

## 6. Error handling, retry, observability

**Connection failures (most common):**
- Phone: `BluetoothConnection.toAddress(...)` throws → caught, retry in 30 s. No notification spam. `bt_last_sync_at` updated only on success.
- Desktop: pyserial raises `SerialException` when port disappears or peer disconnects → caught, sleep 15 s, re-open. Settings re-read every retry.

**Bad frames / malformed JSON / version mismatch:**
- Receiver sends `{"error":"<reason>"}` and closes. Sender logs + retries next cycle.
- No partial application — `_apply_sync_import` already isolates per-row errors (commit `03f8313`), so a bad row never poisons the batch.

**Auth failure (`unauthorized`):**
- Phone surfaces a *visible* badge on the Settings BT card ("Clinic PC rejected this device — re-pair?") because this won't self-recover. All other errors stay silent.

**Visible state on both sides:**
- Desktop `app_settings`: `bt_sync_enabled`, `bt_sync_com_port`, `bt_last_sync_at`, `bt_last_error`.
- Phone local storage: same shape.
- Both flow into the existing `sync_status_bar.dart` widget — adds a "· Bluetooth" link label alongside the existing "· Local Wi-Fi" / "· Cloud".

**No retries beyond the 30 s loop.** Persistent failures fail *visibly* (badge); transient failures self-heal on next tick.

---

## 7. Testing strategy

**Desktop (`pytest`, no real BT hardware):**
- Unit-test frame codec (`encode_frame` / `decode_frame`) — round-trip, truncation, oversized payload rejection, malformed JSON.
- Unit-test dispatcher with an in-memory bidirectional pipe (`io.BytesIO` pairs) — exercise hello/export/import flows including auth failure, unknown op, and the bad-row-in-batch case.
- Integration-test against a `pyserial` loopback (or `serial.serial_for_url("loop://")`) so the server thread can accept on a virtual port — verifies threading + settings re-read.

**Flutter (`flutter test`, no real BT):**
- Mock `BluetoothConnection`. Verify `_syncSession` calls hello → export → import in order, handles error responses, doesn't apply when import fails, never blocks beyond timeout.
- Test fallback gating: when `_storage.getLocalUrl()` reachability or cloud reachability returns true, the BT loop tick is skipped.

**End-to-end (manual, on real hardware — no honest way to automate):**
- Pair phone↔desktop in Windows once.
- Wi-Fi off on phone, edit on phone → appears on desktop within ~60 s via BT.
- Edit on desktop → appears on phone within ~60 s.
- Walk phone out of range, edit, walk back → sync resumes.
- BT off on desktop → phone goes silent. Turn back on → resumes.

**Deliberately not tested:**
- Real BT radio behavior (multipath, interference, OS BT stack quirks) — covered by manual.
- Cross-desktop-OS — Windows only.

---

## 8. Files to change (summary)

**Backend (`dental_clinic.py`):**
- New `bt_sync_server()` daemon + `_bt_serve_session()` + `encode_frame` / `decode_frame` helpers.
- New `GET /api/bt/status` + `POST /api/bt/configure` endpoints.
- `requirements.txt`: add `pyserial>=3.5`.
- `DentalClinicApp.spec`: add `pyserial`, `serial.tools.list_ports` to `hiddenimports`.
- New web-portal Settings card (HTML/JS in the existing template).
- Translations: 10-15 new `data-en` / `data-ar` strings.

**Frontend (Flutter):**
- `pubspec.yaml`: remove `flutter_blue_plus`, add `flutter_bluetooth_serial`, add `flutter_background_service`.
- `services/bluetooth_sync_service.dart`: full rewrite (foreground-service-based loop, framed protocol client).
- `services/connectivity_sync_service.dart`: hook BT loop to fire when LAN/cloud unreachable; add "Bluetooth" label to `SyncLink`.
- `state/app_state.dart`: wire bonded MAC + enabled flag through.
- `screens/settings_screen.dart`: new BT card.
- `services/local_storage_service.dart`: `setBtBondedMac` / `getBtBondedMac` / etc.
- `android/app/src/main/AndroidManifest.xml`: add permissions, declare foreground service.

**Tests:**
- `tests/test_bt_protocol.py` (frame codec + dispatcher unit tests).
- `tests/test_bt_server_loop.py` (settings re-read, port unavailable, threading).
- `clinic_mobile_app/test/bluetooth_sync_service_test.dart` (mock connection, fallback gating).

**Docs:**
- README: add a "Bluetooth sync" subsection under the existing Sync model section.
- This spec doc.
