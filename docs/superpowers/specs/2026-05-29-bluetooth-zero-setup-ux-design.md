# Zero-setup, plain-language Bluetooth sync — design

## Goal

Make Bluetooth sync feel like a consumer feature, not a developer tool:

1. **No Windows COM port.** The doctor never creates, picks, or even sees a COM port. Flipping the desktop toggle is the only action.
2. **Desktop UI is just the toggle.** No listener pill, no paired-phones table, no connection log, no advanced port dropdown. (A single plain-language line appears *only* when something actually fails — see [Open question](#open-question).)
3. **Mobile UI is just "choose your clinic PC" + the toggle + "Sync now".** No COM-port hints, no dev text.
4. **Errors auto-fix where possible, otherwise speak plain language.** No raw `PlatformException` strings ever reach the user.

Pairing the phone and PC once in their OS Bluetooth settings (normal "Add a Bluetooth device") **stays** — it is the trust gate, and it is not the COM-port step the doctor complained about.

## Why

The COM-port friction is a **Windows limitation, not a code defect.** The desktop listens for the phone through a Windows *Incoming SPP COM port* opened with pyserial (`_bt_open_port` → `serial.Serial(port)`, dental_clinic.py:11922-11932). Creating that port programmatically is unsupported on Windows 10/11 — our own installer script documents this and falls back to popping the Bluetooth dialog for a manual "Add → Incoming" click (`installer/provision_bt.ps1:41-53`, exit code 2 = "user action required"). So **as long as the PC listens through a COM port, the manual step cannot be removed.**

The fix is to have the PC listen a different way: register its own RFCOMM service through the modern Windows Bluetooth socket API, which needs no COM port and advertises itself over SDP so the phone finds it automatically.

The UI and error work is independent of the transport and worth doing regardless.

## Constraints (decided in brainstorming, 2026-05-29)

| | |
|---|---|
| PC listener | Native Windows RFCOMM **server socket** (`AF_BTH`), advertised via SDP. **Keep the existing COM-port listener as an automatic fallback** so nothing regresses on machines where the native path fails. |
| New dependencies | **None.** Native socket via Python `ctypes` against Winsock — must survive the frozen PyInstaller `.exe`. (PyBluez rejected: no maintained Windows wheels for 3.11/3.12, breaks the "single file auto-installs deps" model.) |
| Phone connection logic | **Unchanged.** Android already connects to the standard SPP UUID via SDP — advertise that UUID and `BluetoothConnection.toAddress(mac)` resolves it. |
| Desktop UI | Literally just the toggle; conditional one-line error only on failure. |
| Mobile UI | Toggle + "Choose your clinic PC" picker + "Sync now via Bluetooth". Nothing else. |
| Error precision | Phone-side states (own BT off, permission, not paired, no PC chosen): **precise**. PC-silent (connect failed): **one friendly catch-all** — classic BT cannot distinguish "PC BT off" vs "asleep" vs "app closed" vs "out of range". |
| Diagnostics | `recent_attempts` deque + `paired_devices` rows keep populating server-side and stay on `/api/bt/status`; just **removed from the UI**. Costs nothing, preserves troubleshooting. |
| Hardware testing | The end-to-end radio path is **not** unit-testable here. Same on-device smoke gate as before — the user verifies. |
| Out of scope | The "30 s loop only runs while the app is foreground" limitation (separate concern); iOS (BT-SPP is Android-only). |

## Architecture

### Desktop: native RFCOMM listener with COM-port fallback

All in `dental_clinic.py`, reusing the existing protocol/session/auth layer untouched.

**New: `_BtSocketStream`** — adapts an accepted socket to the interface `_bt_serve_session` already expects. That function only uses `decode_bt_frame(stream_in)` (a `.read(n)`-style reader) plus `stream_out.write(bytes)` / `stream_out.flush()` (dental_clinic.py:11843-11856). The adapter implements:
- `read(n)` → loop `sock.recv()` until `n` bytes accumulated or EOF (raise/return empty → `decode_bt_frame` sees EOF).
- `write(b)` → `sock.sendall(b)`; `flush()` → no-op.

**New: `_bt_rfcomm_serve(stop_event)`** — the native listener:
1. `WSAStartup`.
2. `socket(AF_BTH=32, SOCK_STREAM=1, BTHPROTO_RFCOMM=3)`.
3. `bind` to a `SOCKADDR_BTH` with `port = BT_PORT_ANY` (Windows assigns the RFCOMM channel).
4. `WSASetService(..., RNRSERVICE_REGISTER)` publishing a `WSAQUERYSET`/`CSADDR_INFO` whose service class is the **Serial Port** UUID `00001101-0000-1000-8000-00805F9B34FB`, bound to the assigned channel — this is the SDP record the phone searches for.
5. `listen()`, then loop: `accept()` (with a timeout so `stop_event` is honored between connections) → wrap in `_BtSocketStream` → `_bt_serve_session(stream, stream)` (verbatim) → close the accepted socket.

A real per-connection socket also **removes the dead-session hack**: the comment at dental_clinic.py:11866-11873 explains the COM port can't surface the peer's disconnect promptly; an accepted socket sees a clean EOF (`recv() == b''`), so the listener is immediately free for the next connection.

**Changed: `bt_sync_server(stop_event)`** (dental_clinic.py:11935) — strategy selection each cycle:
- Read `bt_sync_enabled` (unchanged). The `bt_sync_com_port` setting is no longer required for the native path.
- If enabled: attempt `_bt_rfcomm_serve`. On a clean start, set `_bt_server_listening = True` while accepting.
- If the native listener raises on startup (bind/register fails — older Windows, missing radio, API error): record the error and **fall back** to the current COM-port path (`_bt_open_port` on the auto-picked port via `_bt_pick_default_port`), exactly as today.
- Preserve: settings re-read each loop, `_bt_sleep`/`stop_event`, `_bt_server_listening` flag, `_bt_record_success`/`_bt_record_error`, and the WERKZEUG_RUN_MAIN debug guard.

**Installer:** `provision_bt.ps1` leaves the critical path. Since the native listener advertises its own SDP service, no Incoming COM port is provisioned. The script may be retained as a harmless no-op for the fallback case but is no longer invoked to gate setup, and `installer/DentaCare.iss` drops the "user action required" follow-up message box.

### Desktop UI: just the toggle

The `Settings → Bluetooth Sync` card (HTML/JS template in `dental_clinic.py`, anchored near the strings at dental_clinic.py:3998, 4074, 7260-7316) is reduced to:
- One **Bluetooth sync** toggle (on/off), bilingual EN/AR.
- **Removed:** the status pill, the **Listener** indicator, the **Paired phones (N)** table, the **Recent connection log** table, and the **Advanced — pick COM port** disclosure.
- A single plain-language error line, rendered **only** when `/api/bt/status` reports a `last_error` (e.g. "Bluetooth couldn't start — is this PC's Bluetooth turned on?"). Hidden otherwise.

`/api/bt/status` keeps returning all current fields (so nothing else breaks and diagnostics remain queryable); the front-end simply stops rendering the removed blocks. `/api/bt/configure` no longer needs `com_port` from the user — when enabling, the native path is used and the COM-port value is only consulted by the fallback.

### Mobile UI: just pick your PC

`Settings → Bluetooth peer` (`clinic_mobile_app/lib/screens/settings_screen.dart:342-411`):
- **Keep:** the **Enable Bluetooth sync** toggle, the **"Choose your clinic PC"** picker (`_pickBondedPeer`, currently "Pick clinic PC"), and the **"Sync now via Bluetooth"** button.
- **Remove:** `_BtErrorBanner`'s COM-port "tip" (settings_screen.dart:699-720) — it points at desktop internals that no longer exist. The banner itself stays but renders only the plain mapped message.

### Errors: auto-fix, then plain language

**New: `btErrorMessage(Object error) → BtUserMessage { String text; BtAction? action }`** (pure function, e.g. `clinic_mobile_app/lib/utils/bt_error_message.dart`), bilingual via the existing `app_strings` mechanism. Every BT entry point (`_btAutoTick`, `syncViaBluetoothNow`, `_pickBondedPeer`) routes failures through it. Mapping:

| Situation | Behavior |
|---|---|
| Phone Bluetooth off | Auto-prompt `FlutterBluetoothSerial.requestEnable()`; if still off → "Turn on Bluetooth to sync." |
| BT permission missing/revoked | Auto-request via `BluetoothPermissions.ensureGranted()`; if denied → "Allow Bluetooth permission in Android settings to sync." |
| No clinic PC chosen | "Choose your clinic PC first." + action routes to the picker. |
| PC not bonded | "Pair the clinic PC in your phone's Bluetooth settings first." |
| Token revoked / `unauthorized` | Silent re-pair + retry (already implemented in `BluetoothSyncService.runOneSyncCycle`, bluetooth_sync_service.dart:204-209). Surface nothing. |
| Connect failed / PC silent | "Couldn't reach the clinic PC. Make sure it's on, nearby, and its Bluetooth is on." |
| Any other exception | Same friendly catch-all as above; raw text → debug log only. |

This replaces today's leak of raw strings such as `'BT connect failed: $e'` and `'Could not access Bluetooth: $e'` (bluetooth_sync_service.dart:146-149, settings_screen.dart:649). The auto-fix paths partly exist already (`requestEnable` in the picker at settings_screen.dart:626-639, `ensureGranted` at :613) — the change is to run them at **every** entry point and centralize the messaging.

## Data flow (happy path, after change)

1. Doctor flips desktop **Bluetooth sync** on → `bt_sync_server` starts `_bt_rfcomm_serve`, binds, publishes the SPP SDP record, `accept()` loop running.
2. Doctor opens the phone, picks the bonded PC once.
3. Phone offline (no LAN/cloud) → `_btAutoTick` fires → `BluetoothConnection.toAddress(mac)` → Android SDP lookup finds the advertised SPP service → connects.
4. First time: `bt_pair` issues a `device_token` (unchanged). Then `hello → sync_export → sync_import` over the same `{tables, tombstones}` envelope (unchanged).
5. Any failure → `btErrorMessage` → auto-fix or one plain sentence.

## Testing

**Mobile (unit, no hardware):**
- `bt_error_message_test.dart` — each error class → expected `{text, action}`, EN + AR.
- Existing `bluetooth_frame_codec_test.dart`, `bt_session_client_test.dart`, `bluetooth_sync_service_test.dart` stay green (protocol + auto-pair + self-heal unchanged).

**Desktop (unit, no radio):**
- `_BtSocketStream` round-trips the 4-byte length-prefixed frame codec (feed a fake socket, assert `decode_bt_frame`/`encode_bt_frame` parity) — extend `tests/test_bt_codec.py` or a new `tests/test_bt_socket_stream.py`.
- `bt_sync_server` native→COM-port **fallback decision** via injected fakes (native serve raises → COM-port path invoked) — extend `tests/test_bt_worker.py`.
- The `WSASetService`/`accept()` radio path is **not** unit-tested.

**Hardware smoke (user, gates the change):** pair phone+PC, Wi-Fi off on the phone, enable the desktop toggle, pick the PC on the phone, tap **Sync now via Bluetooth** → confirm first cycle issues a token and a second cycle moves a real record both ways. This is the same gate that already blocks the `v1.0.0` tag.

## Risks & honest notes

- **ctypes Winsock is fiddly and untestable here.** Mitigated by the COM-port fallback: worst case the doctor is back to today's behavior, not broken.
- **"Why is the PC silent" can't be pinpointed** over classic BT — friendly catch-all by design, not laziness.
- **Still Android-only.** iOS has no BT-SPP; unaffected.
- **Foreground-only loop** (swipe-from-recents / reboot stops sync) is unchanged and out of scope here.

## Open question

The user asked for the desktop to be "literally just the toggle," but a toggle that fails silently contradicts the error goal. This design surfaces **one** plain error line on the desktop *only when `last_error` is set*, and shows nothing in the normal case. If the user wants the desktop to be truly silent (no error line ever, errors visible only on the phone), drop the conditional line — the rest of the design is unaffected.
