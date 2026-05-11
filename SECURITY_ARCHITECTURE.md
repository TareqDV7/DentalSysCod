# Complete Security Architecture - Dental Clinic Licensing System

**Version**: 1.0 | **Status**: Production Ready
**Date**: 2026-05-01

## Overview

The Dental Clinic licensing system combines **external serial generation** with **device-locked offline tokens** to create a secure, non-transferable licensing model.

```
┌─────────────────────────────────────────────────────────────────┐
│         EXTERNAL SERIAL GENERATOR (standalone tool)            │
│                                                                   │
│  Input: Device ID, Clinic Name, Plan, Expiry                   │
│  ↓                                                               │
│  Generate: Unique Serial + HMAC-Signed Token                   │
│  ↓                                                               │
│  Output: DENTAL-SMD-LAPTO-00001 + Offline Token                │
│                                                                   │
│  Output: CSV with serials.csv for distribution                 │
└─────────────────────────────────────────────────────────────────┘
                          ↓
              (Distribution to Clinic Admins)
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│           CLINIC DEVICE (Desktop/Mobile App)                   │
│                                                                   │
│  Step 1: Get device_id (computer name, serial, mac hash)       │
│  Step 2: Input serial: DENTAL-SMD-LAPTO-00001                 │
│  Step 3: Call /api/license/activate (device_id + serial)       │
│  Step 4: Receive offline_license_token                         │
│  Step 5: Store token in localStorage (mobile) or DB (desktop)  │
│                                                                   │
│  Step 6 onwards: Works offline using stored token              │
└─────────────────────────────────────────────────────────────────┘
                          ↓
              (Token Call to Backend)
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│               BACKEND VALIDATION (dental_clinic.py)             │
│                                                                   │
│  Validate:                                                       │
│  ├─ Serial exists and is valid                                 │
│  ├─ Serial not already used on different device                │
│  ├─ device_id matches request                                  │
│  └─ Generate offline token with device_id embedded             │
│                                                                   │
│  Offline Token:                                                  │
│  ├─ Payload: JSON(serial, clinic_name, device_id, expiry)     │
│  ├─ Signature: HMAC-SHA256(payload)                            │
│  └─ Format: base64(payload).base64(signature)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Security Properties

### ✅ What This System Provides

1. **Device Locking**
   - Each serial bound to one device_id
   - Serial for Device A won't work on Device B
   - Non-transferable by design

2. **Offline Operation**
   - Token signature verifiable without network
   - Device works offline indefinitely (until expiry)
   - No phone-home requirements

3. **Tamper-Proof**
   - HMAC-SHA256 signature detects modification
   - Constant-time comparison prevents timing attacks
   - Backend signing key required to forge tokens

4. **Expiry & Grace**
   - Active license period (e.g., 365 days)
   - 30-day grace period for extension/renewal
   - Clear expiry messages to user

5. **External Generation**
   - Serial generator kept separate from main system
   - Admin controls when/which serials are issued
   - Serials created before deployment to device

### ⚠️ What This System Does NOT Protect

- Won't prevent: User sharing device with multiple people
- Won't prevent: Physical theft of licensed device
- Won't prevent: Sharing offline token between similar devices
  - *Mitigation*: Unique hardware fingerprint (not just computer name)

## File Structure

```
clinic/
├── serial_generator.py                    ← External tool (run separately)
├── SERIAL_GENERATOR_README.md            ← User guide
├── LICENSE_INTEGRATION_GUIDE.md           ← Backend integration steps
├── example_devices.txt                    ← Sample device list
├── batch_serials.csv                      ← Generated serials (example)
│
├── dental_clinic.py                       ← Backend (has token functions)
│   ├── get_or_create_license_signing_key()
│   ├── build_offline_license_payload()
│   ├── encode_offline_license_token()
│   ├── decode_offline_license_token()
│   ├── verify_offline_license_token()
│   ├── /api/license/activate              ← NEEDS: device_id validation
│   └── /api/license/offline-verify        ← NEEDS: device_id check
│
├── clinic_mobile_app/lib/main.dart        ← Flutter (NEEDS: device_id capture)
│   ├── Get device_id
│   ├── Call /api/license/activate
│   └── Store offline_license_token
│
└── DentalClinicApp.spec                   ← Desktop app (NEEDS: device_id capture)
    ├── Get device_id
    ├── Call /api/license/activate
    └── Store offline_license_token
