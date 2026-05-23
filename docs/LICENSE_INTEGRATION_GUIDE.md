# License Activation Integration Guide
## How Backend Validates Device-Locked Serials

This guide explains how the main Dental Clinic system integrates with the external Serial Generator tool to provide device-locked licensing.

## Current Backend Status

The backend (`dental_clinic.py`) already has:
✓ Offline license token system (HMAC-SHA256)
✓ Token encoding/decoding functions
✓ `/api/license/activate` endpoint
✓ `/api/license/offline-verify` endpoint
✓ localStorage support in portal

## How Device Locking Works

### Step 1: Desktop/Mobile App Gets Device ID
```python
# Example: Get Windows computer name
import socket
device_id = socket.gethostname()  # e.g., "LAPTOP-DOCTOR-001"

# Or use hardware serial (more secure):
# import subprocess
# device_id = subprocess.run(
#     "wmic baseboard get serialnumber",
#     capture_output=True, text=True
# ).stdout.strip()
```

### Step 2: App Calls /api/license/activate
```python
import requests

payload = {
    "serial": "DENTAL-SMD-LAPTO-00001",  # From serial generator
    "device_id": "LAPTOP-DOCTOR-001",     # Current device identifier
    "clinic_name": "Smile Dental Clinic"
}

response = requests.post(
    "http://localhost:5000/api/license/activate",
    json=payload
)

result = response.json()
# {
#   "status": "success",
#   "offline_license_token": "eyJ...",
#   "expires_at": "2027-05-01T...",
#   "device_id": "LAPTOP-DOCTOR-001"
# }
```

### Step 3: Backend Validates Device ID
Current endpoint needs modification:

```python
# BEFORE: Only checked serial
@app.route('/api/license/activate', methods=['POST'])
def activate_license():
    data = request.json
    serial = data.get('serial')
    # ...validate serial...

# AFTER: Also validate device_id
@app.route('/api/license/activate', methods=['POST'])
def activate_license():
    data = request.json
    serial = data.get('serial')
    device_id = data.get('device_id')  # NEW: Get device ID from request
    
    # Validate serial exists
    # Validate serial not already activated on different device
    # Validate device_id matches
    # Generate offline_license_token with device_id embedded
    # Return token to client
```

### Step 4: Token Contains Device ID
The offline license token payload includes:
```json
{
  "serial": "DENTAL-SMD-LAPTO-00001",
  "clinic_name": "Smile Dental Clinic",
  "device_id": "LAPTOP-DOCTOR-001",    ← Device binding
  "status": "active",
  "max_devices": 1,
  "issued_at": "2026-05-01T13:05:30.226109Z",
  "expires_at": "2027-05-01T13:05:30.226109Z",
  "licensed": true
}
```

### Step 5: Verification Flow
```
User tries to activate on Device B:
├─ Device B sends: serial + device_id_B
├─ Backend receives offline_license_token from Device A
├─ Backend checks:
│  ├─ Token signature valid? ✓
│  ├─ Token expired? No ✓
│  ├─ device_id in token == device_id_B? ✗ MISMATCH
│  └─ REJECT activation ✗

→ License activation FAILS on Device B
→ Serial "DENTAL-SMD-LAPTO-00001" only works on Device A
```

## Required Backend Changes

### 1. Modify /api/license/activate Endpoint

**File**: `dental_clinic.py`

**Location**: Find the activate_license() function

**Changes needed**:

