# Serial License Generator - External Security Tool

**الأداة الخارجية لإصدار السيريلات الآمنة**

This is a standalone tool separate from the main Dental Clinic system. It generates device-locked activation serials that are tied to specific hardware, preventing license transfers between devices.

## How It Works (كيف تعمل)

### License Security Model
```
1. Device Identifier
   └── Device ID (hardware fingerprint: computer name, Mac address hash, etc.)

2. Serial Generation (خارجي - External)
   ├── Input: Device ID, Clinic Name, Plan, Expiry
   └── Output: Serial Number + Offline License Token

3. Serial Format
   └── DENTAL-[CLINIC_CODE]-[DEVICE_HASH]-[COUNTER]
      Example: DENTAL-SMD-LAPTO-00001

4. Offline License Token
   ├── Payload: JSON with serial + device_id + clinic_name + expiry
   ├── Signature: HMAC-SHA256 of payload
   └── Format: base64(payload).base64(signature)

5. Security: Each serial is locked to ONE device
   ├── Serial DENTAL-SMD-LAPTO-00001 → locked to LAPTOP-DOCTOR-001
   ├── Cannot be used on LAPTOP-RECEPTIONIST-001
   ├── Cannot be transferred or copied
   └── Unique device_id check on activation
```

## Installation

```bash
# No additional dependencies needed! Already uses Python stdlib:
# - hmac, hashlib, base64, json, csv, argparse, datetime

# Just copy serial_generator.py to your clinic directory
cp serial_generator.py /path/to/clinic/
```

## Usage

### 1. Generate Single Device Serial
```bash
python serial_generator.py \
  --clinic "Smile Dental Clinic" \
  --code "SMD" \
  --device "LAPTOP-DOCTOR-001" \
  --expiry 365
```

Output:
```
SERIAL NUMBER: DENTAL-SMD-LAPTO-00001

Offline License Token (copy to device):
eyJzZXJpYWwiOiJERU50QUwtU01ELUxBUFRPLTAwMDAxIiwi...
```

### 2. Batch Generate from Device List
```bash
# Create devices.txt with one device ID per line:
cat > devices.txt << EOF
LAPTOP-DOCTOR-001
LAPTOP-RECEPTIONIST-001
DESKTOP-NURSE-LAB-001
IPAD-WAITING-ROOM-001
EOF

# Generate all serials to CSV
python serial_generator.py \
  --clinic "Smile Dental Clinic" \
  --code "SMD" \
  --devices-file devices.txt \
  --expiry 365 \
  --output serials.csv
```

Output file: `serials.csv` with columns:
- Serial
- Device ID
- Clinic Name
- Plan
- Issued At
- Expires At
- Offline Token

### 3. Using Custom Backend Signing Key (Optional)
```bash
# Export signing key from backend database first:
# SELECT key FROM app_settings WHERE key_name = 'license_signing_key'

python serial_generator.py \
  --clinic "Smile Dental Clinic" \
  --code "SMD" \
  --device "LAPTOP-DOCTOR-001" \
  --key-file backend_signing_key.json
```

**Note**: If no key-file provided, tool uses default signing key. For production, export the backend's signing key to ensure tokens match.

## Device Identification Methods

The `device_id` must uniquely identify each machine. Common approaches:

### Option 1: Computer Hostname (Easiest)
```bash
# Windows
echo %COMPUTERNAME%

# Linux/Mac
hostname
```

### Option 2: Hardware Hash (More Secure)
```bash
# Windows PowerShell
Get-WmiObject -Class Win32_BaseBoard | Select-Object SerialNumber

# Linux
dmidecode -s system-serial-number

# Mac
system_profiler SPHardwareDataType | grep 'Serial'
```

### Option 3: MAC Address Hash
```bash
# Windows
getmac /v

# Linux
ip addr show

# Mac
ifconfig | grep ether
```

**Recommendation**: Use combination of hostname + first MAC address hash for best balance of uniqueness and stability.

## Integration with Main System

### Backend (dental_clinic.py)
Already has these functions:
- `verify_offline_license_token(token, signing_key)` - Validates device_id matches
- `/api/license/offline-verify` - POST endpoint for token verification

### When User Activates on Device:
```
1. User receives: Serial + Offline License Token
2. Desktop/Mobile app calls: /api/license/activate
3. Backend:
   a. Detects device_id (computer name or hardware fingerprint)
   b. Stores device_id with activation
   c. Generates offline_license_token with device_id embedded
4. User's device stores: Offline License Token in localStorage/secure storage
5. Device can work offline using stored token
6. If token presented to different device_id:
   ├── Signature verification fails OR
   └── Device_id in payload doesn't match current device
   └── Activation rejected ✗

```