```

## Activation Flow

### User's First Run

```
User: Runs app for first time
  ↓
App: Detects no license, shows input form
  ↓
User: Enters serial: DENTAL-SMD-LAPTO-00001
  ↓
App: 
  ├─ Gets device_id: "LAPTOP-DOCTOR-001"
  └─ Calls: POST /api/license/activate
     {
       "serial": "DENTAL-SMD-LAPTO-00001",
       "device_id": "LAPTOP-DOCTOR-001",
       "clinic_name": "Smile Dental"
     }
  ↓
Backend:
  ├─ Verifies: serial "DENTAL-SMD-LAPTO-00001" exists ✓
  ├─ Checks: not already used on different device ✓
  ├─ Verifies: device_id matches ✓
  └─ Generates: offline_license_token with device_id embedded
  ↓
App:
  ├─ Receives: offline_license_token
  ├─ Stores: in localStorage (mobile) or local DB (desktop)
  └─ Shows: "✓ License activated successfully"
  ↓
App: Can now work offline indefinitely
  ├─ On startup: Verifies stored token signature (offline)
  ├─ Checks: device_id still matches
  ├─ Checks: not expired
  └─ Allows: Normal operation ✓
```

### User on Different Device

```
User: Takes serial "DENTAL-SMD-LAPTO-00001" to different computer
  ↓
App on LAPTOP-RECEPTIONIST: Detects no license
  ↓
User: Enters same serial: DENTAL-SMD-LAPTO-00001
  ↓
App: 
  ├─ Gets device_id: "LAPTOP-RECEPTIONIST-001"
  └─ Calls: POST /api/license/activate
     {
       "serial": "DENTAL-SMD-LAPTO-00001",
       "device_id": "LAPTOP-RECEPTIONIST-001"
     }
  ↓
Backend:
  ├─ Finds: Serial "DENTAL-SMD-LAPTO-00001" already used
  ├─ Checks: stored device_id = "LAPTOP-DOCTOR-001"
  ├─ Compares: request device_id = "LAPTOP-RECEPTIONIST-001"
  ├─ MISMATCH! ✗
  └─ Returns: HTTP 409 Conflict
     {
       "status": "error",
       "message": "Serial already activated on different device",
       "detail": "Serial locked to: LAPTOP-DOCTOR-001"
     }
  ↓
App: Shows error
  "⚠️ This serial is locked to a different device
   Contact clinic admin for a new serial"
  ↓
Outcome: ✗ License activation FAILS
```

## Device ID Strategy

The security of the system depends on unique, stable device identification.

### Recommended Approach (Best: Hybrid)

```python
# 1. Get computer hostname (stable, human-readable)
import socket
hostname = socket.gethostname()  # "LAPTOP-DOCTOR-001"

# 2. Get first MAC address (hardware-specific)
import subprocess
mac = subprocess.run(
    "getmac /v | head -1",
    capture_output=True,
    shell=True,
    text=True
).stdout.strip()