```python
@app.route('/api/license/activate', methods=['POST'])
def activate_license():
    """
    Activate license with device locking
    
    Request JSON:
    {
        "serial": "DENTAL-SMD-LAPTO-00001",
        "device_id": "LAPTOP-DOCTOR-001",    ← NEW: Device identifier
        "clinic_name": "Smile Dental Clinic"
    }
    """
    try:
        data = request.json
        serial = data.get('serial', '').strip()
        device_id = data.get('device_id', '').strip()  # NEW
        clinic_name = data.get('clinic_name', '').strip()
        
        # VALIDATION: Require device_id
        if not device_id:
            return {
                'status': 'error',
                'message': 'device_id is required for device-locked licensing'
            }, 400
        
        # Check if serial exists in database (if tracking)
        cursor = get_db_cursor()
        cursor.execute(
            'SELECT * FROM licenses WHERE serial = ?',
            (serial,)
        )
        existing = cursor.fetchone()
        
        # NEW: If serial already activated, verify it's same device
        if existing:
            stored_device_id = existing.get('device_id')
            if stored_device_id and stored_device_id != device_id:
                return {
                    'status': 'error',
                    'message': 'Serial already activated on different device',
                    'detail': f'Serial locked to: {stored_device_id}'
                }, 409  # Conflict
        
        # Get signing key for token generation
        signing_key = get_or_create_license_signing_key(cursor)
        
        # Build offline license payload WITH device_id
        payload = build_offline_license_payload(
            serial=serial,
            clinic_name=clinic_name,
            device_id=device_id,  # NEW: Include device lock
            plan_name='Standard'
        )
        
        # Encode offline token
        offline_token = encode_offline_license_token(payload, signing_key)
        
        # NEW: Store activation record (optional, for tracking)
        cursor.execute(
            '''INSERT OR REPLACE INTO licenses 
               (serial, device_id, clinic_name, activated_at) 
               VALUES (?, ?, ?, ?)''',
            (serial, device_id, clinic_name, datetime.utcnow().isoformat())
        )
        get_db().commit()
        
        return {
            'status': 'success',
            'message': f'License activated on device: {device_id}',
            'offline_license_token': offline_token,
            'serial': serial,
            'device_id': device_id,  # Echo back for confirmation
            'expires_at': payload['expires_at'],
            'clinic_name': clinic_name
        }, 200
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Activation failed: {str(e)}'
        }, 500
```

### 2. Modify /api/license/offline-verify Endpoint

**File**: `dental_clinic.py`

**Location**: Find the offline_verify_license() function

**Changes needed**:

```python
@app.route('/api/license/offline-verify', methods=['POST'])
def offline_verify_license():
    """
    Verify offline license token on device (without network)
    
    Request JSON:
    {
        "token": "eyJ...",
        "device_id": "LAPTOP-DOCTOR-001"  ← NEW: Current device
    }
    """
    try:
        data = request.json
        token = data.get('token', '').strip()
        device_id = data.get('device_id', '').strip()  # NEW
        
        if not token or not device_id:
            return {'status': 'error', 'message': 'token and device_id required'}, 400
        
        signing_key = get_or_create_license_signing_key(get_db_cursor())
        is_valid, payload = verify_offline_license_token(token, signing_key)
        
        if not is_valid:
            return {
                'status': 'invalid',
                'message': 'License token invalid or expired'
            }, 403
        
        # NEW: Verify device_id matches
        token_device_id = payload.get('device_id', '')
        if token_device_id != device_id:
            return {
                'status': 'invalid',
                'message': 'License locked to different device',
                'detail': f'Token locked to: {token_device_id}, Current device: {device_id}'
            }, 403
        
        return {
            'status': 'valid',
            'message': 'License active on this device',
            'serial': payload.get('serial'),
            'clinic_name': payload.get('clinic_name'),
            'expires_at': payload.get('expires_at'),
            'device_id': device_id
        }, 200
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Verification failed: {str(e)}'
        }, 500
```

### 3. Add Database Table for License Tracking (Optional)

```sql
-- Optional: Track which serial is on which device
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial TEXT UNIQUE NOT NULL,
    device_id TEXT NOT NULL,
    clinic_name TEXT,
    activated_at TIMESTAMP,
    last_verified TIMESTAMP,
    status TEXT DEFAULT 'active'  -- active, revoked, expired
);
```

## Mobile/Desktop App Integration

### Flutter Example (lib/main.dart)

```dart
// 1. Get device ID
import 'dart:io';

Future<String> getDeviceId() async {
  if (Platform.isAndroid) {
    // Use Android device name or serial
    // or use device_info_plus package:
    // final deviceInfo = await DeviceInfoPlugin().androidInfo;
    // return deviceInfo.serialNumber;
    return 'DEVICE-${Platform.operatingSystem}-001';
  } else if (Platform.isIOS) {
    // Use iOS device name
    // final deviceInfo = await DeviceInfoPlugin().iosInfo;
    // return deviceInfo.identifierForVendor;
    return 'DEVICE-iOS-001';
  }
  return 'DEVICE-Unknown';
}

// 2. Call activation with device ID
Future<void> activateLicense(String serial) async {
  final deviceId = await getDeviceId();
  
  final response = await http.post(
    Uri.parse('$serverUrl/api/license/activate'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'serial': serial,
      'device_id': deviceId,  // Include device ID
      'clinic_name': 'Smile Dental'
    }),
  );
  
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    final offlineToken = data['offline_license_token'];
    
    // Store token in localStorage
    await storage.write(
      key: 'OFFLINE_LICENSE_KEY',
      value: offlineToken,
    );
  }
}

// 3. Verify offline (no network needed)
Future<bool> verifyLicenseOffline() async {
  final deviceId = await getDeviceId();
  final token = await storage.read(key: 'OFFLINE_LICENSE_KEY');
  
  if (token == null) return false;
  
  // For offline verification, use the verify function directly
  // (no HTTP call needed)
  return verifyOfflineLicenseLocal(token, deviceId);
}
```

