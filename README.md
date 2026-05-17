# DentaCare — Dental Management System

A self-contained dental clinic management platform with a Flask web portal and a Flutter mobile app. Designed for offline-first operation — the desktop server runs on a local machine and the mobile app syncs data over Wi-Fi, with Bluetooth as a fallback when the network is unavailable. An optional **cloud node** runs the same code in multi-tenant mode, so each clinic's local server can mirror to (and remote devices can reach) a shared server when there's internet — while everything keeps working locally when there isn't.

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

**Backend** — `dental_clinic.py`: single Python file, auto-installs its own dependencies, initialises a SQLite database, and serves both a full web portal and a REST API on `http://0.0.0.0:5000`. The clinic's staff always use their **local** server (works offline); set `CLINIC_CLOUD_MODE=1` (Docker deployment) to run the same file as the shared **cloud node** instead — see [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md).

**Mobile** — `clinic_mobile_app/`: Flutter app that keeps its own local SQLite database, writes locally first, then pushes/pulls from the server. Works fully offline; syncs when connectivity returns. Each sync picks the best available link in order: **LAN local server → cloud node → Bluetooth**. The app reaches the cloud node directly via a clinic token (paired from Settings → Cloud Account), so a phone stays in sync with the clinic's data even when it's off the clinic Wi-Fi.

---

## Quick Start

### Desktop server

```bash
# Windows
py dental_clinic.py

# Linux / macOS
python3 dental_clinic.py
```

Dependencies (`Flask`, `Flask-CORS`, `waitress`) are installed automatically on first run. The browser opens at `http://localhost:5000` automatically — which lands on the sign-in page.

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
- Tune with env vars: `CLINIC_BACKUP_INTERVAL_HOURS` (default `6`; set `0` to disable the automatic loop), `CLINIC_BACKUP_RETENTION` (default `20`).