## Distribution Workflow

1. **Generate Serials** (External tool - this script)
   ```
   serial_generator.py → serials.csv
   ```

2. **Distribute to Clinic**
   - Email serial + offline token to clinic admin
   - Or: Provide serials.csv file
   - Or: QR code + serial number

3. **Clinic Admin on Device**
   - Input serial number in app
   - App calls `/api/license/activate` with serial + device_id
   - Server verifies serial matches device_id
   - Returns offline_license_token

4. **Device Stores Token**
   - Desktop: Saved to local database
   - Mobile: Saved to localStorage
   - Works offline indefinitely (until expiry)

## Security Features

✓ **Device Locking**: Each serial tied to one device_id
✓ **HMAC Signature**: Token can't be modified without signing key
✓ **Expiry Window**: Active license + 30-day grace period
✓ **Offline Verification**: No network needed after initial activation
✓ **External Generation**: Serials created separately from main system
✓ **Non-Transferable**: Same serial won't work on different device

## Examples

### Clinic with Multiple Devices
```bash
# Create devices.txt for "Smile Dental" clinic
echo "LAPTOP-DR-AHMED" > devices.txt
echo "LAPTOP-RECEPTIONIST" >> devices.txt
echo "IPAD-WAITING" >> devices.txt

# Generate all 3 serials
python serial_generator.py \
  --clinic "Smile Dental" \
  --code "SMD" \
  --devices-file devices.txt \
  --output smile_dental_serials.csv

# Output: 3 serials, each locked to its device
# DENTAL-SMD-LAPTO-00001 → LAPTOP-DR-AHMED
# DENTAL-SMD-LAPTO-00002 → LAPTOP-RECEPTIONIST
# DENTAL-SMD-IPAD--00003 → IPAD-WAITING

# Share CSV with clinic admin
# Each device gets its corresponding serial
```

### Two-Year Enterprise License
```bash
python serial_generator.py \
  --clinic "Major Hospital Network" \
  --code "HOSP" \
  --device "DESKTOP-MAIN-SERVER" \
  --plan "Enterprise" \
  --expiry 730
```

## Troubleshooting

### "Serial number already exists"
→ Delete the CSV and regenerate with different device IDs

### "Token verification fails on device"
→ Check that device_id in token matches current device's identifier
→ Use consistent device naming across generation and activation

### "Wrong clinic code length"
→ Use max 4 characters for clinic code (e.g., SMD not SMILE)

### "Can't load signing key from backend"
→ Normal - tool will use default signing key
→ For production, export backend key first:
  ```sql
  SELECT key FROM app_settings 
  WHERE key_name = 'license_signing_key'
  ```

## File Format Reference

### devices.txt (Input)
```
LAPTOP-DOCTOR-001
LAPTOP-RECEPTIONIST-001
DESKTOP-NURSE-LAB-001
IPAD-WAITING-ROOM-001
```

### serials.csv (Output)
```csv
Serial,Device ID,Clinic Name,Plan,Issued At,Expires At,Offline Token
DENTAL-SMD-LAPTO-00001,LAPTOP-DOCTOR-001,Smile Dental,Standard,...,eyJ...
DENTAL-SMD-LAPTO-00002,LAPTOP-RECEPTIONIST-001,Smile Dental,Standard,...,eyJ...
```

## Licensing & Security Notes

- ⚠️ **Keep signing keys secure** - If backend key is exposed, anyone can generate valid tokens
- 🔒 **Store generated serials securely** - CSVs contain offline tokens
- 🔑 **Backup signing key** - If lost, can't generate compatible serials
- 📝 **Log serial issuance** - Track which serial went to which clinic/device
- ♻️ **Revoke on device problems** - If device compromised, change the key in backend

## FAQ

**Q: Can I move a serial to another device?**
A: No - by design. Each serial is locked to one device_id. Use the generator to create a new serial for the new device.

**Q: What if device gets replaced?**
A: Generate new serial for new device. Old device's serial becomes invalid (expected behavior for security).

**Q: Can clinic users create their own serials?**
A: No - this tool is admin-only, kept external from main system for security.

**Q: How long are serials valid?**
A: Configurable (default 365 days) + 30-day grace period after expiry.

**Q: Can serials be extended?**
A: Generate new serial with later expiry date. Old serial stops working on grace period end.

---

**Created**: 2026-05-01
**Version**: 1.0
**Status**: Production Ready
