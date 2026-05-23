# Changelog

## 2026-05-24

- **Bluetooth sync diagnostics — fix opaque "bt pairing failed" error.** First-hardware test of the BT-SPP fallback (paired Android phone ↔ Windows clinic PC) surfaced two diagnostic gaps that made the failure impossible to triage: the phone showed a generic *"bt pairing failed"* snackbar no matter what actually broke, and the desktop Settings → Bluetooth Sync card showed nothing about which phones were paired, which had connected, or whether the daemon was even listening. Both sides now surface real information.
  - **Mobile (`bluetooth_sync_service.dart`)**: `_autoPair()` previously had `catch (_) { return null; }` which swallowed every underlying exception. Replaced with a typed `_AutoPairOutcome` return type that carries the real error message — `TimeoutException` becomes *"BT connect timed out (10 s) — is the clinic PC listening?"*, generic `Exception` becomes *"BT connect failed: <toString>"*, and a rejected handshake surfaces the server's error message. `runOneSyncCycle` propagates the outcome's message into the `BtSessionResult.failure`, which the existing snackbar + status line already render.
  - **Mobile (`settings_screen.dart`)**: the persistent red error banner under the Bluetooth peer card is now a `_BtErrorCard` with `SelectableText` (so the doctor can long-press → copy the message when asking for help), wraps multi-line errors instead of overflow-ellipsis, and appends a locale-aware hint ("Tip: on the clinic PC, open Settings → Bluetooth Sync, check the COM port pill is green") when the message looks like a connect failure.
  - **Desktop (`dental_clinic.py`)**: `/api/bt/status` now returns three new fields. `server_listening` (bool) is driven by a module-level flag the daemon flips True inside the `with ser:` block and False in `finally` — so the UI can tell the user the COM port is actually open. `paired_devices` returns the `paired_devices` table (newest-first, cap 20, excludes `device_token`). `recent_attempts` returns the last 10 entries of a new in-memory `collections.deque(maxlen=20)` populated by `_bt_record_attempt(...)` from every BT op (`hello`, `bt_pair`, `sync_export`, `sync_import`), with outcome ∈ `{ok, unauthorized, error, rejected}` and a short detail. In-memory only — lost on restart, that's intentional.
  - **Desktop (Settings → Bluetooth Sync card)**: under the status pill now lives a one-line "Listening on COMx ✓ / No listener" indicator + two collapsed `<details>` blocks — "Paired phones (N)" (name, first paired, last seen, active) and "Recent connection log" (time, device, op, outcome, detail). All bilingual EN/AR. Hooked into the same `/api/bt/status` fetch that already drives the pill — no extra round trip.
  - **Tests**: 6 new tests in `tests/test_bt_diagnostics.py` covering empty diagnostics, `paired_devices` round-trip (with token redaction), `recent_attempts` ordering + maxlen cap, and `server_listening` flag. Total **170 passing across 22 suites** (was 164/21). Flutter side: 27 tests still pass, `flutter analyze` clean.
- **Artifacts refreshed**: `deployment/DentaCare.exe` (17.68 MB, EXE `/healthz` → 200) and `deployment/mobile/android/clinic-mobile.apk` (53.82 MB, grew slightly from 53.75 because of the new error-handling code).

## 2026-05-23 (later)

- Refreshed `deployment/DentaCare.exe` and `deployment/mobile/android/clinic-mobile.apk` from current source so both shipped artifacts match `main` (EXE smoke-tested via `/healthz` → 200). APK shrunk to 53.75 MB (was 54 MB) after dropping the `flutter_background_service` dependency tree.
- **Repo layout cleanup.** Moved seven long-form docs out of the repo root into `docs/`: `USER_GUIDE.md`, `DEPLOY_INSTRUCTIONS.txt`, `MOBILE_APP_SETUP.txt`, `SECURITY_ARCHITECTURE.md`, `SERIAL_GENERATOR_README.md`, `SERIAL_GENERATOR_QUICKREF.md`, `LICENSE_INTEGRATION_GUIDE.md`. Root now keeps only the docs you actually want a contributor to see on landing (`README.md`, `CHANGELOG.md`, `LICENSE`, `DEPLOY_CLOUD.md`) plus source / config / launchers. Updated the cross-references inside `docs/SECURITY_ARCHITECTURE.md` (file-tree + Files & Checksums table). README file-tree updated. Tests still 164 passing.
- Removed stale untracked artifacts at the repo root: `SESSION_SUMMARY.md`, `cleanup.ps1`, `__pycache__/`, `.pytest_cache/`, and the PyInstaller `build/` / `dist/` intermediates — all regeneratable or one-off scratch, none of them tracked in git.

## 2026-05-23

