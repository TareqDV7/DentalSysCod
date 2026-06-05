# DentaCare — Dental Management System

A self-contained dental clinic management platform with a Flask web portal and a Flutter mobile app. Designed for offline-first operation — the desktop server runs on a local machine and the mobile app syncs data over Wi-Fi, with Bluetooth (classic SPP) as a fallback when the network is unavailable. An optional **cloud node** runs the same code in multi-tenant mode, so each clinic's local server can mirror to (and remote devices can reach) a shared server when there's internet — while everything keeps working locally when there isn't.

---

## Architecture Overview

```
                          ┌──────────────────────────────────────┐
                          │  CLOUD NODE (optional)               │
   background sync,       │  same dental_clinic.py, CLOUD_MODE=1 │
   when internet is up    │  cloud_master.db + clinic_<id>.db ×N │
        ┌─────────────────┤  app.dentacare.tech (HTTPS via Caddy)│
        │                 └──────────────────────────────────────┘
        │                                ▲ remote mobile (HTTPS)
        ▼                                │
┌─────────────────────────────────┐      │     LAN / Bluetooth
│  dental_clinic.py  (LOCAL)      │◄─────┼──────────────────────┐
│  (Flask web server + SQLite DB) │      │                      │
│  Serves web portal on :5000     │      │          ┌───────────┴──────────┐
└─────────────────────────────────┘      │          │  clinic_mobile_app/   │
          ▲  Browser                      └──────────┤  (Flutter — Android)  │
     Clinic staff                                    │  Local SQLite + sync  │
     (desktop/tablet via browser)                    └───────────────────────┘
```

**Backend** — `dental_clinic.py`: the Flask app, REST API and SQLite schema (with its HTML/CSS/JS portals living in `templates.py`); auto-installs its own dependencies, initialises a SQLite database, and serves both a full web portal and a REST API on `http://0.0.0.0:5000`. The clinic's staff always use their **local** server (works offline); set `CLINIC_CLOUD_MODE=1` (Docker deployment) to run the same file as the shared **cloud node** instead — see [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md).

**Mobile** — `clinic_mobile_app/`: Flutter app that keeps its own local SQLite database, writes locally first, then pushes/pulls from the server. Works fully offline; syncs when connectivity returns. Each sync picks the best available link in order: **LAN local server → cloud node → Bluetooth**. The app reaches the cloud node directly via a clinic token (linked in one tap by scanning the desktop's pairing QR — Settings → Scan QR to link — or paired manually), so a phone stays in sync with the clinic's data even when it's off the clinic Wi-Fi. The patient detail screen carries the canonical follow-up sheet (date · procedure · tooth · price · discount · lab · payment · running balance — the same per-patient ledger as the desktop, recomputed locally so the doctor sees the new balance immediately after logging an entry, and reconciled against the server's recompute on the next sync), plus a Treatment Plans tab for multi-visit work, a Holidays card in Settings for clinic-wide non-working days, and a Procedure-catalog admin sheet (Settings → Procedure catalog) that mirrors the desktop's catalog management — the same list the follow-up sheet picks from to prefill price/lab. Bluetooth sync runs entirely in the main app isolate — the 30-second auto-fallback loop ticks while the app's Android activity is in the `resumed` lifecycle state, and pauses when the activity moves to `paused` / `detached`. Walking into BT range of the bonded clinic PC while offline (with the app open) triggers a silent auto-pair on first cycle, then sync, no taps. The mobile app intentionally skips the desktop's legacy `treatments` table — follow-ups supersede it.

---

## Quick Start

### Desktop server

**Customers:** Download `DentaCare-Setup.exe` from the releases page, double-click, follow the wizard. After install, DentaCare runs as a Windows service (`DentaCare` in `services.msc`) in the background; click the Start Menu icon to open the window. The service auto-starts on Windows boot, so mobile sync stays alive even when the window is closed.

**Developers (running from source):**

```bash
# Windows
py dental_clinic.py
.\start.bat

# Linux / macOS
python3 dental_clinic.py
```

Dependencies (`Flask`, `Flask-CORS`, `waitress`, plus `pywebview` + `pystray` + `Pillow` for the window app) are installed via `pip install -r requirements.txt`. Source mode opens the system default browser at `http://localhost:5000` with Werkzeug's auto-reloader active.

Set `CLINIC_HEADLESS=1` to skip the browser auto-open (useful when testing the window app: in a second terminal, `python dentacare_window.py` opens the pywebview window against the running service).

> **Windows note** — if double-clicking `dental_clinic.py` raises the OS dialog *"The application was unable to start correctly (0xc0000022)"*, that's Defender's **Controlled Folder Access** rejecting an interactive launch when the project lives under a protected folder (`%userprofile%\Desktop` is one by default). `start.bat` goes through `cmd → python.exe` instead of the `.py` shell association, which Defender lets through. The alternative is to whitelist Python in an **admin** PowerShell once: `Add-MpPreference -ControlledFolderAccessAllowedApplications '<path-to-python.exe>'`. This gotcha doesn't affect customers using the installer — the installer drops files into `Program Files\DentaCare\`, which CFA implicitly trusts.

**First login:** the web portal requires a staff sign-in. On first run a default account is created — username `admin`, password `admin` — and the console prints a reminder to change it. Either set `CLINIC_ADMIN_PASSWORD` before the first run, or change the password afterwards from **Settings → Account → Change Password**.

### Mobile app

1. Connect the phone to the same local network as the server.
2. Open the app → enter server URL (e.g. `http://192.168.1.x:5000`), serial number, and clinic name.
3. The app calls `/api/license/activate`, stores the returned offline token, and is ready to use.

Build the APK:

```bash
cd clinic_mobile_app
flutter pub get
flutter build apk --release
```

The compiled APK is also available under `deployment/mobile/android/`.

### Run modes (dev vs. production)

The server picks a mode automatically: **debug** when run from source (`python dental_clinic.py`), **production** when run as the packaged `.exe`. Override with the `CLINIC_DEBUG` env var (`1` = debug, `0` = production).