# 3. Combine for unique ID
device_id = f"{hostname}_{mac[:8]}"  # "LAPTOP-DOCTOR-001_001122FF"
```

### Device ID Options by Platform

| Method | Windows | Linux | Mac | Pros | Cons |
|--------|---------|-------|-----|------|------|
| Hostname | ✓ | ✓ | ✓ | Human-readable | Can be changed |
| MAC address | ✓ | ✓ | ✓ | Hardware-tied | Can spoof, multi-NIC |
| Serial number | ✓ | ~ | ✓ | Unique, permanent | Varies by hardware |
| UUID/GUID | ✓ | ✓ | ✓ | Unique per OS install | Regenerable |
| Combination | ✓ | ✓ | ✓ | Best balance | More complex |

**Recommendation**: Use hostname + first MAC address hash for stability & security.

## Testing Checklist

- [ ] Serial generator creates valid tokens with correct device_id
- [ ] Backend activation rejects serial on mismatched device
- [ ] Backend allows same serial on same device
- [ ] Offline verification works without network
- [ ] Offline verification fails with wrong device_id
- [ ] Token signature invalid if modified
- [ ] Expiry dates are honored (with grace period)
- [ ] Multiple devices can have different serials (one per device)

## Production Deployment Steps

1. **Configure Serial Generator**
   - Keep `serial_generator.py` on admin machine (NOT on server)
   - Generate serials as clinic onboards
   - Export CSV and distribute to clinic

2. **Update Backend**
   - Apply changes to `/api/license/activate` (device_id validation)
   - Apply changes to `/api/license/offline-verify` (device_id check)
   - Optional: Create license tracking table
   - Test with sample serials

3. **Update Desktop App**
   - Add device_id capture code
   - Pass device_id to /api/license/activate
   - Store offline token locally
   - Verify offline licensing works

4. **Update Mobile App**
   - Add device_id capture code (using device_info_plus or similar)
   - Pass device_id to /api/license/activate
   - Store offline token in secure storage
   - Verify offline licensing works

5. **Distribution**
   - Create serials for each clinic's devices
   - Document which serial goes to which device
   - Provide serial + instruction to clinic admin
   - Clinic admin inputs serial on first app run

6. **Monitoring**
   - Log activation attempts (especially failures)
   - Track license usage by clinic/device
   - Alert on unusual patterns (cross-device attempts)
   - Support process for serial renewal/reset

## Support Scenarios

### Scenario 1: Device Replacement
```
Problem: Clinic got new laptop, old serial won't work on new machine
Solution: Generate new serial for new device using serial_generator.py
```

### Scenario 2: Honest Error
```
Problem: User entered wrong serial number
Solution: Verify in serial CSV which serial matches device_id
          Provide correct serial and ask user to re-activate
```

### Scenario 3: Serial Expiry
```
Problem: License shows "License expired" 
Action: 
  ├─ If within 30-day grace period: Show "Please renew" message
  ├─ After grace period: Block app access
Solution: Generate new serial with extended expiry date
```

### Scenario 4: Offline Token Corruption
```
Problem: Stored token corrupted/deleted
Solution: Device can still activate online if it has network
          Backend will regenerate offline token
```

## Security Key Rotation

If backend signing key is ever compromised:

1. Generate new signing key:
   ```sql
   UPDATE app_settings 
   SET key = NEW_RANDOM_KEY 
   WHERE key_name = 'license_signing_key'
   ```

2. Regenerate all serials with new key:
   ```bash
   python serial_generator.py --key-file new_backend_key.json ...
   ```

3. All existing devices must re-activate with new serials

## Files & Checksums

| File | Purpose | Validation |
|------|---------|-----------|
| `serial_generator.py` | Standalone serial tool | py_compile check |
| `SERIAL_GENERATOR_README.md` | User documentation | Manual review |
| `LICENSE_INTEGRATION_GUIDE.md` | Backend integration | Manual review |
| `dental_clinic.py` | Backend with token functions | py_compile check |
| `clinic_mobile_app/` | Flutter app | flutter analyze |
| `DentalClinicApp.exe` | Desktop binary | SHA256 checksum |

## References

- RFC 2104: HMAC specification
- RFC 4648: Base64 Data Encodings
- OWASP: Device Identification Best Practices
- CWE-287: Improper Authentication

---

**Last Updated**: 2026-05-01
**Next Review**: After production deployment
**Status**: ✅ Ready for Implementation