Other env vars: `CLINIC_HOST` (default `127.0.0.1`; set to `0.0.0.0` for LAN access), `CLINIC_PORT` (default `5000`), `CLINIC_ADMIN_PASSWORD` (first-run admin password), `CLINIC_DATA_DIR` (override where the DB / `uploads/` / `backups/` live — used by the Docker/cloud deployment), `CLINIC_CLOUD_MODE` (run as the cloud node — see below), `CLINIC_CLOUD_URL` + `CLINIC_CLOUD_TOKEN` (point a local server at the cloud node for background sync — usually set via the UI's pairing flow instead), `CLINIC_CLOUD_SYNC_INTERVAL_MINUTES` (default `15`).

### Cloud node (multi-tenant)

The same `dental_clinic.py`, run with `CLINIC_CLOUD_MODE=1`, becomes a shared **cloud node**: a master registry DB (`cloud_master.db`) tracks clinics, and each clinic gets its own SQLite file (`clinic_<id>.db`). Every `/api/*` request must carry a clinic token (`X-Clinic-Token` header or `?clinic_token=`); a `before_request` hook resolves it and points the per-request DB path at that clinic's file, so the existing handlers run unchanged but see only that tenant's data. The staff web portal isn't served here — clinics keep using their own local server, which mirrors to the cloud in the background when there's internet (see *Cloud sync* below).

- `POST /api/clinics/register` (`{serial_number, clinic_name, offline_token?}` → `{clinic_id, clinic_token, already_registered}`) provisions a clinic — idempotent per serial, no clinic token required. The endpoint is **rate-limited per source IP** (default 10/hour, env-tunable). When `CLINIC_SERIAL_SIGNING_KEY` is configured, the optional `offline_token` (HMAC-signed by `serial_generator.py`) is verified when present; set `CLINIC_REQUIRE_SIGNED_SERIAL=1` to make it mandatory.
- Deployment (Docker + Caddy for auto-HTTPS, on a DigitalOcean droplet at `app.dentacare.tech`): see [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md) and the [`cloud/`](cloud/) directory.

### Cloud sync (local ⇄ cloud)

When a clinic's local server has a cloud URL + clinic token configured, a background worker thread (modelled on the backups thread — production runs only, not the cloud node) does one pull-then-push cycle against the cloud node every `CLINIC_CLOUD_SYNC_INTERVAL_MINUTES` (default 15): it pulls an incremental `/api/sync/export?since=…` delta from the cloud and applies it locally, then pushes its own delta to the cloud's `/api/sync/import`. Both directions use the same last-write-wins-by-`updated_at` merge (and tombstones) as device sync, with the clinic token in `X-Clinic-Token`. Sync state — `cloud_url`, `cloud_clinic_token`, `cloud_last_sync_at`, `cloud_last_sync_result`, `cloud_last_pull_at`, `cloud_last_push_at` — is kept in `app_settings`. A failed round (offline, etc.) is just recorded, never fatal; env vars `CLINIC_CLOUD_URL` / `CLINIC_CLOUD_TOKEN` override the stored values.

Staff manage it from **Settings → Cloud Sync**: enter the cloud URL + serial and **Pair with cloud** (calls `/api/clinics/register` on the cloud, stores the returned token, runs an immediate first sync), then **Sync now** / **Unpair**. The dashboard shows a small "☁️ Synced …" / "Cloud sync: off" / "⚠️ Cloud sync error" badge. API: `POST /api/cloud/pair` · `GET /api/cloud/status` · `POST /api/cloud/sync-now` · `POST /api/cloud/unpair` (local server only; the cloud node returns `400`).

### Sync model

The mobile app and the local↔cloud mirror reconcile with the server through two endpoints:

- `GET /api/sync/export` — returns the synced tables. Pass `?since=<ISO timestamp>` to get only rows changed after that point (an incremental delta); without it you get a full snapshot. The response also carries a `tombstones` list — `{table_name, row_id, deleted_at}` entries recording rows that were deleted.
- `POST /api/sync/import` — accepts the same shape (`tables` + `tombstones`). Rows are merged **last-write-wins by `updated_at`**; an incoming row that's older than the local copy is skipped. Tombstones propagate deletions the same way: a deletion only takes effect if it's newer than the local row's last update, and a stale row push won't resurrect something that was already deleted (the deletion is remembered in the `sync_tombstones` table).

Both endpoints require a paired-device token (`X-Device-Token` header or `device_token` query param).

### Bluetooth sync (offline fallback)

When the phone can reach neither the LAN nor the cloud node, it falls back to **classic Bluetooth (SPP)** with the desktop. Pair phone ↔ PC once in Windows Bluetooth settings; in the local server's **Settings → Bluetooth Sync** card (`GET /api/bt/status`, `POST /api/bt/configure`), flip *Enable Bluetooth Sync* — that's it. The server auto-picks the right COM port (Windows registers an *incoming* SPP port with `LOCALMFG` in its hwid; the picker ranks that one first), reflected back in the status pill (grey = off, amber = no port found, green = listening / last-synced, red = error). For unusual setups, the *Advanced* disclosure exposes a manual port dropdown + Save. On the phone, **Settings → Bluetooth peer** → "Pick clinic PC" → choose the bonded desktop.

From then on, whenever the phone is in range and Wi-Fi/cloud are unreachable, the app runs one `hello → sync_export → sync_import` round-trip every 30 s over a 4-byte length-prefixed JSON protocol — same `{tables, tombstones}` envelope as the HTTP `/api/sync/*` endpoints, reusing `_collect_sync_export` and `_apply_sync_import` on the server so there is no duplicated sync logic. Last-write-wins by `updated_at` is unchanged. The first wire message is `{"op":"hello","device_token":…}`; the desktop verifies it against `paired_devices` and closes the socket on mismatch. The Settings → Bluetooth peer card also has a **Sync now via Bluetooth** button that forces one immediate cycle, useful for verifying the link.

Desktop side: a daemon thread parallel to `cloud_sync_worker()` re-reads its settings each cycle (`bt_sync_enabled`, `bt_sync_com_port` in `app_settings`), so toggles in the UI take effect without restart. The thread runs in both production and debug (debug-mode guarded by `WERKZEUG_RUN_MAIN` so the reloader's parent process doesn't fight the child for the COM port), skipped on the cloud node, and never holds the socket open between syncs. Phone side: the 30 s loop is driven by a foreground `Timer.periodic` in `ConnectivitySyncService`, which means it ticks while the app is open. Required Android 12+ runtime permissions (`BLUETOOTH_CONNECT`, `BLUETOOTH_SCAN`) are requested when the user flips *Enable Bluetooth sync* in Settings and re-checked each tick — a denied / revoked permission writes a visible error into the card rather than failing silently. (Background-isolate fallback so the loop survives the app being killed is a planned v1.0.x follow-up; `flutter_background_service` is declared but not yet wired.)

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
- Billing / payment records with discount and balance due; payment method is a **Cash / Card / Transfer dropdown**. Every patient picker (payments, statement, appointments) has a **search box** above it that filters the list by name or phone, so it stays usable with a large patient roster

> The dashboard's "Today's Revenue" and "Today's Visits" cards count *today's* follow-up payments and entries (visits are recorded on the follow-up sheet, not the legacy `visits` table). `Clinic profit = price − discount − lab expense`; lab expense is also auto-recorded as a postponed expense, so don't add the two together.

### Header & UI
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
- Translation keys live in the `translations` JS object inside `dental_clinic.py`
- The Flutter app exposes a language toggle in Settings (EN / ع) via `app_state.dart`

---

## Project Structure

> Build artifacts, the SQLite database, logs, the `backups/` folder, and one-off scratch scripts are kept out of version control via `.gitignore`.

```
clinic/
├── dental_clinic.py          # Entire backend: Flask app + HTML/CSS/JS template + SQLite schema
├── requirements.txt          # Flask, Flask-CORS, pyserial, waitress
├── serial_generator.py       # CLI tool to generate and batch-export license serials
├── pytest.ini                # pytest config
├── DentalClinicApp.spec      # PyInstaller build spec
├── DEPLOY_CLOUD.md           # Cloud-node deployment runbook
├── LICENSE                   # Proprietary — all rights reserved
├── cloud/                    # Cloud-node deploy stack
│   ├── Dockerfile            #   the app image (CLINIC_CLOUD_MODE=1)
│   ├── docker-compose.yml    #   app + Caddy (auto-HTTPS)
│   └── Caddyfile             #   TLS / reverse proxy for app.dentacare.tech
├── tests/                    # 145 tests across 19 suites
│   ├── test_api_fuzz.py             # Public API never returns 500 on malformed input
│   ├── test_appointment_api.py
│   ├── test_appointment_flow.py
│   ├── test_appointment_status.py   # Status-update accepts the full dropdown set
│   ├── test_backup.py               # Per-tenant cloud backups + flat single-tenant layout
│   ├── test_bt_codec.py             # 4-byte length-prefixed JSON frame codec
│   ├── test_bt_endpoints.py         # /api/bt/status + /api/bt/configure
│   ├── test_bt_protocol.py          # hello / sync_export / sync_import dispatcher
│   ├── test_bt_session.py           # Frame in → dispatch → frame out, auth gating
│   ├── test_bt_worker.py            # BT daemon thread settings re-read + back-off
│   ├── test_catalog_migration.py    # Legacy treatment_catalog → treatment_procedures
│   ├── test_cloud_mode.py           # Cloud-mode routing, isolation, rate limit, HMAC gate
│   ├── test_cloud_sync_worker.py    # Local ⇄ cloud background sync round-trip
│   ├── test_credit_balance.py       # Patient credit derivation + Credit Used
│   ├── test_date_utils.py
│   ├── test_expression_preservation.py  # "20+20" verbatim on sheet/invoice
│   ├── test_followup_balance.py     # Recomputed Amount to Pay running balance
│   ├── test_sync_resilience.py      # Bad row doesn't kill batch; mobile fixes verified
│   └── test_sync_tombstones.py      # Sync delta / tombstone propagation
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
        ├── models/                     # Appointment, Patient, Visit, BillingRecord, …
        ├── screens/
        │   ├── activation_screen.dart  # First-run: server URL + serial activation
        │   ├── home_screen.dart        # Shell: AppBar + NavigationBar + IndexedStack
        │   ├── dashboard_screen.dart   # Stats grid + recent appointments
        │   ├── patients_screen.dart
        │   ├── patient_detail_screen.dart
        │   ├── appointments_screen.dart
        │   ├── financial_screen.dart
        │   ├── reports_screen.dart
        │   └── settings_screen.dart    # Server URL, sync, dark mode, language
        ├── services/
        │   ├── database_service.dart       # Local SQLite (sqflite)
        │   ├── api_client.dart             # Dio HTTP client
        │   ├── internet_sync_service.dart  # Pull /api/sync/export, push /api/sync/import
        │   ├── connectivity_sync_service.dart
        │   ├── bluetooth_sync_service.dart # Fallback sync over BLE
        │   ├── license_service.dart
        │   ├── patient_service.dart
        │   ├── appointment_service.dart
        │   ├── billing_service.dart
        │   └── report_service.dart
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
| GET / POST | `/api/treatment-plans` | Treatment plans |
| PUT / DELETE | `/api/treatment-plans/<id>` | Manage plan |

### Billing

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / POST | `/api/billing` | List / create billing record |
| DELETE | `/api/billing/<id>` | Delete record |
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
| GET | `/api/bt/status` | Current BT-sync state (`enabled`, `com_port`, `last_sync_at`, `last_error`, `available_ports`) — requires login |
| POST | `/api/bt/configure` | Persist `{enabled, com_port}` to `app_settings`; the daemon thread picks up the new settings on its next loop iteration — requires login |

### Cloud sync (local server only — see *Cloud sync* above)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cloud/pair` | Register this clinic with the cloud node — `{cloud_url, serial_number}` → stores the returned clinic token + runs an immediate first sync |
| GET | `/api/cloud/status` | Pairing + last-sync state (`configured`, `cloud_url`, `clinic_id`, `last_sync_at`, `last_sync_result`, …) |
| POST | `/api/cloud/sync-now` | Run one pull-then-push cycle against the cloud node immediately |
| POST | `/api/cloud/unpair` | Forget the cloud URL + token (stops background sync) |

### Cloud node (only when `CLINIC_CLOUD_MODE=1`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/clinics/register` | Provision a clinic tenant — `{serial_number, clinic_name}` → `{clinic_id, clinic_token, already_registered}`; idempotent per serial. The only `/api/*` endpoint that doesn't need a clinic token |

> On the cloud node every other `/api/*` call must carry `X-Clinic-Token` (or `?clinic_token=`) and is routed to that clinic's database; `/api/medical-images*` returns `501` there; non-`/api/` paths return a short "use your local server" notice. See [`DEPLOY_CLOUD.md`](DEPLOY_CLOUD.md).

### Licensing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/license/activate` | Activate serial, return offline token |
| POST | `/api/license/login` | Token-based login |
| POST | `/api/license/offline-verify` | Verify HMAC token offline |
| GET | `/api/license/status` | Current license info |
| GET | `/api/system/readiness` | Health check |

### Mobile Downloads

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/mobile-download` | Download page |
| GET | `/downloads/android` | Serve Android APK |
| GET | `/downloads/ios` | iOS instructions |
| GET / POST | `/api/mobile/download-links` | Manage download links |

---

## Licensing

Serials are generated with `serial_generator.py`:

```bash
python3 serial_generator.py --clinic "Smile Dental" --code "SMD" --device "LAPTOP-ABC123"
python3 serial_generator.py --clinic "Smile Dental" --code "SMD" \
  --devices-file devices.txt --output serials.csv --key-file backend_key.json
```

Offline tokens are HMAC-SHA256 signed. The mobile app and the cloud node can both verify a token without reaching any other party, so the mobile works entirely air-gapped once activated and the cloud can gate registration without a database lookup.

> Generated `*.csv` / `*.json` outputs from this tool are gitignored — they contain real signed tokens and must not be committed.

## License

This project is licensed under a **proprietary "All Rights Reserved" license** — see [`LICENSE`](LICENSE) for the full notice. The source is on GitHub for backup and portfolio purposes; reuse, redistribution, or modification requires written permission from the copyright holder.

---

## Tests

```bash
cd clinic/
python3 -m pytest tests/ -v
```

**148 tests across 19 suites.** Covers the appointment API + flow, date utilities, the catalog migration, follow-up running balance, patient credit balance, expression preservation in money fields, appointment status updates, sync tombstones (delta export + deletion propagation), sync resilience (per-row error isolation, mobile-shaped payloads, billing `amount`), cloud-mode multi-tenant routing + tenant isolation + rate limit + HMAC-signed serials, the local ⇄ cloud background sync round-trip, the per-tenant cloud backup loop (master + each `clinic_<id>.db`, per-label retention, isolation on per-tenant failure) plus the historic flat single-tenant layout, the Bluetooth-SPP fallback (4-byte length-prefixed frame codec, hello/sync_export/sync_import dispatcher reusing the HTTP helpers, full session driver including malformed-frame handling, `/api/bt/status` + `/api/bt/configure` endpoints behind staff login, and a daemon-thread worker that re-reads settings each cycle and recovers from `SerialException`), and a 38-case property-fuzz suite that exercises every public endpoint with malformed JSON, wrong types, missing fields and oversized payloads — anything returning HTTP 5xx is a test failure.

The Flutter app has its own analyzer-clean test suite under `clinic_mobile_app/test/` — currently `bluetooth_frame_codec_test.dart`, `bt_session_client_test.dart`, `bluetooth_sync_service_test.dart`, and the default widget test (13 tests total). Run with `cd clinic_mobile_app && flutter test`.

Financial logic can also be exercised end-to-end against a running server with the ad-hoc runner under `tools/`:

```bash
python tools/qa_financial_test.py
```

Covers 10 blocks: summary math, weekly range math, Saturday edge case, receivables discount correctness, follow-up running balance, billing records, expenses, edge cases, monthly range, and cross-report consistency.

### Continuous integration

`.github/workflows/ci.yml` runs on every push to `main`/`develop` and on pull requests: it installs `requirements.txt`, syntax-checks `dental_clinic.py` (`py_compile`), and runs `pytest tests/` against Python 3.10, 3.11 and 3.12.

---

## Packaging (Windows executable)

```bash
pyinstaller DentalClinicApp.spec
# Output: dist/DentaCare.exe
```

The `.spec` file bundles `dental_clinic.py` and `DentaCare.PNG` into a single portable `.exe` — no Python installation required on the target machine. The SQLite database, `uploads/` and `backups/` are created at runtime next to the executable. The `hiddenimports` list includes `waitress`, `markupsafe`, `werkzeug.security` (auth / production server), and `serial` + `serial.tools.list_ports` (Bluetooth-SPP sync — the daemon thread imports `pyserial` lazily but PyInstaller needs them declared up front); keep them there if you regenerate the spec. When frozen, the app defaults to production mode (waitress + automatic backups).

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
| `flutter_background_service` | Android foreground service for the 30 s BT auto-reconnect loop |
| `fl_chart` | Financial charts |
| `table_calendar` | Appointment calendar view |
| `flutter_animate` | UI micro-animations |
| `google_fonts` | Typography |
| `intl` | Date/number formatting + i18n |
