#!/usr/bin/env python3
"""
Serial License Generator - External Standalone Tool
Generates device-locked activation serials for Dental Clinic app
Each serial is tied to a specific device (hardware-locked)
"""

import os
import sys
import json
import base64
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def generate_keypair() -> tuple[str, str]:
    """Return (private_seed_b64, public_key_b64) for a fresh Ed25519 keypair.
    The private seed is 32 raw bytes, base64 (std) encoded.
    Note: keys are standard base64; the token wire format (from sign_serial_token) uses base64url."""
    priv = Ed25519PrivateKey.generate()
    seed = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return base64.b64encode(seed).decode(), base64.b64encode(pub).decode()


def sign_serial_token(payload: dict, private_seed_b64: str) -> str:
    """Return 'base64url(payload_json).base64url(ed25519_sig)'."""
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_seed_b64))
    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    sig = priv.sign(payload_json)
    return f'{_b64u(payload_json)}.{_b64u(sig)}'


def verify_serial_token(token: str, public_key_b64: str) -> tuple[bool, dict | None]:
    """Return (ok: bool, payload: dict|None). Verifies the Ed25519 signature."""
    try:
        payload_part, sig_part = str(token).split('.', 1)
        payload_bytes = _b64u_decode(payload_part)
        sig = _b64u_decode(sig_part)
    except (ValueError, base64.binascii.Error):
        return False, None
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        pub.verify(sig, payload_bytes)
        payload = json.loads(payload_bytes.decode('utf-8'))
        if not isinstance(payload, dict):
            return False, None
        return True, payload
    except (InvalidSignature, ValueError, UnicodeDecodeError):
        return False, None


# Constants
SERIAL_PREFIX = "DENTAL"
SERIAL_SEPARATOR = "-"

def generate_device_serial_number(clinic_code: str, device_id: str, counter: int = 1) -> str:
    """
    Generate a human-readable serial number format:
    DENTAL-CLINIC-DEVICE-XXXXXXXX
    
    Args:
        clinic_code: Short clinic identifier (max 4 chars)
        device_id: Device identifier/hash
        counter: Sequential counter for multiple serials per device
    
    Returns:
        Formatted serial string like: DENTAL-CLINIC-A1B2C-00001
    """
    # Create clinic code (max 4 chars, alphanumeric, uppercase)
    clinic_part = clinic_code[:4].upper().replace(" ", "")
    
    # Create device part (take first 5 chars of device hash)
    device_part = device_id[:5].upper()
    
    # Create counter part (padded to 5 digits)
    counter_part = f"{counter:05d}"
    
    serial = f"{SERIAL_PREFIX}{SERIAL_SEPARATOR}{clinic_part}{SERIAL_SEPARATOR}{device_part}{SERIAL_SEPARATOR}{counter_part}"
    return serial


def generate_license_token(
    serial: str,
    clinic_name: str,
    device_id: str,
    plan_name: str = "Standard",
    max_devices: int = 1,
    expiry_days: int = 365,
    private_seed_b64: str = None,
) -> dict:
    """
    Generate a vendor-signed (Ed25519) v2 license token.

    Args:
        serial: Serial number
        clinic_name: Clinic name
        device_id: Device identifier (informational; the cloud authority caps
            devices via per-device fingerprints, not this field)
        plan_name: Plan type (Standard, Premium, etc.)
        max_devices: Maximum devices the cloud authority will admit for this serial
        expiry_days: Days until expiry
        private_seed_b64: base64 Ed25519 private seed (from load_private_seed /
            generate_keypair). REQUIRED — there is NO demo-key fallback.

    Returns:
        Dictionary with token and metadata
    """
    if not private_seed_b64:
        raise ValueError('private_seed_b64 is required (no demo-key fallback)')

    now_utc = datetime.now(timezone.utc)
    issued_at = now_utc.replace(tzinfo=None).isoformat() + "Z"
    expires_at = (now_utc + timedelta(days=expiry_days)).replace(tzinfo=None).isoformat() + "Z"
    grace_until = (now_utc + timedelta(days=expiry_days + 30)).replace(tzinfo=None).isoformat() + "Z"

    # v2 payload — the shape the cloud authority's /api/license/validate reads.
    payload = {
        "v": 2,
        "serial": serial,
        "clinic_name": clinic_name,
        "plan_name": plan_name,
        "device_id": device_id,
        "max_devices": max_devices,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "grace_until": grace_until,
    }

    offline_token = sign_serial_token(payload, private_seed_b64)

    return {
        "serial": serial,
        "offline_token": offline_token,
        "payload": payload,
        "issued_at": issued_at,
        "expires_at": expires_at
    }