- **Mobile Bluetooth sync — stability redesign.** Repeated crashes on Android 13/14 were rooted in the foreground-service stack (`flutter_background_service` + Android FGS rules): any failure in that chain killed the process with an uncatchable `RemoteServiceException` / `ForegroundServiceDidNotStartInTimeException` that no Dart `try/catch` could intercept. The fix removes the foreground-service path entirely: the 30 s BT auto-loop now runs in the main isolate and is bound to the Android activity lifecycle — it ticks while the app is on screen (or in the recent-apps cache) and pauses when the activity is `paused` / `detached`. Manual "Sync now via Bluetooth" and the BT auto-pair handshake are unchanged. **Lost capability**: silent walk-by sync when the app has been swiped from recents or the phone has rebooted — the doctor opens the app once when arriving at the clinic and sync resumes automatically. Removed dependency: `flutter_background_service` (with its platform packages). Removed permissions: `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, `POST_NOTIFICATIONS`.

## 2026-05-22

- Billing → Payment Record: picking or searching a patient now shows that patient's **combined payment history** — the billing payment records merged with the per-entry payments recorded on the follow-up sheet — sorted oldest-first with a *Total Collected* footer. Backed by a new endpoint `/api/patients/<id>/payment-history`.
- Web portal now fills the browser window: the top bar sits flush at the top and the app spans full width, with the working area held in a centered ~1500px column so it still reads as premium (previously a rounded card floating with a 22px gutter — the "window in a window" look).
- Project cleanup: removed regeneratable build artifacts (`build/`, `dist/`, Python caches) and stale duplicate deliverables (the old-name `DentalClinicApp.exe`/`.rar` and superseded `.rar` archives), plus a stray `-w` junk file. The May-11 `deployment/dental_clinic.db` was archived into `backups/` before removal.
- Fixed `rebuild.bat`, which had been broken: it built through the spec (which outputs `DentaCare.exe`) but then checked for and copied `DentalClinicApp.exe`, so it failed on every run. Renamed `DentalClinicApp.spec` → `DentaCare.spec` to match its output.
- Rebuilt `deployment/DentaCare.exe` from current source (PyInstaller 6.19.0 / Python 3.14.4); smoke-tested the packaged app — `/healthz` and `/login` both returned 200. Test suite: **164 tests across 21 suites, all passing**.

## 2026-05-12

- Patient statement / invoice now reflects the follow-up sheet exactly: one row per follow-up entry with date, procedure, price, **discount**, payment, and running balance; totals corrected to subtotal, discount, total to pay (= price − discount), paid, and left (the discount was previously ignored, so "Total to Pay" and "Left" were overstated). The printable EN/AR invoice carries the same breakdown.
- Dashboard cards changed to **Today's Revenue** and **Today's Visits** — they now count today's follow-up payments and entries (the legacy `visits` table is unused; visits are recorded on the follow-up sheet, which is why the old "Total Visits" card always showed 0).
- Reports (weekly / monthly / lab) now also show a current **Outstanding Balances** table and an *Unpaid by Patients* total — what each patient still owes — whenever a report is run.
- Billing / payment record: **Payment Method** is now a Cash / Card / Transfer dropdown instead of a free-text field.
- Reviewed the financial equations: clinic profit and the per-row balance subtract the discount; receivables and the invoice totals use `price − discount − payments`; the report `profit` stays `revenue (payments collected) − expenses (paid + postponed)`. Note: a follow-up's lab expense is both subtracted in its clinic profit *and* auto-recorded as a postponed expense, so those two figures shouldn't be summed.

## 2026-05-11

- Cloud tier added on top of the local server + mobile app: `sync_tombstones` + incremental `/api/sync/export?since=` (deletions now propagate); `CLINIC_CLOUD_MODE` runs `dental_clinic.py` multi-tenant as the cloud node (`app.dentacare.tech`, Docker + Caddy); `cloud_sync_worker()` mirrors a clinic's local server to/from the cloud in the background, managed from **Settings → Cloud Sync** (`/api/cloud/{pair,status,sync-now,unpair}`) with a dashboard status badge. See `DEPLOY_CLOUD.md`.
- Patient follow-up sheet: the *Add Entry* date is now a Day / Month / Year dropdown set (defaulting to today) instead of a free-text field; editing an entry closes the patient profile window and opens the edit window on its own (Save / Cancel return to the profile).
- Fixed the clinic-profit calculation in the follow-up sheet: clinic profit is now `price − discount − lab expense` (the discount given to the patient was previously ignored). Applied on add, edit, and in the summary/monthly report aggregates; the per-row "Profit" column is computed the same way.
- Test suite: 39 tests across six suites (added `test_sync_tombstones.py`, `test_cloud_mode.py`, `test_cloud_sync_worker.py`).

## 2026-05-04

- Normalized report date filters in `dental_clinic.py` so summary endpoints reject invalid dates and accept ISO or display-formatted input.
- Removed duplicated appointment row mapping by adding a shared serializer for appointment API responses.
- Hardened appointment status updates with validation and 404 handling when the record does not exist.
- Moved initial mobile sync off the app startup critical path in `clinic_mobile_app/lib/state/app_state.dart` so the UI becomes responsive sooner.
- Improved Dio error extraction in `clinic_mobile_app/lib/services/api_client.dart` to surface server errors and status codes more clearly.
- Updated `verify_reports.py` to cover invalid summary dates and invalid appointment status updates.
- Stabilized the Flutter widget smoke test so it verifies startup behavior without depending on live sync completion.