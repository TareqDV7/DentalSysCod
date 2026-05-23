# Serial Generator - Quick Reference Card

**Print this or save to device for quick command lookup**

---

## 🚀 Quick Start

### Single Device Serial
```bash
python serial_generator.py \
  --clinic "Clinic Name" \
  --code "CODE" \
  --device "DEVICE-ID"
```

### Batch from File
```bash
python serial_generator.py \
  --clinic "Clinic Name" \
  --code "CODE" \
  --devices-file devices.txt \
  --output serials.csv
```

---

## 📋 All Command Options

```
--clinic NAME              Clinic name (required)
--code CODE                Clinic code, max 4 chars (required)
--device ID                Single device ID to generate
--devices-file FILE        File with list of device IDs
--plan NAME                License plan (default: Standard)
--expiry DAYS              Days until expiry (default: 365)
--output FILE              Output CSV file
--key-file FILE            Backend signing key file (optional)
--json                     Output as JSON instead of CSV
--help                     Show help message
```

---

## 💡 Common Examples

### Example 1: Single Laptop (1 Year)
```bash
python serial_generator.py \
  --clinic "Smile Dental" \
  --code "SMD" \
  --device "LAPTOP-DOCTOR-AHMED"
```

**Output:**
```
Serial: DENTAL-SMD-LAPTO-00001
Token: eyJ...
```

---

### Example 2: Multiple Devices in Clinic (Batch)

**Step 1: Create devices.txt**
```
LAPTOP-DOCTOR-AHMED
LAPTOP-RECEPTIONIST-SARA
DESKTOP-LAB
IPAD-WAITING-ROOM
```

**Step 2: Generate All Serials**
```bash
python serial_generator.py \
  --clinic "Smile Dental" \
  --code "SMD" \
  --devices-file devices.txt \
  --output smile_serials.csv
```

**Output:** smile_serials.csv with 4 rows
```csv
Serial,Device ID,Clinic Name,...
DENTAL-SMD-LAPTO-00001,LAPTOP-DOCTOR-AHMED,...
DENTAL-SMD-LAPTO-00002,LAPTOP-RECEPTIONIST-SARA,...
DENTAL-SMD-DESKT-00003,DESKTOP-LAB,...
DENTAL-SMD-IPAD--00004,IPAD-WAITING-ROOM,...
```

---

### Example 3: 2-Year Enterprise License
```bash
python serial_generator.py \
  --clinic "Big Hospital" \
  --code "BIG" \
  --device "DESKTOP-SERVER-001" \
  --expiry 730 \
  --plan "Enterprise"
```

---

### Example 4: Using Backend Signing Key
```bash
python serial_generator.py \
  --clinic "Smile Dental" \
  --code "SMD" \
  --device "LAPTOP-001" \
  --key-file backend_key.json
```

---

## 🔍 Getting Device ID

### Windows
```bash
# Get computer name
echo %COMPUTERNAME%
```

### Linux / Mac
```bash
# Get hostname
hostname
```

---

## 📊 CSV File Format

After generation, CSV has these columns:
```
Serial          → DENTAL-SMD-LAPTO-00001
Device ID       → LAPTOP-DOCTOR-001
Clinic Name     → Smile Dental
Plan            → Standard
Issued At       → 2026-05-01T13:05:30Z
Expires At      → 2027-05-01T13:05:30Z
Offline Token   → eyJ...
```

---

## ✅ Validation

All generated tokens are valid and include:
- ✓ Device locking (won't work on other devices)
- ✓ HMAC signature (tamper-proof)
- ✓ Expiry dates (1 year default + 30-day grace)
- ✓ Offline capability (verifiable without network)

---

## 🚨 Troubleshooting

| Problem | Solution |
|---------|----------|
| Command not found | Make sure you're in clinic directory |
| "clinic code must be max 4" | Use only 4 chars: SMD not SMILE |
| "No devices found" | Check devices.txt exists and has content |
| Python error | Make sure .venv is activated |
| File permission denied | Run as administrator or check file perms |

---

## 🔐 Security Notes

- Each serial locked to ONE device (non-transferable)
- Tokens are HMAC-signed (can't be forged)
- Keep backend signing key secure
- Don't share CSV files publicly
- Document which serial went to which clinic/device

---

## 📞 Support

- See `SERIAL_GENERATOR_README.md` for detailed guide
- See `LICENSE_INTEGRATION_GUIDE.md` for backend integration
- See `SECURITY_ARCHITECTURE.md` for security details

---

**Created**: 2026-05-01 | **Version**: 1.0