def load_private_seed(key_file: str) -> str:
    """Return the base64 Ed25519 private seed from a key file. Fails loudly if the
    file is missing or malformed — there is NO demo-key fallback."""
    if not key_file or not os.path.exists(key_file):
        raise FileNotFoundError(f'Signing key file not found: {key_file}')
    with open(key_file, 'r') as f:
        data = json.load(f)
    seed = str(data.get('private') or '').strip()
    if not seed:
        raise ValueError('Key file has no "private" seed')
    return seed


def create_serial_batch(
    clinic_name: str,
    clinic_code: str,
    devices: list,
    plan_name: str = "Standard",
    expiry_days: int = 365,
    output_file: str = None,
    signing_key_file: str = None
) -> list:
    """
    Create a batch of serials for multiple devices

    Args:
        clinic_name: Clinic name
        clinic_code: Clinic code for serial
        devices: List of device identifiers
        plan_name: License plan
        expiry_days: Expiry duration
        output_file: Optional CSV output file
        signing_key_file: Optional signing key file from backend

    Returns:
        List of generated license records
    """
    private_seed_b64 = load_private_seed(signing_key_file)

    licenses = []

    for idx, device_id in enumerate(devices, 1):
        serial = generate_device_serial_number(clinic_code, device_id, idx)
        license_data = generate_license_token(
            serial=serial,
            clinic_name=clinic_name,
            device_id=device_id,
            plan_name=plan_name,
            max_devices=1,  # Device-locked
            expiry_days=expiry_days,
            private_seed_b64=private_seed_b64,
        )
        licenses.append(license_data)
        
        print(f"✓ Generated serial {idx}/{len(devices)}: {serial}")
    
    # Export to CSV if requested
    if output_file:
        import csv
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'Serial', 'Device ID', 'Clinic Name', 'Plan', 
                    'Issued At', 'Expires At', 'Offline Token'
                ])
                writer.writeheader()
                
                for lic in licenses:
                    writer.writerow({
                        'Serial': lic['serial'],
                        'Device ID': lic['payload']['device_id'],
                        'Clinic Name': lic['payload']['clinic_name'],
                        'Plan': lic['payload']['plan_name'],
                        'Issued At': lic['issued_at'],
                        'Expires At': lic['expires_at'],
                        'Offline Token': lic['offline_token']
                    })
            print(f"\n✓ Exported {len(licenses)} serials to: {output_file}")
        except Exception as e:
            print(f"\n✗ Error exporting to CSV: {e}")
    
    return licenses


