# Dental Clinic Mobile App

Flutter application for device-locked license activation and offline token verification.

## Recent fixes (2026-06)

- **One unified patient ledger (sheet + billing).** A patient now has a single
  balance: `Outstanding = Σ charges − Σ payments`, where **both** the follow-up
  sheet and billing contribute charges *and* payments. A billing entry can be a
  charge, a payment, or both — a **payment-only** receipt has charge 0 and just
  draws the balance down. Overpayment is simply a negative balance (credit); the
  old separate "Use credit" step is gone. The profile balance, Billing tab
  (Accounts), Receivables, payment history, and dashboard revenue all derive
  from `DatabaseService.getPatientBalance()`, so every surface shows the same
  number and the desktop and mobile agree. Mirrors the desktop's
  `get_patient_balance`. See `docs/superpowers/specs/2026-06-12-unified-patient-ledger-design.md`.
- **Billing tab has an Accounts / Invoices toggle.** *Accounts* (default) is the
  per-patient unified rollup (charged / paid / balance / status) — tap a patient
  to open their full payment history. *Invoices* keeps individual billing entries
  with **Add** (charge and/or payment). Query: `getBillingAccounts()`; model:
  `BillingAccount`; view: `lib/screens/billing_accounts_view.dart`.
- **Dashboard Revenue now includes Billing.** The Revenue stat (and its
  sparkline) sums both visit/follow-up payments **and** Financial → Billing
  paid amounts, so any recorded transaction is reflected. The kept-alive
  dashboard also reloads when you switch back to it, so figures are never stale
  after edits made on other tabs.
- **Appointment booking warns on taken slots.** When the chosen time overlaps an
  existing scheduled appointment, the add-appointment sheet shows a
  "this time is already booked" warning (naming the clashing time) — but still
  lets you save (warn-but-allow; supports running more than one chair). Overlap
  logic lives in `lib/utils/appointment_overlap.dart`.
- **Larger launcher icon.** The home-screen icon is regenerated from a tighter
  crop of the logo (`dentacare_icon_launcher.png` / `dentacare_icon_fg.png`) so
  it no longer floats small inside a sea of white. The in-app logo
  (`dentacare_icon.png`) is unchanged. Regenerate with
  `dart run flutter_launcher_icons`.

## Features

- ✅ Hardware-based device ID detection (Android/iOS/Windows/macOS/Linux)
- ✅ Device-locked offline tokens (HMAC-SHA256)
- ✅ Secure storage via `flutter_secure_storage`
- ✅ Two activation modes: **Online** (backend API) + **Offline** (paste token)
- ✅ Standalone operation after activation

---

## Quick Start

### Setup
```bash
cd clinic_mobile_app
flutter pub get
flutter analyze  # Should show: No issues found!
```

### Run
```bash
flutter run  # Runs on default emulator/device
```

### Activate Online
1. Ensure backend is running: `python dental_clinic.py`
2. In app, enter serial number and clinic name
3. Press "Activate" → receives offline token
4. Proceeds to MainScreen

### Activate Offline  
1. Paste pre-generated token into "Paste offline token" field
2. Press "Use Token"  
3. Token stored locally → MainScreen

---

## Device ID Detection

App detects hardware identifiers on each platform:

| Platform  | Source                  |
|-----------|-------------------------|
| Android   | `android.os.Build.ID`   |
| iOS       | `identifierForVendor`   |
| Windows   | WMIC baseboard serial    |
| macOS     | IOPlatformSerialNumber  |
| Linux     | `/etc/machine-id`       |

*Fallback: UUID generated and persisted*

---

## Build for Release

```bash
flutter build apk --release      # Android APK
flutter build appbundle --release # Android Bundle
flutter build ios --release       # iOS
flutter build windows --release   # Windows
```

---

## File Structure

```
lib/
├── main.dart                    # App entry + AppEntry routing
├── screens/
│   ├── activation_screen.dart   # Activation UI
│   └── main_screen.dart         # Licensed app main
├── services/
│   ├── device_service.dart      # Hardware ID detection
│   ├── license_service.dart     # Backend API
│   └── local_storage_service.dart # Secure storage
```

---

## Architecture

### AppEntry (main.dart)
- On startup, checks if token exists and is valid
- Decodes token to verify device_id matches current hardware
- Routes to ActivationScreen (invalid/missing) or MainScreen (valid)

### ActivationScreen
- **Online Mode**: Collects serial_number + clinic_name → calls `/api/license/activate`
- **Offline Mode**: Paste pre-generated token → stores directly
- Both modes → token stored securely → MainScreen opened

### MainScreen
- Displays activated license info (serial, clinic name)
- Patient/appointment/billing buttons (placeholder UI)
- Logout button clears stored token

---

## Services

### LocalStorageService
Wrapper around `flutter_secure_storage` for encrypted key-value storage:
- `device_token`: Active offline token
- `device_id`: Persisted UUID fallback
- `serial_number`: License serial
- `clinic_name`: Clinic name

### DeviceService  
Hardware-based device ID detection with platform-specific logic:
- Returns format: `DEVICE-XXXXXXXXXXXXX` (16 hex chars)
- Falls back to persisted UUID if hardware detection fails

### LicenseService
Backend API client:
- `activate(baseUrl, serialNumber, clinicName, deviceId, deviceName)`
- Returns: `offline_license_token` in response

---

## Testing Activation Locally

### Start Backend
```bash
cd clinic
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe dental_clinic.py
```

Backend runs on `http://localhost:5000`

### Run Mobile App
```bash
cd clinic_mobile_app
flutter run
```

### Activate  
1. App shows ActivationScreen
2. Enter serial: `SN123456`
3. Enter clinic: `Main Clinic`
4. Press "Activate"
5. App calls `POST /api/license/activate`
6. Receives offline token
7. Token stored
8. Routes to MainScreen

---

## Offline Token Format

Base64url-encoded JSON payload + HMAC-SHA256 signature:

```
token = base64url(payload) + "." + base64url(signature)

payload = {
  "device_id": "DEVICE-ABC123DEF456789",
  "serial_number": "SN123456",
  "expires_at": "2025-12-31T23:59:59Z",
  "validity": true
}

signature = HMAC-SHA256(payload, signing_key)
```

Verification enforces:
1. HMAC matches stored signing key
2. `device_id` matches current hardware
3. `expires_at` hasn't passed

---

## Troubleshooting

### "License invalid or locked to different device"
- Token bound to a specific device ID
- Cannot be transferred between devices
- Generate new token on target device

### Token expired
- Check `expires_at` in token payload
- Request new token from backend

### Device ID mismatch
- Hardware detection failed
- Check platform-specific prerequisites
- May use persisted UUID as fallback

---

For full system documentation, see the [main README](../README.md).