- **Debug** — Flask's built-in server with the auto-reloader, so code/template edits show up immediately.
- **Production** — served by [`waitress`](https://docs.pylonsproject.org/projects/waitress/) (a real multi-threaded WSGI server) instead of the Werkzeug dev server, which holds up far better when several staff browsers and the mobile app hit it at once. `waitress` is installed automatically on first run; if it can't be installed the server still starts on the built-in dev server with a warning.

The SQLite database runs in **WAL mode** (set once in `init_database()`), so readers don't block on the single writer — this is what keeps concurrent web + mobile-sync access from hitting "database is locked".

### Backups

- **Automatic** — in production runs, a background thread writes a timestamped copy of every active SQLite database (via SQLite's online backup API, so it's a consistent snapshot taken without stopping the server) to a `backups/` folder, shortly after startup and then every 6 hours. The most recent 20 copies are kept; older ones are pruned.
  - **Local server** (single-tenant): one file per snapshot, written directly to `backups/dental_clinic_YYYYMMDD_HHMMSS.db`. Restore by stopping the server, copying a backup over `dental_clinic.db`, and restarting.
  - **Cloud node** (`CLINIC_CLOUD_MODE=1`): one snapshot per tenant per cycle, written to `backups/<label>/<label>_YYYYMMDD_HHMMSS.db` — `backups/master/` for `cloud_master.db` and `backups/clinic_<id>/` for each clinic DB. Retention is tracked per subfolder, so a 20-cap and 6h cadence give ~5 days of recovery per clinic. Restore by copying a backup over the matching `clinic_<id>.db` (or `cloud_master.db`) inside the `dentacare-data` volume and restarting the stack. One tenant's failure (e.g. a corrupt clinic file) is logged and skipped without aborting the others.
- **Manual** — the dashboard's **Download Backup** button (`GET /api/backup`, login required) downloads the current database on demand. (Local server only — the cloud node has no portal.)
- **Cloud node — offsite-friendly sidecar** — the in-app snapshots above land on the same `dentacare-data` volume as the live DBs, so the cloud `docker-compose.yml` also runs a separate **`backup` container** (`cloud/backup.py`, stdlib-only) that mounts the data volume **read-only** and writes to its own `dentacare-backups` volume. Each run snapshots every `*.db` (master + each `clinic_<id>.db`) via the same online-backup API into one timestamped folder (`<BACKUP_DIR>/2026-06-03T12-30-00Z/…`), optionally gzipped (`BACKUP_GZIP=1`), then prunes folders older than `BACKUP_RETENTION_DAYS` (default `14`) while always keeping at least `BACKUP_MIN_KEEP` (default `7`). It runs daily in `--loop` mode (`BACKUP_INTERVAL_HOURS`, default `24`); a single failing tenant is logged and skipped. Because it's a separate process on a separate volume, a mistake or volume problem on the live data path can't take the backups down with it — see [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md) "Backups & restore".
- Tune with env vars: `CLINIC_BACKUP_INTERVAL_HOURS` (default `6`; set `0` to disable the automatic loop), `CLINIC_BACKUP_RETENTION` (default `20`).

Other env vars: `CLINIC_HOST` (default `127.0.0.1`; set to `0.0.0.0` for LAN access), `CLINIC_PORT` (default `5000`), `CLINIC_ADMIN_PASSWORD` (first-run admin password), `CLINIC_DATA_DIR` (override where the DB / `uploads/` / `backups/` live — used by the Docker/cloud deployment), `CLINIC_CLOUD_MODE` (run as the cloud node — see below), `CLINIC_CLOUD_URL` + `CLINIC_CLOUD_TOKEN` (point a local server at the cloud node for background sync — usually set via the UI's pairing flow instead), `CLINIC_OFFLINE_TOKEN` (a signed `offline_token` the local server forwards when pairing to a cloud that enforces signed serials — falls back to the persisted `cloud_offline_token` setting), `CLINIC_CLOUD_SYNC_INTERVAL_MINUTES` (default `15`), `CLINIC_SERIAL_PUBLIC_KEY` (cloud node: base64 Ed25519 public key used to verify vendor-signed serials), `CLINIC_REQUIRE_SIGNED_SERIAL` (default `1`/on — require a valid signed serial; set `0` to accept unsigned), `CLINIC_ADMIN_API_TOKEN` (cloud node: shared secret gating `POST /api/license/admin/revoke`; unset = endpoint closed), `CLINIC_LOG_FORMAT` (default `text`; set to `json` to emit one JSON line per HTTP request to stdout — `{ts, method, path, status, latency_ms, clinic_id?}` — for ingestion by log shippers like Better Stack, Datadog, or CloudWatch).

### Cloud node (multi-tenant)

The same `dental_clinic.py`, run with `CLINIC_CLOUD_MODE=1`, becomes a shared **cloud node**: a master registry DB (`cloud_master.db`) tracks clinics, and each clinic gets its own SQLite file (`clinic_<id>.db`). Every `/api/*` request must carry a clinic token (`X-Clinic-Token` header or `?clinic_token=`); a `before_request` hook resolves it and points the per-request DB path at that clinic's file, so the existing handlers run unchanged but see only that tenant's data. The staff web portal isn't served here — clinics keep using their own local server, which mirrors to the cloud in the background when there's internet (see *Cloud sync* below).

- `POST /api/clinics/register` (`{serial_number, clinic_name, offline_token?}` → `{clinic_id, clinic_token, already_registered}`) provisions a clinic — idempotent per serial, no clinic token required. The endpoint is **rate-limited per source IP** (default 10/hour, env-tunable). The optional `offline_token` is an **Ed25519 vendor-signed serial** (issued by `serial_generator.py`); the cloud verifies its signature with `CLINIC_SERIAL_PUBLIC_KEY`. Signed serials are **mandatory by default** (`CLINIC_REQUIRE_SIGNED_SERIAL=1`); set it to `0` only if you deliberately want to accept unsigned serials. A failed registration is logged server-side but returns a **generic** error message — paths, SQL, and exception text never leak to the client. (A local server's pairing flow forwards its `offline_token` automatically — see *Cloud sync* below — so the signed-serial gate doesn't break the UI pairing path.)
- **Cloud license authority** — the cloud node is the cryptographic source of truth for serial validity, subscription/revocation, and per-serial device caps, exposed via `POST /api/license/validate` (verifies the Ed25519 signature, registers the serial on first use, enforces status + subscription expiry/renewal, and atomically claims a device slot up to the serial's `max_devices`) and an admin endpoint `POST /api/license/admin/revoke` (gated by `CLINIC_ADMIN_API_TOKEN` via the `X-Admin-Token` header) to revoke/suspend a serial or release a device slot. State lives in two `cloud_master.db` tables, `license_serials` and `license_device_slots`. The vendor signs serials with an Ed25519 **private seed** that never leaves the vendor machine; only the matching public key is set on the cloud.
- Deployment (Docker + Caddy for auto-HTTPS, on a DigitalOcean droplet at `app.dentacare.tech`): see [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md) and the [`cloud/`](cloud/) directory. Caddy must be configured to **append** `X-Forwarded-For` (its default) so the app's single-hop `ProxyFix` reads the real client IP.

### Cloud sync (local ⇄ cloud)

When a clinic's local server has a cloud URL + clinic token configured, a background worker thread (modelled on the backups thread — production runs only, not the cloud node) does one pull-then-push cycle against the cloud node every `CLINIC_CLOUD_SYNC_INTERVAL_MINUTES` (default 15): it pulls an incremental `/api/sync/export?since=…` delta from the cloud and applies it locally, then pushes its own delta to the cloud's `/api/sync/import`. Both directions use the same last-write-wins-by-`updated_at` merge (and tombstones) as device sync, with the clinic token in `X-Clinic-Token`. Sync state — `cloud_url`, `cloud_clinic_token`, `cloud_last_sync_at`, `cloud_last_sync_result`, `cloud_last_pull_at`, `cloud_last_push_at` — is kept in `app_settings`. A failed round (offline, etc.) is just recorded, never fatal; env vars `CLINIC_CLOUD_URL` / `CLINIC_CLOUD_TOKEN` override the stored values.

Staff manage it from **Settings → Cloud Sync**: enter the cloud URL + serial and **Pair with cloud** (calls `/api/clinics/register` on the cloud, stores the returned token, runs an immediate first sync), then **Sync now** / **Unpair**. The dashboard shows a small "☁️ Synced …" / "Cloud sync: off" / "⚠️ Cloud sync error" badge. When a signed `offline_token` is available (the pair-request body, the persisted `cloud_offline_token` setting, or the `CLINIC_OFFLINE_TOKEN` env), the pair call forwards it so registration still succeeds against a cloud running with `CLINIC_REQUIRE_SIGNED_SERIAL=1`.

**One-tap phone pairing (QR).** Once a clinic is paired, **Settings → Cloud Sync → Link a phone** reveals a QR (`GET /api/cloud/pairing-qr`, login-gated, SVG) encoding the compact payload `{"v":1,"u":<cloud_url>,"t":<clinic_token>}`. The mobile app's **Settings → Scan QR to link** scans it (`mobile_scanner` → pure `parsePairingPayload()` → `AppState.linkWithToken()`), persists `cloud_url` + `clinic_token`, and runs a first sync — **without** re-typing the URL/serial and **without** re-registering, since the desktop already registered the clinic. Manual pairing remains as a fallback. The token is rendered only into the login-gated QR (served `Cache-Control: no-store`) and is never returned by the public `/api/cloud/status`. API: `POST /api/cloud/pair` · `GET /api/cloud/status` · `GET /api/cloud/pairing-qr` · `POST /api/cloud/sync-now` · `POST /api/cloud/unpair` (local server only; the cloud node returns `400`/`404`).

### Sync model

The mobile app and the local↔cloud mirror reconcile with the server through two endpoints:

- `GET /api/sync/export` — returns the synced tables. Pass `?since=<ISO timestamp>` to get only rows changed after that point (an incremental delta); without it you get a full snapshot. The response also carries a `tombstones` list — `{table_name, row_id, deleted_at}` entries recording rows that were deleted.
- `POST /api/sync/import` — accepts the same shape (`tables` + `tombstones`). Rows are merged **last-write-wins by `updated_at`**; an incoming row that's older than the local copy is skipped. Tombstones propagate deletions the same way: a deletion only takes effect if it's newer than the local row's last update, and a stale row push won't resurrect something that was already deleted (the deletion is remembered in the `sync_tombstones` table).

Both endpoints require a paired-device token (`X-Device-Token` header or `device_token` query param). The mobile gets one via either:
- **Wi-Fi/LAN onboarding** — Settings → "Pair via Wi-Fi (6-digit code)": clinic PC's web portal generates a `POST /api/pairing/start` code, mobile enters it and calls `POST /api/pairing/complete`, server stores the issued token in `paired_devices`.
- **Bluetooth auto-pair** — first time the user taps "Sync now via Bluetooth" with no token, the mobile sends `op:bt_pair` over the already-OS-bonded BT-SPP channel; server issues + persists a fresh token and the mobile saves it. No code typing — the OS-level Bluetooth bond + the configured COM port are the trust gates. If the server's `paired_devices` is ever cleared, the next BT sync detects `unauthorized`, silently re-pairs, and retries.

### Bluetooth sync (offline fallback)

When the phone can reach neither the LAN nor the cloud node, it falls back to **classic Bluetooth (SPP)** with the desktop. Setup is two steps:

1. Pair phone ↔ PC once in Windows Bluetooth settings (normal "Add a Bluetooth device").
2. On the desktop, **Settings → Bluetooth sync** → flip the toggle.

That's it. There is **no Windows COM port to create**: the desktop registers its own RFCOMM service through the native Windows Bluetooth API (`AF_BTH` via `ctypes` against `ws2_32`) and publishes an SDP record under the standard Serial Port Profile UUID, so the phone's `BluetoothConnection.toAddress(mac)` finds it by service UUID. The Settings card itself is just the toggle plus a single plain-language error line that appears only when something's wrong — no listener pill, no paired-phones table, no connection log, no advanced dropdown. (`/api/bt/status` keeps all those fields populated server-side for troubleshooting; the UI just doesn't render them.) Earlier builds required a manual *Incoming COM port* step in Windows; this is no longer needed. The legacy `installer/provision_bt.ps1` script still ships under `{app}\installer\` as a rare-case fallback an admin can run by hand, but the installer no longer invokes it.

On the phone, **Settings → Bluetooth peer** → "Pick clinic PC" → choose the bonded desktop. From then on, whenever the phone is in range and Wi-Fi/cloud are unreachable, the app runs one `hello → sync_export → sync_import` round-trip every 30 s over a 4-byte length-prefixed JSON protocol — same `{tables, tombstones}` envelope as the HTTP `/api/sync/*` endpoints, reusing `_collect_sync_export` and `_apply_sync_import` on the server so there is no duplicated sync logic. Last-write-wins by `updated_at` is unchanged. The handshake is `{"op":"hello","device_token":…}`; the desktop verifies it against `paired_devices` and closes the socket on mismatch — **except** the very first time, when the phone has no token yet: then the mobile sends `{"op":"bt_pair","device_id":…,"device_name":…}` first, the server creates (or rotates) a `paired_devices` row and returns a fresh `device_token`, the mobile stores it, and subsequent cycles authenticate normally. The same self-pair runs again automatically if the stored token is later revoked or the server's DB is reset (mobile sees `unauthorized`, drops the token, re-pairs once, retries). Trust model: the BT RFCOMM service is gated by an OS-level Bluetooth bond plus the doctor explicitly enabling BT sync on the PC, so anyone who reaches this protocol already has physical-presence approval. The Settings → Bluetooth peer card also has a **Sync now via Bluetooth** button that forces one immediate cycle, useful for verifying the link or triggering the first-time pair.

Desktop side: a daemon thread parallel to `cloud_sync_worker()` re-reads its settings each cycle (`bt_sync_enabled` in `app_settings`), so toggling in the UI takes effect without restart. The thread runs in both production and debug (debug-mode guarded by `WERKZEUG_RUN_MAIN` so the reloader's parent process doesn't fight the child for the radio), skipped on the cloud node. Each cycle prefers the native AF_BTH listener (`_bt_open_native_listener` → `_bt_accept_and_serve` → `_bt_close_native_listener`); if `_bt_open_native_listener` raises `OSError` (older Windows SKU, no BT radio, API error), the loop **falls back automatically to the legacy pyserial COM-port path** so machines without working AF_BTH never regress. `bt_last_sync_at` is only stamped after a real frame is dispatched through `_bt_handle_request`; idle accept cycles return without writing the timestamp.

Phone side: the 30 s loop is driven by `Timer.periodic` inside `ConnectivitySyncService`, running in the main Dart isolate. `AppState` is a `WidgetsBindingObserver` and starts the loop when the Android activity is `resumed` (and BT is enabled with a bonded peer), then stops it on `paused` / `detached` — so the loop keeps ticking while the app is on screen or in the recent-apps cache and goes quiet when the activity is gone. The "Sync now via Bluetooth" button calls `ConnectivitySyncService.syncViaBluetooth` directly, which short-circuits the LAN/cloud reachability gate. Required Android 12+ runtime permissions (`BLUETOOTH_CONNECT`, `BLUETOOTH_SCAN`) are requested when the user flips *Enable Bluetooth sync* in Settings and re-checked each tick. **Errors speak plain language** — `lib/utils/bt_error_message.dart` exports a `BtFailure` enum plus `classifyBtError(Object) → BtFailure` and `btMessageFor(BtFailure, locale) → String`, so every BT entry point (`_pickBondedPeer`, `syncViaBluetoothNow`, `_btAutoTick`) surfaces a bilingual EN/AR sentence the doctor can act on ("Turn on Bluetooth to sync.", "Couldn't reach the clinic PC. Make sure it's on, nearby, and its Bluetooth is on.") instead of a raw `PlatformException`. Persisted error strings are stored as `bt-failure:<name>` / `peer-unreachable:<Type>` tokens so changing the app language re-renders the active banner immediately.

**Known limitation:** the 30 s auto-loop only runs while the app's activity is alive — swiping the app from recents or rebooting the phone stops sync until the doctor opens the app again. (Earlier releases used a `flutter_background_service` foreground notification to keep the loop alive when the activity was gone, but the foreground-service stack repeatedly crashed the app on Android 13/14 with an uncatchable `RemoteServiceException`; the stability tradeoff is intentional for the single-doctor clinic flow.)

---

## Branding & Configuration

### Backend

Static branding is defined in one place near the top of `dental_clinic.py`:

```python
CLINIC_CONFIG = {
    'SYSTEM_NAME':    'DentaCare',
    'CLINIC_NAME':    'Dental Management System',
    'DOCTOR_NAME':    'Dr. Wasfy Barzaq',
    'DOCTOR_NAME_AR': 'د. وصفي برزق',
    'CLINIC_TAGLINE': 'Patient Care & Practice Management',
}
```

These are injected as Jinja2 variables into the HTML template at startup. The doctor name can also be changed at runtime directly from the header UI — the new value is persisted to the `app_settings` table in the database and takes effect immediately without restarting.

### Mobile app

```dart
// clinic_mobile_app/lib/config/app_config.dart
class AppBranding {
  static const String systemName  = 'DentaCare';
  static const String clinicName  = 'Dental Management System';
  static const String doctorName  = 'Dr. Wasfy Barzaq';
  static const String tagline     = 'Patient Care & Practice Management';
  static const String appVersion  = '1.0.0';
}
```

---

## Features

### Patient Management
- Add, edit, and delete patients with full profile (name, DOB, phone, email, address, medical history)
- Date of birth picker with Day / Month / Year dropdowns
- Duplicate detection — warns on matching name or phone number before saving, without blocking
- Follow-up sheet per patient: treatment procedure, tooth number, price, **discount**, lab expense, **clinic profit** (= price − discount − lab expense), payment, **Amount to Pay** (the running ledger balance). The *Add Entry* date uses Day / Month / Year dropdowns; editing an entry closes the patient window and opens the edit window on its own (Save / Cancel return to the patient profile)
- The "Amount to Pay" column is the true running balance — `Σ (price − discount − payment)` walked in date order — recomputed on the server every time the sheet is read and rewritten after any add / edit / delete, so editing or removing an earlier entry (or adding one out of date order) keeps every later row correct. Deleting a follow-up also removes its auto-created lab expense.
- **Patient credit balance** — money the clinic is holding *for* the patient. It's the overpayment on the follow-up ledger (`Σ payment − Σ (price − discount)`, when positive) plus any manual credit adjustments. Shown on the patient profile, and a payment record's *Credit Used* field draws it down (the form shows how much is available, and the amount can't exceed it).
- **Amount fields keep your expression** — any money field (price / discount / lab / payment on the follow-up sheet, subtotal / discount / paid on a payment record) accepts an arithmetic expression like `20+20`; the number is used for all maths but the expression is stored and shown verbatim on the sheet and on the printed invoice (e.g. `20+20 = ₪ 40.00`).
- **Percentage discounts** — a discount field (follow-up Add/Edit, billing) also accepts a percentage, `%20` or `20%`. It resolves to that percent of the line's base — the follow-up **price**, or the billing **subtotal** — when you leave the field, and the `20%` notation is preserved on the sheet (hover for the ₪ amount) and the printed invoice (e.g. `20% = ₪ 20.00`), the same as arithmetic expressions. Percentages work in discount fields only; typing `%` in price / payment / lab / subtotal / paid is rejected (the field turns red).
- **Odontogram (tooth chart)** — an interactive FDI permanent-dentition chart (32 teeth, ISO two-digit numbering 11–48) on the patient profile. Each tooth carries one condition from an **editable catalog** (`tooth_conditions`, seeded with a Core 8 — healthy / decay / filled / crown / root canal / missing / implant / needs-extraction — managed like the procedure catalog, EN/AR, color-coded). Tap a tooth to set its condition, **+ Log treatment** (opens the follow-up Add form with the tooth pre-filled), or **+ Add to plan** (treatment plans are now **multi-tooth**). Two badges are **computed at read time from the ledger + plans, never stored**: a purple *has-plan* dot and an amber *unpaid-balance* dot (₪). Teeth recorded on legacy follow-ups (`tooth_no`) are **auto-adopted** onto the chart on read (valid FDI only; junk ignored). Available on both the web portal (inline SVG arch) and the Flutter app (CustomPaint arch); the three new tables (`tooth_conditions`, `patient_tooth_chart`, `treatment_plan_teeth`) ride the existing `SYNC_TABLES` machinery, so they sync (last-write-wins + tombstones) like everything else
- Medical image uploads (X-rays, photos)

### Appointments
- Schedule, confirm, cancel, and complete appointments
- Calendar view with week/month navigation
- Status dropdown (Scheduled / Confirmed / Cancelled / Completed) fully translated in EN and AR
- Convert appointment directly to a visit

### Financial
- **Expenses**: categorised clinic expenses with paid / postponed status; negative amounts rejected
- **Summary / weekly / range reports**: revenue (= follow-up payments collected), expenses (paid + postponed), profit (= revenue − expenses), clinic gross profit (= Σ price − discount − lab), lab expenses, patient count for any date range — all scoped to non-deleted follow-ups. Every report also shows a **current "Amounts Still Owed" table** — what each patient still owes (net billed = price − discount, paid, left, last visit, overdue days) — plus an *Unpaid by Patients* total
- **Receivables report**: amount still owed per patient, with discounts subtracted from what is owed
- **Patient statement / invoice**: built straight from the patient's follow-up sheet — one row per entry (date, procedure, price, **discount**, payment, running balance), with totals = subtotal, discount, total to pay (price − discount), paid, and what's left. The printable invoice (EN/AR) carries the same breakdown
- Billing / payment records with discount and balance due; payment method is a **Cash / Card / Transfer dropdown**. Paid status and balance are computed against the **settled** amount (paid + any credit applied), with total/balance clamped at 0 — so a credit-only partial reads *Partial* and an overpayment reads a 0 balance rather than going negative. Deleting a billing record **reverses any credit the invoice consumed** (returning it to the patient) before removing the row, and tombstones the deletion so it propagates on the next sync. Every patient picker (payments, statement, appointments) is a single **searchable dropdown** — one field that filters the list by name or phone as you type and slides the matches down (keyboard navigable), instead of a separate search box stacked above the select — so it stays usable with a large patient roster
- **Per-patient payment history** — picking (or searching) a patient in the Billing → Payment Record tab swaps the all-records table for that patient's *combined* payment history: every payment they've made, merged from both the follow-up sheet's per-entry `payment` column **and** the billing payment records (including records settled purely by patient credit, with the applied-credit amount surfaced), sorted oldest-first with a "Total Collected" footer. *Show all records* clears the filter. Backed by `GET /api/patients/<id>/payment-history`

> The dashboard's "Today's Revenue" and "Today's Visits" cards count *today's* follow-up payments and entries (visits are recorded on the follow-up sheet, not the legacy `visits` table). `Clinic profit = price − discount − lab expense`; lab expense is also auto-recorded as a postponed expense, so don't add the two together.

### Header & UI
- The web portal runs **full-window** — the top bar sits flush against the top of the browser window and the app fills the whole viewport, instead of floating as a centred rounded card. On wide monitors the header and sidebar span edge-to-edge while the working area stays in a centred ~1500px column, so it reads as premium rather than just stretched
- Modern glass-morphism header with gradient background, sheen overlay, and accent bottom line
- Doctor name badge is clickable — opens an inline popover to edit the EN and AR name live, saved to DB
- Theme toggle (light / dark mode) persisted to localStorage
- Language toggle (English / Arabic RTL) persisted to localStorage
- **Logout** link in the header; **Settings → Account** lets the signed-in user change their password
- Appointment status choices remain visible in both languages

### Access Control & Security
- The web portal (`/`), printable invoices (`/invoice/<id>`), and the database backup download (`/api/backup`) require a logged-in staff session — anonymous browsers are redirected to a sign-in page
- Credentials live in a `users` table; passwords are stored as salted hashes (`werkzeug.security`). A default `admin` / `admin` account is seeded on first run (override with `CLINIC_ADMIN_PASSWORD`; change it from the UI)
- Session secret is generated once and persisted in `app_settings`, so logins survive restarts
- Invoice output is HTML-escaped: patient names, payment method/status, invoice numbers, treatment descriptions and the doctor name are escaped both in the server-rendered `/invoice/<id>` page and in the client-side "total invoice" print template, so a crafted patient name can't inject markup or script. The `?lang=` parameter on `/invoice/<id>` is normalised to `en`/`ar` rather than reflected verbatim
- Scope note: the data/sync REST API (`/api/patients`, `/api/appointments`, `/api/sync/*`, `/api/license/*`, …) is intentionally **not** behind the staff session so the offline-first mobile app keeps working unchanged. For a hardened deployment, keep the server bound to the LAN you trust (or behind a reverse proxy with auth), and treat that network as the security boundary for the API

### Internationalisation
- Full English and Arabic (RTL) support throughout the web portal
- Translation keys live in the `translations` JS object inside `templates.py` (the `HTML_TEMPLATE` web portal)
- The Flutter app exposes a language toggle in Settings (EN / ع) via `app_state.dart`

---

## Project Structure

> Build artifacts, the SQLite database, logs, the `backups/` folder, and one-off scratch scripts are kept out of version control via `.gitignore`.

```
clinic/
├── dental_clinic.py          # Backend: Flask app + REST API + SQLite schema
├── templates.py              # HTML/CSS/JS for the web portal, mobile-download page, and login
├── requirements.txt          # Flask, Flask-CORS, pyserial, waitress, qrcode
├── serial_generator.py       # CLI tool to generate and batch-export license serials
├── serial_admin.py           # Vendor-only loopback GUI (http://127.0.0.1:8787) for keypair generation + serial minting
├── pytest.ini                # pytest config
├── DentaCare.spec            # PyInstaller build spec (outputs dist/DentaCare.exe)
├── rebuild.bat               # One-click clean rebuild of the Windows executable
├── start.bat                 # Launcher: bypasses Windows Defender CFA on Explorer double-click
├── DEPLOY_CLOUD.md           # Cloud-node deployment runbook
├── LICENSE                   # Proprietary — all rights reserved
├── docs/                     # Long-form docs (user guide, deploy, security, serial generator, mobile setup)
│   ├── USER_GUIDE.md
│   ├── DEPLOY_INSTRUCTIONS.txt
│   ├── MOBILE_APP_SETUP.txt
│   ├── SECURITY_ARCHITECTURE.md
│   ├── SERIAL_GENERATOR_README.md       # Serial-generator user guide
│   ├── SERIAL_GENERATOR_QUICKREF.md     # Serial-generator cheat sheet
│   ├── LICENSE_INTEGRATION_GUIDE.md     # Backend license-token integration
│   └── superpowers/                     # Design specs + plans for major features
├── cloud/                    # Cloud-node deploy stack
│   ├── Dockerfile            #   the app image (CLINIC_CLOUD_MODE=1)
│   ├── docker-compose.yml    #   app + Caddy (auto-HTTPS) + backup sidecar
│   ├── Caddyfile             #   TLS / reverse proxy for app.dentacare.tech
│   ├── backup.py             #   tenant-DB backup sidecar (RO data mount → backups volume, rotation)
│   └── legal/                #   Privacy + TOS templates (starting point — fill placeholders + lawyer-review)
├── tests/                    # 400 tests across 46 suites
│   ├── test_api_fuzz.py             # Public API never returns 500 on malformed input
│   ├── test_appointment_api.py
│   ├── test_appointment_flow.py
│   ├── test_appointment_status.py   # Status-update accepts the full dropdown set
│   ├── test_backup.py               # Per-tenant cloud backups + flat single-tenant layout
│   ├── test_bt_codec.py             # 4-byte length-prefixed JSON frame codec
│   ├── test_bt_diagnostics.py       # /api/bt/status diagnostics (paired_devices, recent_attempts, server_listening)
│   ├── test_bt_endpoints.py         # /api/bt/status + /api/bt/configure
│   ├── test_bt_protocol.py          # hello / bt_pair / sync_export / sync_import dispatcher
│   ├── test_bt_session.py           # Frame in → dispatch → frame out, auth gating
│   ├── test_bt_socket_stream.py     # Socket → .read/.write/.flush adapter for the native RFCOMM listener
│   ├── test_bt_worker.py            # BT daemon thread: native-preferred + COM-port fallback, settings re-read
│   ├── test_catalog_migration.py    # Legacy treatment_catalog → treatment_procedures
│   ├── test_cloud_backup.py         # Cloud tenant-DB backup sidecar: retention edge cases + snapshot round-trip + run_once
│   ├── test_cloud_mode.py           # Cloud-mode routing, isolation, rate limit, HMAC gate + hardened register errors
│   ├── test_cloud_pairing_qr.py     # /api/cloud/pairing-qr endpoint (auth gate, unpaired 400, SVG payload)
│   ├── test_cloud_sync_worker.py    # Local ⇄ cloud background sync round-trip
│   ├── test_license_activation_a2.py # Local-server activation hardening: signature gate, token-sourced fields, grace-bypass fix, cloud-authoritative + offline fallback, LAN-attach device cap, login/status device-membership gates, server-fingerprint binding, no-500 fuzz
│   ├── test_license_authority.py    # Cloud license authority: /api/license/validate (signature, register-on-first-use, status/subscription/renewal, atomic device-cap, concurrency) + admin revoke/release + ProxyFix gating
│   ├── test_license_gate_a3.py      # First-run gate: unlicensed splash, view-only enforcement, write-block 403, grace pass-through, API exclusions
│   ├── test_license_gate_ui_a3.py   # First-run gate UI: DOMContentLoaded JS gate rendered in HTML for unlicensed + view-only; absent when licensed
│   ├── test_onboarding_b.py         # Premium onboarding B: baked cloud URL fallback, env override, pair flow, onboarding state API, license-cloud-url helper
│   ├── test_onboarding_ui_b.py      # Premium onboarding B UI: cloud-link panel present in HTML template + node --check syntax
│   ├── test_serial_admin_d.py       # Vendor serial-minting GUI: loopback guard, key status, generate with clobber guard, mint single/batch/clinic-level/CSV, no-500 fuzz
│   ├── test_serial_admin_ui_d.py   # Vendor serial-minting GUI UI: key-panel + mint-form present in HTML, node --check JS syntax
│   ├── test_serial_ed25519.py       # Ed25519 keypair + serial-token sign/verify, the dental_clinic verifier, load_private_seed, no demo-key fallback
│   ├── test_credit_balance.py       # Patient credit derivation + Credit Used
│   ├── test_date_utils.py
│   ├── test_expression_preservation.py  # "20+20" / "20%" verbatim on sheet/invoice
│   ├── test_followup_balance.py     # Recomputed Amount to Pay running balance
│   ├── test_health_check.py         # Service-mode health-check helper
│   ├── test_healthz.py              # /healthz probe (status, mode, db_writable, uptime)
│   ├── test_medical_images.py       # Medical-image upload + byte download + sync reconcile
│   ├── test_payment_history.py      # Per-patient combined payment history (follow-up + billing)
│   ├── test_resolve_data_dir.py     # Data-dir resolution (source vs. frozen/service)
│   ├── test_service_mode.py         # Packaged-service mode detection
│   ├── test_sync_resilience.py      # Bad row doesn't kill batch; mobile fixes verified
│   ├── test_sync_tombstones.py      # Sync delta / tombstone propagation
│   ├── test_tooth_conditions.py      # Editable tooth-condition catalog (Core-8 seed, CRUD, soft-delete)
│   ├── test_tooth_chart_api.py       # Tooth-chart upsert / clear / FDI validation / per-patient scoping
│   ├── test_tooth_chart_badges.py    # Computed has_plan / unpaid_balance + legacy tooth_no auto-adopt
│   ├── test_tooth_chart_sync.py      # Odontogram tables export/import + tombstone propagation
│   ├── test_treatment_plan_teeth.py  # Multi-tooth treatment plans (treatment_plan_teeth link table)
│   └── test_window_state.py         # pywebview window-state persistence
├── tools/
│   ├── db_check.py           # Quick SQLite inspection helper
│   └── qa_financial_test.py  # Ad-hoc financial-logic runner against a live server
├── backups/                  # Auto-generated DB backups (git-ignored, created at runtime)
├── deployment/
│   ├── DentaCare.exe         # PyInstaller-packaged Windows executable
│   └── mobile/android/       # Pre-built Android APK
└── clinic_mobile_app/
    ├── pubspec.yaml
    └── lib/
        ├── main.dart
        ├── config/
        │   └── app_config.dart         # AppBranding constants
        ├── state/
        │   └── app_state.dart          # Provider: theme, locale, sync, DB references
        ├── models/                     # Appointment, Patient, Visit, BillingRecord, ToothCondition, ToothChartEntry, TreatmentPlan (now carries teeth[]), …
        ├── screens/
        │   ├── pairing_screen.dart     # Wi-Fi/LAN onboarding: server URL + 6-digit pair code → device token (reached from Settings → Pair via Wi-Fi)
        │   ├── scan_pairing_screen.dart # QR scan (mobile_scanner) → parsePairingPayload → link-by-token (Settings → Scan QR to link)
        │   ├── activation_screen.dart  # Offline-license flow: serial activation (legacy/manual entry)
        │   ├── home_screen.dart        # Shell: AppBar + NavigationBar + IndexedStack
        │   ├── dashboard_screen.dart   # Stats grid + recent appointments
        │   ├── patients_screen.dart
        │   ├── patient_detail_screen.dart
        │   ├── odontogram_view.dart    # Tooth-chart tab: CustomPaint FDI arch + tap sheet (set condition / log treatment / add to plan)
        │   ├── appointments_screen.dart
        │   ├── catalog_screen.dart     # Procedure catalog admin (CRUD + active/inactive toggle) — opens from Settings → Procedure catalog
        │   ├── tooth_conditions_screen.dart # Tooth-condition catalog admin (mirrors catalog_screen) — opens from Settings → Tooth conditions
        │   ├── financial_screen.dart
        │   ├── reports_screen.dart
        │   └── settings_screen.dart    # Server URL, sync, dark mode, language
        ├── services/
        │   ├── database_service.dart        # Local SQLite (sqflite)
        │   ├── local_storage_service.dart   # Secure storage (tokens, bonded peer, server URL)
        │   ├── api_client.dart              # Dio HTTP client
        │   ├── internet_sync_service.dart   # Pull /api/sync/export, push /api/sync/import
        │   ├── connectivity_sync_service.dart  # LAN → cloud → BT fallback driver, 30 s loop
        │   ├── cloud_sync_service.dart      # Pair (or QR link-by-token) phone to cloud node, push/pull deltas
        │   ├── bluetooth_sync_service.dart  # Classic BT-SPP fallback (Android), zero Windows COM-port setup — runs in the main isolate, driven by ConnectivitySyncService's 30 s timer
        │   ├── bt_session_client.dart       # hello / bt_pair / sync_export / sync_import session driver
        │   ├── license_service.dart
        │   ├── patient_service.dart
        │   ├── appointment_service.dart
        │   ├── billing_service.dart
        │   ├── catalog_service.dart         # Treatment-procedure catalog: list / add / update / soft-delete, syncs to /api/treatment-procedures
        │   ├── tooth_chart_service.dart     # Tooth-condition catalog + per-patient chart (pure parseToothChart + server-backed CRUD)
        │   └── report_service.dart
        ├── utils/
        │   ├── bt_error_message.dart        # Pure: BtFailure enum + classifyBtError + bilingual btMessageFor — plain-language BT errors
        │   └── pairing_payload.dart         # Pure: parsePairingPayload — decode the desktop pairing QR's {v,u,t}
        ├── widgets/
        │   ├── stat_card.dart      # Dashboard metric tile
        │   ├── clinic_card.dart    # Rounded surface card
        │   ├── section_header.dart
        │   ├── status_badge.dart
        │   ├── empty_state.dart
        │   ├── gradient_button.dart
        │   └── sync_status_bar.dart
        └── theme/
            └── clinic_brand.dart   # Material 3 color scheme + typography
```

---

## REST API Reference

All endpoints are served by `dental_clinic.py` on port `5000`. Endpoints marked **requires login** need a staff browser session (`/login`); everything else — including the whole data/sync/license surface used by the mobile app — is open on the network the server is bound to.

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web portal (full HTML SPA) — requires login |
| GET | `/api/stats` | Dashboard summary counts |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/login` | Sign-in page / submit credentials (form: `username`, `password`, `next`) |
| GET | `/logout` | Clear session, redirect to sign-in |
| GET | `/api/auth/me` | Current session status (`{authenticated, username}`) |
| POST | `/api/auth/change-password` | Change the signed-in user's password (`current_password`, `new_password`) |

### Patients

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/patients` | List all / create patient |
| GET | `/api/patients/check-duplicate` | Check for duplicate name or phone |
| PUT | `/api/patients/<id>` | Update patient |
| DELETE | `/api/patients/<id>` | Delete patient |
| GET | `/api/patients/<id>/full-profile` | Patient + visits + billing |
| GET / POST | `/api/patients/<id>/followups` | Follow-up notes (with discount) |
| DELETE / PUT | `/api/patients/<id>/followups/<fid>` | Manage follow-up |
| GET | `/api/patients/<id>/invoice-summary` | Billing summary for patient |
| GET | `/api/patients/<id>/payment-history` | Combined payment history — follow-up sheet payments + billing records, oldest-first |

### Appointments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/appointments` | List / create |
| GET | `/api/appointments/recent` | Last N appointments |
| PUT | `/api/appointments/<id>/status` | Update status |
| DELETE | `/api/appointments/<id>` | Delete |

### Visits & Treatments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/visits` | List / create visit |
| PUT | `/api/visits/<id>/status` | Update visit status |
| POST | `/api/visits/from-appointment/<id>` | Convert appointment to visit |
| GET / POST | `/api/treatments` | Treatments on a visit |
| DELETE | `/api/treatments/<id>` | Remove treatment |
| GET / POST | `/api/treatment-procedures` | Procedure catalog (list / create) |
| PUT | `/api/treatment-procedures/<id>` | Update procedure |
| GET / POST | `/api/treatment-plans` | Treatment plans — GET returns each plan's `teeth[]`; POST accepts a `teeth` array (multi-tooth, FDI-validated) |
| PUT / DELETE | `/api/treatment-plans/<id>` | Manage plan — PUT reconciles `teeth` when the key is present (deleting links is tombstoned); DELETE cascades + tombstones its tooth links |

### Odontogram (tooth chart)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/tooth-conditions` | Condition catalog — list active (`?all=1` includes inactive) / create. Duplicate name → `409`, blank → `400` |
| PUT / DELETE | `/api/tooth-conditions/<id>` | Update / soft-delete (deactivate, tombstoned) a condition |
| GET / POST | `/api/patients/<id>/tooth-chart` | GET returns `{conditions, teeth}` — each tooth carries `condition_id/condition_name/color/note/source` plus read-time-computed `has_plan` + `unpaid_balance` badges, with valid-FDI legacy `tooth_no` auto-adopted. POST upserts one tooth (FDI-validated; `condition_id: null` clears it to healthy + tombstones the row) |
| DELETE | `/api/patients/<id>/tooth-chart/<tooth_no>` | Clear a tooth (deletes the chart row + tombstones it) |

### Billing

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/billing` | List / create billing record |
| DELETE | `/api/billing/<id>` | Delete record (reverses any credit the invoice applied) |
| GET | `/invoice/<id>` | Printable HTML invoice (`?lang=en|ar`) — requires login |

### Financial

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/expenses` | Expenses list / create (amount > 0 enforced) |
| DELETE / PUT | `/api/expenses/<id>` | Manage expense |
| GET | `/api/reports/summary` | Revenue + expense summary |
| GET | `/api/reports/weekly` | Range breakdown (revenue, expenses, profit) |
| GET | `/api/reports/receivables` | Outstanding balances with discount applied |

### Administration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/clinic-settings` | Read / update doctor name (persisted to DB) |
| GET / POST | `/api/holidays` | Clinic holidays |
| DELETE | `/api/holidays/<id>` | Remove holiday |
| GET | `/api/audit-logs` | Activity audit trail |
| GET | `/api/backup` | Download SQLite database backup — requires login |
| GET / POST | `/api/medical-images` | Patient X-rays / images |
| GET / POST | `/api/support` | Support tickets |

### Sync & Pairing

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sync/export` | Data snapshot for a device — add `?since=<ISO ts>` for an incremental delta; response includes deletion `tombstones` |
| POST | `/api/sync/import` | Receive a delta (`tables` + `tombstones`) from a device; last-write-wins by `updated_at` |
| POST | `/api/pairing/start` | Begin device pairing flow |
| POST | `/api/pairing/complete` | Complete pairing, issue token |

### Bluetooth sync (local server only — see *Bluetooth sync* above)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bt/status` | Current BT-sync state (`enabled`, `com_port`, `last_sync_at`, `last_error`, `available_ports`, `recommended_port`, `paired_devices` [`device_id, device_name, paired_at, last_seen_at, is_active`, capped 20 newest-first], `recent_attempts` [last 10 of an in-memory deque, `{ts, op, device_id, device_name, outcome, detail}` — `op` ∈ `hello`/`bt_pair`/`sync_export`/`sync_import`, `outcome` ∈ `ok`/`unauthorized`/`error`/`rejected`], `server_listening` [bool — true while the daemon holds the COM port open]) — requires login |
| POST | `/api/bt/configure` | Persist `{enabled, com_port}` to `app_settings`; the daemon thread picks up the new settings on its next loop iteration — requires login |

### Cloud sync (local server only — see *Cloud sync* above)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cloud/pair` | Register this clinic with the cloud node — `{cloud_url, serial_number, offline_token?}` → stores the returned clinic token + runs an immediate first sync; forwards a signed `offline_token` when available |
| GET | `/api/cloud/status` | Pairing + last-sync state (`configured`, `cloud_url`, `clinic_id`, `last_sync_at`, `last_sync_result`, …) — never returns the clinic token |
| GET | `/api/cloud/pairing-qr` | SVG QR of `{"v":1,"u":cloud_url,"t":clinic_token}` for one-tap phone linking — **requires login**, `Cache-Control: no-store`; `400` when unpaired, `404` on the cloud node |
| POST | `/api/cloud/sync-now` | Run one pull-then-push cycle against the cloud node immediately |
| POST | `/api/cloud/unpair` | Forget the cloud URL + token (stops background sync) |

### Cloud node (only when `CLINIC_CLOUD_MODE=1`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/clinics/register` | Provision a clinic tenant — `{serial_number, clinic_name, offline_token?}` → `{clinic_id, clinic_token, already_registered}`; idempotent per serial. Verifies the Ed25519 `offline_token` when the signed-serial gate is on (default) |
| POST | `/api/license/validate` | License authority — `{serial_token, device_fingerprint, device_name?}` → `{valid, reason?, status, plan_name, expires_at, grace_until, remaining_slots}`. Verifies the signature, registers on first use, enforces status/subscription/renewal, and atomically claims a device slot. Business failures are HTTP 200 with `valid:false` (`reason` ∈ `malformed`/`bad_signature`/`revoked`/`suspended`/`expired`/`device_cap_reached`) |
| POST | `/api/license/admin/revoke` | Admin-only (`X-Admin-Token` = `CLINIC_ADMIN_API_TOKEN`) — `{serial, status}` to revoke/suspend/re-activate, or `{serial, device_fingerprint, release:true}` to free a device slot. Rate-limited; `401` when the token is unset or wrong |

> These three are the only cloud `/api/*` endpoints that don't need a clinic token (they self-authenticate via signature / admin token). Every other `/api/*` call must carry `X-Clinic-Token` (or `?clinic_token=`) and is routed to that clinic's database; `/api/medical-images*` returns `501` there; non-`/api/` paths return a short "use your local server" notice. See [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md).

### Licensing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/license/activate` | Activate serial, return offline token |
| POST | `/api/license/login` | Token-based login |
| POST | `/api/license/offline-verify` | Verify HMAC token offline |
| GET | `/api/license/status` | Current license info |
| GET | `/api/system/readiness` | Authenticated readiness summary (paired devices, active licenses) |
| GET | `/healthz` | Unauthenticated liveness/readiness probe (`status`, `mode`, `db_writable`, `last_backup_at`, `uptime_seconds`) — works on local and cloud, returns 503 if the DB is unreachable. Designed for external monitoring; payload kept under 500 bytes for aggressive polling. |

### Mobile Downloads

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/mobile-download` | Download page |
| GET | `/downloads/android` | Serve Android APK |
| GET | `/downloads/ios` | iOS instructions |
| GET / POST | `/api/mobile/download-links` | Manage download links |

---

## Licensing

There are **two** token systems, used at different points:

1. **Vendor serial token (Ed25519).** Generated by `serial_generator.py` (CLI) or `serial_admin.py` (GUI), signed with a vendor **private seed** that never leaves the vendor machine. The local app and cloud verify it with the matching public key (`CLINIC_SERIAL_PUBLIC_KEY` env var, or the baked constant `_BAKED_SERIAL_PUBLIC_KEY` in `dental_clinic.py`). Generate the keypair once:

   ```bash
   # GUI (recommended) — run on vendor machine, open http://127.0.0.1:8787
   python serial_admin.py

   # CLI alternative
   python serial_generator.py --genkey            # → backend_ed25519_key.json (git-ignored)
   #   copy the printed public key → paste into _BAKED_SERIAL_PUBLIC_KEY in dental_clinic.py
   #   and set CLINIC_SERIAL_PUBLIC_KEY=<that> on the cloud node
   ```

   **Activation flow:** vendor mints a serial in the GUI → gives the clinic owner one **Activation Code** (a long Ed25519-signed token that already carries the serial number, plan, device cap and expiry inside it). On first run, after the staff sign-in, the app presents a premium, theme-aware activation card: the owner pastes only the Activation Code — there is **no** separate serial field to retype, since the serial lives inside the code. The card decodes the token locally and shows a read-only confirmation (clinic · serial · plan · expiry) so the owner can verify it's the right key before pressing **Activate**; on success it transitions in place to an optional "enable cloud backup" step. The same card is reachable later from the **Renew** banner (grace period) or the view-only banner (inactive license). Signing is mandatory — there is **no** demo/default key. See [`docs/SERIAL_GENERATOR_README.md`](docs/SERIAL_GENERATOR_README.md).

2. **Local offline-activation token (HMAC-SHA256).** Issued by a clinic's **local** server (`/api/license/activate`) to a device and verified offline (`/api/license/offline-verify`) using a key the local server keeps in its own DB. This is what lets the mobile app work fully air-gapped once activated. (Hardening this path and deriving device fingerprints is a separate, later phase.)

> Generated `*.csv` / `*.json` outputs and `backend_ed25519_key.json` are git-ignored — they contain real signed tokens / the private seed and must never be committed.

## License

This project is licensed under a **proprietary "All Rights Reserved" license** — see [`LICENSE`](LICENSE) for the full notice. The source is on GitHub for backup and portfolio purposes; reuse, redistribution, or modification requires written permission from the copyright holder.

---

## Tests

```bash
cd clinic/
python3 -m pytest tests/ -v
```

**400 tests across 46 suites.** Covers the appointment API + flow, date utilities, the catalog migration, follow-up running balance, the per-patient combined payment history (follow-up sheet payments merged with billing records, ordering, totals, per-patient scoping, exclusion of zero-value and deleted entries), patient credit balance, expression preservation in money fields, appointment status updates, sync tombstones (delta export + deletion propagation), sync resilience (per-row error isolation, mobile-shaped payloads, billing `amount`), cloud-mode multi-tenant routing + tenant isolation + rate limit + Ed25519-signed serials, the local ⇄ cloud background sync round-trip, the per-tenant cloud backup loop (master + each `clinic_<id>.db`, per-label retention, isolation on per-tenant failure) plus the historic flat single-tenant layout, the Bluetooth-SPP fallback (4-byte length-prefixed frame codec, hello/bt_pair/sync_export/sync_import dispatcher reusing the HTTP helpers — including the zero-code first-time pair that issues a fresh device_token over the OS-bonded BT channel and rotates cleanly on re-pair, full session driver including malformed-frame handling, `/api/bt/status` + `/api/bt/configure` endpoints behind staff login, the `_BtSocketStream` adapter that lets the native RFCOMM listener reuse `_bt_serve_session` verbatim — `tests/test_bt_socket_stream.py`, and a daemon-thread worker that prefers the native AF_BTH path and falls back to the legacy pyserial COM-port path on `OSError` — `tests/test_bt_worker.py`), the BT diagnostics surfacing on `/api/bt/status` (paired_devices list, recent_attempts ring buffer bounded to maxlen=20, ok/unauthorized outcomes recorded by the dispatcher, server_listening flag round-trip — `tests/test_bt_diagnostics.py`), medical-image upload + byte download + sync reconciliation, the `/healthz` probe (200 with `status/mode/db_writable/uptime_seconds` on local, 503 when the DB is unreachable, open without a clinic token on the cloud node), the packaging/runtime plumbing (data-dir resolution for source vs. frozen/service builds, packaged-service-mode detection, the service health-check helper, and pywebview window-state persistence), and a property-fuzz suite that exercises every public endpoint (the odontogram routes included) with malformed JSON, wrong types, missing fields and oversized payloads — anything returning HTTP 5xx is a test failure. The odontogram backend contributes five suites: the editable tooth-condition catalog (Core-8 seed, CRUD, duplicate/blank rejection, soft-delete + tombstone), the tooth-chart upsert/clear with FDI validation and per-patient scoping, the read-time `has_plan`/`unpaid_balance` badge computation plus legacy `tooth_no` auto-adopt, multi-tooth treatment plans via the `treatment_plan_teeth` link table (create / diff / cascade-delete, all tombstoned), and the export/import + tombstone round-trip for the three new `SYNC_TABLES` entries. Two cloud suites round it out: the one-tap pairing-QR endpoint (`tests/test_cloud_pairing_qr.py` — login gate, `400` when unpaired, `404` on the cloud node, and a well-formed SVG payload carrying the `{v,u,t}` token), and the tenant-DB backup sidecar (`tests/test_cloud_backup.py` — 14 cases over retention edge cases, the online-backup snapshot round-trip, and a single `run_once`). The cloud license authority adds two suites: `tests/test_serial_ed25519.py` (Ed25519 keypair + serial-token sign/verify, the `dental_clinic` verifier, `load_private_seed`, and the guarantee that there is no demo-key fallback) and `tests/test_license_authority.py` (`/api/license/validate` — signature verify, register-on-first-use, status/subscription/renewal gates including revoked-ignores-a-newer-token, the atomic device-slot cap under 8-thread concurrency, the `X-Admin-Token`-gated revoke/release endpoint, and that ProxyFix is wrapped only in cloud mode). Two premium-onboarding suites complete the backend coverage: `tests/test_onboarding_b.py` (baked cloud-URL fallback, `CLINIC_LICENSE_CLOUD_URL` env override, pair flow using the baked URL when omitted, onboarding-state endpoint, and the `_license_cloud_url` helper) and `tests/test_onboarding_ui_b.py` (cloud-link panel elements present in the HTML template + `node --check` syntax pass).

The Flutter app has its own analyzer-clean test suite (97 tests) under `clinic_mobile_app/test/` — currently `bluetooth_frame_codec_test.dart`, `bt_session_client_test.dart` (includes BT auto-pair handshake), `bluetooth_sync_service_test.dart` (includes auto-pair + self-heal on revoked token), `bt_error_message_test.dart` (`BtFailure` enum → bilingual EN/AR plain-language text via `btMessageFor`, plus `classifyBtError` mapping of `TimeoutException` / `'connect failed'` / `'read failed'` exception shapes), `followup_balance_test.dart`, `amount_expr_test.dart` (safe "20+20" money-expression evaluator), `patient_statement_totals_test.dart` (statement/invoice totals parity, to-pay/left clamped ≥0), `medical_image_reconcile_test.dart` (pull-side server↔local image reconciliation), `tooth_models_test.dart` (`ToothCondition` / `ToothChartEntry` JSON round-trip + `TreatmentPlan.teeth`), `tooth_chart_parse_test.dart` (pure `parseToothChart` splitting conditions + per-tooth badge entries), `odontogram_view_test.dart` (the arch renders 32 tooth cells + the condition legend), `pairing_payload_test.dart` (pure `parsePairingPayload` — decodes the desktop QR's `{v,u,t}`, rejects malformed/unsupported-version/blank payloads), `cloud_link_with_token_test.dart` (`linkWithToken` validates inputs and returns account info to persist, with **no** `/api/clinics/register` HTTP call), `license_gate_service_test.dart` (5 tests — LicenseGateService blocks navigation when unlicensed, passes when licensed, and honours the grace-period flag), and the default widget test. Run with `cd clinic_mobile_app && flutter test`.

Mobile-desktop parity invariants (worth re-checking when touching either side): (1) the Receivables tab in the Financial screen and the desktop's `/api/reports/receivables` both source from the follow-up ledger — `max(Σ price − Σ discount − Σ payment, 0)` per patient — *not* from the `billing_records` table, which under-counts in clinics that record day-to-day collections inside follow-up rows. (2) The mobile follow-up entry sheet exposes the same catalog-prefill behaviour as the desktop: picking a procedure from the dropdown fills the procedure name + the default price/lab expense (only into empty fields, so a doctor's typed numbers aren't clobbered) and stores `procedure_id` alongside the free-text name. (3) The mobile appointments day-list tile is tappable — opens a status picker (scheduled / completed / postponed / pending) plus a delete action, wired to `AppointmentService.updateStatus` and `deleteAppointment`. (4) Currency on every price/total in the mobile UI is `₪` (NIS); accidental USD `$` glyphs are a regression.

Financial logic can also be exercised end-to-end against a running server with the ad-hoc runner under `tools/`:

```bash
python tools/qa_financial_test.py
```

Covers 10 blocks: summary math, weekly range math, Saturday edge case, receivables discount correctness, follow-up running balance, billing records, expenses, edge cases, monthly range, and cross-report consistency.

### Continuous integration

`.github/workflows/ci.yml` runs on every push to `main`/`develop` and on pull requests: it installs `requirements.txt`, syntax-checks `dental_clinic.py` (`py_compile`), and runs `pytest tests/` against Python 3.10, 3.11 and 3.12.

---

## Packaging (Windows installer)

```bash
# Build both binaries + stage the installer payload.
rebuild.bat

# Compile the Inno Setup installer (requires Inno Setup 6 installed).
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DentaCare.iss
# Output: installer\Output\DentaCare-Setup.exe
```

`rebuild.bat` produces:

- `dist\DentaCare.exe` — windowed launcher (pywebview wrapping the Flask UI in a native Windows window)
- `dist\DentaCareService.exe` — headless Flask service (run by NSSM as a Windows service)
- `dist\staging\` — installer payload (binaries + `nssm.exe` + `MicrosoftEdgeWebview2Setup.exe` + `provision_bt.ps1` + `DentaCare.PNG`)

The `DentaCare.spec` PyInstaller spec produces both `.exe`s in a single invocation. `hiddenimports` covers `waitress`, `markupsafe`, `werkzeug.security` (auth / production server), `serial` + `serial.tools.list_ports` (Bluetooth-SPP sync), plus `webview` + `pystray` + `PIL` + `clr_loader` (window app only).

The Inno Setup installer (`installer\DentaCare.iss`):

- Installs binaries to `C:\Program Files\DentaCare\`
- Creates the data folder at `C:\ProgramData\DentaCare\{uploads,backups,logs}\` with `LocalSystem` write access
- Detects and migrates a legacy portable `dental_clinic.db` if found on the user's Desktop, in Documents, or at `C:\DentaCare\` (default-Yes copy prompt; original left as a safety backup)
- Installs the WebView2 runtime via the bundled Evergreen Bootstrapper if it isn't already present
- Registers DentaCare as an auto-start Windows service via NSSM (`LocalSystem`, log rotation at 10 MB)
- Adds Start Menu shortcuts; optional Desktop shortcut; optional auto-launch of the window at logon
- Uninstaller preserves `C:\ProgramData\DentaCare\` by default (default-No prompt before deleting clinic data)

The dev workflow (`python dental_clinic.py` from source → browser at `localhost:5000` with auto-reloader) is untouched. `sys.frozen` detection in `dental_clinic.py:132-145` routes the packaged exe to `%ProgramData%\DentaCare\` while keeping source mode writing next to the script.

---

## Flutter Dependencies (key packages)

| Package | Purpose |
|---------|---------|
| `provider` | State management |
| `sqflite` | Local SQLite database |
| `dio` | HTTP client |
| `flutter_secure_storage` | Encrypted token storage |
| `connectivity_plus` | Network detection |
| `flutter_bluetooth_serial` | Classic BT-SPP sync fallback (Android) |
| `mobile_scanner` | Scan the desktop pairing QR (one-tap cloud link) |
| `fl_chart` | Financial charts |
| `table_calendar` | Appointment calendar view |
| `flutter_animate` | UI micro-animations |
| `google_fonts` | Typography |
| `intl` | Date/number formatting + i18n |