def main():
    # The pretty-print below uses ✓/✗ glyphs; a stock Windows console is cp1252
    # and would raise UnicodeEncodeError on them. Make the streams tolerant.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass

    # Keypair generation is a standalone subcommand — it doesn't take the
    # --clinic/--code args the rest of the CLI requires, so handle it first.
    if len(sys.argv) >= 2 and sys.argv[1] == '--genkey':
        priv_b64, pub_b64 = generate_keypair()
        out = sys.argv[2] if len(sys.argv) >= 3 else 'backend_ed25519_key.json'
        with open(out, 'w') as f:
            json.dump({'alg': 'ed25519', 'private': priv_b64}, f)
        print(f'Private seed written to {out} (KEEP SAFE, gitignored).')
        print(f'Public key (set CLINIC_SERIAL_PUBLIC_KEY on the cloud):\n{pub_b64}')
        return 0

    parser = argparse.ArgumentParser(
        description='Generate device-locked activation serials for Dental Clinic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # One-time: generate the vendor Ed25519 keypair
  python serial_generator.py --genkey                 # → backend_ed25519_key.json
  #   then set CLINIC_SERIAL_PUBLIC_KEY (printed above) on the cloud node

  # Generate single serial (signing key required — no demo-key fallback)
  python serial_generator.py --clinic "Smile Dental" --code "SMD" \\
    --device "LAPTOP-ABC123" --key-file backend_ed25519_key.json

  # Generate batch from file
  python serial_generator.py --clinic "Smile Dental" --code "SMD" \\
    --devices-file devices.txt --output serials.csv --key-file backend_ed25519_key.json

  # Generate with custom expiry
  python serial_generator.py --clinic "Smile Dental" --code "SMD" \\
    --device "DEVICE-ID" --expiry 730 --key-file backend_ed25519_key.json
        '''
    )

    parser.add_argument('--clinic', required=True, help='Clinic name')
    parser.add_argument('--code', required=True, help='Clinic code (max 4 chars) for serial')
    parser.add_argument('--device', help='Single device ID to generate serial for')
    parser.add_argument('--devices-file', help='File with list of device IDs (one per line)')
    parser.add_argument('--plan', default='Standard', help='License plan (default: Standard)')
    parser.add_argument('--expiry', type=int, default=365, help='Days until expiry (default: 365)')
    parser.add_argument('--output', help='Output CSV file for batch generation')
    parser.add_argument('--key-file', help='Vendor Ed25519 signing key file (backend_ed25519_key.json from --genkey)')
    parser.add_argument('--json', action='store_true', help='Output as JSON instead of CSV')

    args = parser.parse_args()

    # Validate inputs
    if not args.device and not args.devices_file:
        parser.error('Must provide either --device or --devices-file')

    if args.code and len(args.code) > 4:
        parser.error('Clinic code must be max 4 characters')

    # The signing key is mandatory now — load it up front so a missing/bad key
    # fails fast with a clear hint instead of mid-batch.
    try:
        private_seed_b64 = load_private_seed(args.key_file)
    except (FileNotFoundError, ValueError) as e:
        parser.error(f'{e}. Generate one first: python serial_generator.py --genkey')

    print(f"\n{'='*60}")
    print(f"   DENTAL CLINIC - SERIAL LICENSE GENERATOR")
    print(f"{'='*60}\n")
    
    # Single device
    if args.device:
        print(f"Generating serial for:")
        print(f"  Clinic: {args.clinic}")
        print(f"  Device: {args.device}")
        print(f"  Plan: {args.plan}")
        print(f"  Expiry: {args.expiry} days\n")
        
        serial = generate_device_serial_number(args.code, args.device)
        license_data = generate_license_token(
            serial=serial,
            clinic_name=args.clinic,
            device_id=args.device,
            plan_name=args.plan,
            expiry_days=args.expiry,
            private_seed_b64=private_seed_b64,
        )
        
        print(f"✓ SERIAL NUMBER: {serial}\n")
        print(f"Offline License Token (copy to device):")
        print(f"{license_data['offline_token']}\n")
        print(f"Issued: {license_data['issued_at']}")
        print(f"Expires: {license_data['expires_at']}\n")
    
    # Batch from file
    elif args.devices_file:
        try:
            with open(args.devices_file, 'r') as f:
                devices = [line.strip() for line in f if line.strip()]
            
            if not devices:
                print(f"✗ No devices found in {args.devices_file}")
                return 1
            
            print(f"Generating {len(devices)} serials from {args.devices_file}:")
            print(f"  Clinic: {args.clinic}")
            print(f"  Plan: {args.plan}")
            print(f"  Expiry: {args.expiry} days\n")
            
            output_file = args.output or f"serials_{args.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            licenses = create_serial_batch(
                clinic_name=args.clinic,
                clinic_code=args.code,
                devices=devices,
                plan_name=args.plan,
                expiry_days=args.expiry,
                output_file=output_file if not args.json else None,
                signing_key_file=args.key_file
            )
            
            if args.json:
                json_file = args.output or f"serials_{args.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(licenses, f, indent=2)
                print(f"✓ Exported {len(licenses)} serials to: {json_file}")
            
            print(f"\n{'='*60}")
            print(f"Generated {len(devices)} device-locked serials ✓")
            print(f"Each serial is locked to its device and cannot be transferred")
            print(f"{'='*60}\n")
            
        except FileNotFoundError:
            print(f"✗ File not found: {args.devices_file}")
            return 1
        except Exception as e:
            print(f"✗ Error: {e}")
            return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
