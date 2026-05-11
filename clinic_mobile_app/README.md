# Dental Clinic Mobile App

Flutter application for device-locked license activation and offline token verification.

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