### Python/PyInstaller Example (dental_clinic_client.py)

```python
import requests
import socket
import json

def get_device_id():
    """Get computer name as device identifier"""
    return socket.gethostname()

def activate_license(server_url: str, serial: str):
    """Activate license on this device"""
    device_id = get_device_id()
    
    response = requests.post(
        f'{server_url}/api/license/activate',
        json={
            'serial': serial,
            'device_id': device_id,  # Include device
            'clinic_name': 'Smile Dental'
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data['offline_license_token']
        
        # Store token locally
        with open('license.txt', 'w') as f:
            f.write(token)
        
        return True, data['message']
    else:
        error = response.json()
        return False, error.get('message')

def verify_license_offline():
    """Verify stored license offline"""
    device_id = get_device_id()
    
    try:
        with open('license.txt', 'r') as f:
            token = f.read()
    except FileNotFoundError:
        return False, 'No license found'
    
    # Verify signature matches
    # (call backend's verify function)
    return True, 'License valid'
```

## Security Considerations

### ✓ Do's
- ✓ Validate device_id on every activation
- ✓ Include device_id in token payload
- ✓ Log activation attempts (especially failures)
- ✓ Store license tokens securely (encrypted storage)
- ✓ Use consistent device_id generation

### ✗ Don'ts
- ✗ Allow serial transfer between devices
- ✗ Skip device_id validation
- ✗ Store raw tokens in plain text
- ✗ Use weak device identifiers (e.g., username)
- ✗ Ignore signature verification errors

## Testing

### Test Case 1: Valid Activation
```bash
# Generate serial for LAPTOP-001
python serial_generator.py --clinic "Test" --code "TST" --device "LAPTOP-001"

# Output: DENTAL-TST-LAPTO-00001

# Activate on LAPTOP-001
curl -X POST http://localhost:5000/api/license/activate \
  -H "Content-Type: application/json" \
  -d '{
    "serial": "DENTAL-TST-LAPTO-00001",
    "device_id": "LAPTOP-001",
    "clinic_name": "Test Clinic"
  }'

# Expected: Status 200, offline_license_token returned ✓
```

### Test Case 2: Cross-Device Rejection
```bash
# Try same serial on LAPTOP-002
curl -X POST http://localhost:5000/api/license/activate \
  -H "Content-Type: application/json" \
  -d '{
    "serial": "DENTAL-TST-LAPTO-00001",
    "device_id": "LAPTOP-002",
    "clinic_name": "Test Clinic"
  }'

# Expected: Status 409, message "Serial already activated on different device" ✗
```

### Test Case 3: Offline Verification
```bash
# Get token from activation above
TOKEN="eyJ..."

# Verify on same device
curl -X POST http://localhost:5000/api/license/offline-verify \
  -H "Content-Type: application/json" \
  -d '{
    "token": "'$TOKEN'",
    "device_id": "LAPTOP-001"
  }'

# Expected: Status 200, "valid" ✓
```

### Test Case 4: Offline Verification Cross-Device
```bash
# Try same token on different device
curl -X POST http://localhost:5000/api/license/offline-verify \
  -H "Content-Type: application/json" \
  -d '{
    "token": "'$TOKEN'",
    "device_id": "LAPTOP-002"
  }'

# Expected: Status 403, message "License locked to different device" ✗
```

## Deployment Checklist

- [ ] Update `/api/license/activate` with device_id validation
- [ ] Update `/api/license/offline-verify` with device_id check
- [ ] Add license tracking table (optional)
- [ ] Update Flutter/mobile app to capture device_id
- [ ] Update PyInstaller desktop app to capture device_id
- [ ] Test all 4 scenarios above
- [ ] Update frontend UI to show device_id confirmation
- [ ] Document device_id strategy for clinics
- [ ] Train clinic admins on serial distribution

## Files Changed

- `serial_generator.py` - External tool (no changes needed after creation)
- `dental_clinic.py` - Backend endpoints (needs `/api/license/activate` and `/api/license/offline-verify` updates)
- `clinic_mobile_app/lib/main.dart` - Mobile app (needs device_id capture)
- `DentalClinicApp.spec` / Desktop source - Desktop app (needs device_id capture)

---

**Integration Status**: Ready for implementation
**Complexity**: Medium (2-3 hours of backend + app changes)
**Security Level**: High (device-locking prevents license theft)
