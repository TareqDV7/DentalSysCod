"""Vendor-side, LOOPBACK-ONLY GUI for minting Ed25519-signed serials.

Run on the vendor machine only:  python serial_admin.py
The private seed (backend_ed25519_key.json) is read server-side at mint time and
NEVER returned, logged, or rendered. Bound to 127.0.0.1; a before_request guard
rejects any non-loopback client.
"""
import base64
import binascii
import io
import csv
import json
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template_string

import serial_generator
from serial_admin_ui import INDEX_TEMPLATE

app = Flask(__name__)

KEY_FILE = os.environ.get(
    'CLINIC_VENDOR_KEY_FILE',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend_ed25519_key.json'),
)
_LOOPBACK = {'127.0.0.1', '::1', 'localhost'}

LEDGER_FILE_ENV = 'CLINIC_MINT_LEDGER_FILE'


# ── Local mint ledger ────────────────────────────────────────────────────────
# Every serial minted on this machine is logged to a small SQLite file (with its
# Activation Code) so the vendor always has a record of what was issued — even if
# they forget to download the CSV. Loopback-only console, so the token at rest is
# no more exposed than the signing key sitting next to it. Best-effort: a ledger
# write must never fail a mint.

def _ledger_path():
    """Path to the mint ledger. Defaults next to the signing key so it travels with
    the vendor console; override with CLINIC_MINT_LEDGER_FILE (used by tests)."""
    override = os.environ.get(LEDGER_FILE_ENV, '').strip()
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(KEY_FILE)), 'minted_serials.db')


def _ledger_conn():
    conn = sqlite3.connect(_ledger_path())
    conn.execute('''
        CREATE TABLE IF NOT EXISTS minted_serials (
            serial        TEXT PRIMARY KEY,
            clinic_name   TEXT,
            clinic_code   TEXT,
            device_id     TEXT,
            plan_name     TEXT,
            max_devices   INTEGER,
            issued_at     TEXT,
            expires_at    TEXT,
            offline_token TEXT,
            published     INTEGER NOT NULL DEFAULT 0,
            published_at  TEXT,
            cloud_url     TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    return conn


def _ledger_record(record, clinic_name='', clinic_code=''):
    """Persist one minted serial. Upsert by serial: refresh metadata/token but keep
    the original created_at and never downgrade a row that's already published."""
    serial = str(record.get('serial') or '').strip().upper()
    if not serial:
        return
    conn = _ledger_conn()
    try:
        conn.execute('''
            INSERT INTO minted_serials
                (serial, clinic_name, clinic_code, device_id, plan_name,
                 max_devices, issued_at, expires_at, offline_token)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(serial) DO UPDATE SET
                clinic_name   = excluded.clinic_name,
                clinic_code   = excluded.clinic_code,
                device_id     = excluded.device_id,
                plan_name     = excluded.plan_name,
                max_devices   = excluded.max_devices,
                issued_at     = excluded.issued_at,
                expires_at    = excluded.expires_at,
                offline_token = excluded.offline_token
        ''', (serial, clinic_name or record.get('clinic_name'),
              clinic_code or record.get('clinic_code'), record.get('device_id'),
              record.get('plan_name'), record.get('max_devices'),
              record.get('issued_at'), record.get('expires_at'),
              record.get('offline_token')))
        conn.commit()
    finally:
        conn.close()


def _ledger_mark_published(serials, cloud_url=''):
    serials = [str(s).strip().upper() for s in serials if str(s).strip()]
    if not serials:
        return
    conn = _ledger_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            'UPDATE minted_serials SET published = 1, published_at = ?, cloud_url = ? '
            'WHERE serial = ?', [(now, cloud_url, s) for s in serials])
        conn.commit()
    finally:
        conn.close()


def _ledger_all():
    conn = _ledger_conn()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT serial, clinic_name, clinic_code, device_id, plan_name, max_devices, '
            'issued_at, expires_at, offline_token, published, published_at, cloud_url, '
            'created_at FROM minted_serials ORDER BY created_at DESC, serial').fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _decode_token_payload(token):
    """Best-effort decode of a serial token's payload WITHOUT verifying the
    signature — only to read metadata (serial, clinic, expiry) for the ledger.
    The cloud still verifies the Ed25519 signature when the token is published."""
    try:
        payload_part = str(token).split('.', 1)[0]
        payload = json.loads(serial_generator._b64u_decode(payload_part).decode('utf-8'))
        return payload if isinstance(payload, dict) else None
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None


@app.before_request
def _loopback_only():
    if (request.remote_addr or '') not in _LOOPBACK:
        return jsonify({'error': 'Forbidden (loopback only)'}), 403
    return None


def _public_key_b64():
    """Derive the base64 public key from the stored seed, or '' if no key file."""
    if not os.path.exists(KEY_FILE):
        return ''
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    seed_b64 = serial_generator.load_private_seed(KEY_FILE)
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed_b64))
    raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode('ascii')


@app.route('/api/key/status')
def key_status():
    if not os.path.exists(KEY_FILE):
        return jsonify({'has_key': False, 'key_file': KEY_FILE})
    try:
        pub = _public_key_b64()
    except (ValueError, OSError, json.JSONDecodeError, binascii.Error):
        return jsonify({'has_key': False, 'key_file': KEY_FILE})
    return jsonify({'has_key': True, 'public_key': pub, 'key_file': KEY_FILE})


@app.route('/api/key/generate', methods=['POST'])
def key_generate():
    data = request.json or {}
    confirm = bool(data.get('confirm_overwrite'))
    if os.path.exists(KEY_FILE) and not confirm:
        return jsonify({'error': 'A signing key already exists. Overwriting it invalidates '
                                 'every serial already issued.', 'reason': 'exists'}), 409
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    with open(KEY_FILE, 'w', encoding='utf-8') as fh:
        json.dump({'alg': 'ed25519', 'private': priv_b64}, fh)
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    return jsonify({'public_key': pub_b64, 'key_file': KEY_FILE})


def _mint_records(data):
    """Return (records, error_tuple). error_tuple is (dict, status) or None."""
    if not os.path.exists(KEY_FILE):
        return None, ({'error': 'No signing key — generate one first', 'reason': 'no_key'}, 400)
    clinic_name = str(data.get('clinic_name') or '').strip()
    clinic_code = str(data.get('clinic_code') or '').strip()
    if not clinic_name:
        return None, ({'error': 'clinic_name is required'}, 400)
    if not clinic_code or len(clinic_code) > 4:
        return None, ({'error': 'clinic_code is required and must be at most 4 characters'}, 400)
    try:
        expiry_days = int(data.get('expiry_days', 365))
        max_devices = max(1, int(data.get('max_devices', 1)))
    except (TypeError, ValueError):
        return None, ({'error': 'expiry_days and max_devices must be numbers'}, 400)

    raw_devices = data.get('devices')
    if isinstance(raw_devices, str):
        devices = [d.strip() for d in raw_devices.splitlines() if d.strip()]
    elif isinstance(raw_devices, list):
        devices = [str(d).strip() for d in raw_devices if str(d).strip()]
    else:
        devices = []
    if not devices:
        devices = [f'CLINIC-{clinic_code.upper()}']

    seed = serial_generator.load_private_seed(KEY_FILE)
    records = []
    for idx, device_id in enumerate(devices, 1):
        serial = serial_generator.generate_device_serial_number(clinic_code, device_id, idx)
        lic = serial_generator.generate_license_token(
            serial=serial, clinic_name=clinic_name, device_id=device_id,
            plan_name=str(data.get('plan_name') or 'Standard'),
            max_devices=max_devices, expiry_days=expiry_days, private_seed_b64=seed)
        records.append({
            'serial': lic['serial'],
            'offline_token': lic['offline_token'],
            'device_id': device_id,
            'plan_name': lic['payload']['plan_name'],
            'max_devices': lic['payload']['max_devices'],
            'issued_at': lic['issued_at'],
            'expires_at': lic['expires_at'],
        })
    return records, None


@app.route('/api/mint', methods=['POST'])
def mint():
    data = request.json or {}
    records, err = _mint_records(data)
    if err is not None:
        return jsonify(err[0]), err[1]
    try:
        for r in records:
            _ledger_record(r, clinic_name=str(data.get('clinic_name') or ''),
                           clinic_code=str(data.get('clinic_code') or ''))
    except sqlite3.Error:
        pass  # the ledger is a convenience; never let it fail a mint
    if request.args.get('format') == 'csv':
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=['Serial', 'Device ID', 'Plan', 'Max Devices',
                                                 'Issued At', 'Expires At', 'Offline Token'])
        writer.writeheader()
        for r in records:
            writer.writerow({'Serial': r['serial'], 'Device ID': r['device_id'],
                             'Plan': r['plan_name'], 'Max Devices': r['max_devices'],
                             'Issued At': r['issued_at'], 'Expires At': r['expires_at'],
                             'Offline Token': r['offline_token']})
        code = str(data.get('clinic_code') or 'serials').upper()
        fname = f"serials_{code}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
        resp = app.response_class(buf.getvalue(), mimetype='text/csv')
        resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    return jsonify({'records': records})


_BAKED_CLOUD_URL = 'https://app.dentacare.tech'


def _upload_records_to_cloud(records, cloud_url, admin_token):
    """POST each minted serial's signed token to the cloud's admin register-serial
    endpoint so a fresh clinic can later activate by short serial alone. Returns a
    list of per-serial results. Pure stdlib HTTP; never raises (per-row errors are
    captured into the result list)."""
    base = str(cloud_url or '').strip().rstrip('/')
    results = []
    for r in records:
        serial = r.get('serial')
        token = r.get('offline_token')
        if not (base and token):
            results.append({'serial': serial, 'ok': False, 'error': 'missing url or token'})
            continue
        try:
            data = json.dumps({'serial_token': token}).encode('utf-8')
            req = urllib.request.Request(
                f'{base}/api/license/admin/register-serial', data=data, method='POST',
                headers={'Content-Type': 'application/json', 'X-Admin-Token': admin_token or ''})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode('utf-8') or '{}')
            results.append({'serial': serial, 'ok': bool(body.get('success')),
                            'already_existed': bool(body.get('already_existed'))})
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read().decode('utf-8') or '{}').get('error') or f'HTTP {exc.code}'
            except Exception:
                msg = f'HTTP {exc.code}'
            results.append({'serial': serial, 'ok': False, 'error': msg})
        except (urllib.error.URLError, OSError, ValueError) as exc:
            results.append({'serial': serial, 'ok': False, 'error': str(exc)})
    return results


@app.route('/api/upload-cloud', methods=['POST'])
def upload_cloud():
    """Publish minted serials to the cloud registry (admin-token gated on the cloud
    side). Loopback-only, like the rest of this console."""
    data = request.json or {}
    records = data.get('records')
    cloud_url = str(data.get('cloud_url') or '').strip()
    admin_token = str(data.get('admin_token') or '').strip()
    if not isinstance(records, list) or not records:
        return jsonify({'error': 'No minted serials to upload — mint first.'}), 400
    if not cloud_url:
        return jsonify({'error': 'cloud_url is required'}), 400
    if not admin_token:
        return jsonify({'error': 'admin_token is required'}), 400
    results = _upload_records_to_cloud(records, cloud_url, admin_token)
    ok = sum(1 for r in results if r.get('ok'))
    try:
        _ledger_mark_published([r['serial'] for r in results if r.get('ok') and r.get('serial')],
                               cloud_url)
    except sqlite3.Error:
        pass
    return jsonify({'results': results, 'ok_count': ok, 'total': len(results)})


@app.route('/api/history')
def history():
    """Local ledger of every serial minted on this machine — serial, clinic, plan,
    expiry, cloud-published flag, and the full Activation Code (for re-publish or
    air-gapped handoff). Loopback-only, like the rest of this console."""
    try:
        return jsonify({'records': _ledger_all()})
    except sqlite3.Error as exc:
        return jsonify({'error': f'Could not read the ledger: {exc}', 'records': []}), 500


@app.route('/api/publish-token', methods=['POST'])
def publish_token():
    """Publish an existing Activation Code (full offline token) to the cloud registry
    so an already-minted serial becomes activatable by short serial. Backfills the
    local ledger too — use this for serials minted before the ledger existed."""
    data = request.json or {}
    token = str(data.get('offline_token') or data.get('serial_token') or '').strip()
    cloud_url = str(data.get('cloud_url') or '').strip()
    admin_token = str(data.get('admin_token') or '').strip()
    if not token:
        return jsonify({'error': 'offline_token (the full Activation Code) is required'}), 400
    if not cloud_url:
        return jsonify({'error': 'cloud_url is required'}), 400
    if not admin_token:
        return jsonify({'error': 'admin_token is required'}), 400
    payload = _decode_token_payload(token) or {}
    serial = str(payload.get('serial') or '').strip().upper()
    record = {
        'serial': serial, 'offline_token': token,
        'clinic_name': payload.get('clinic_name'), 'plan_name': payload.get('plan_name'),
        'max_devices': payload.get('max_devices'), 'issued_at': payload.get('issued_at'),
        'expires_at': payload.get('expires_at'), 'device_id': payload.get('device_id'),
    }
    results = _upload_records_to_cloud([record], cloud_url, admin_token)
    res = results[0] if results else {'ok': False, 'error': 'no result'}
    if res.get('ok'):
        try:
            _ledger_record(record, clinic_name=str(payload.get('clinic_name') or ''))
            _ledger_mark_published([serial], cloud_url)
        except sqlite3.Error:
            pass
    return jsonify({'result': res, 'serial': serial or None})


@app.route('/api/cloud/serials', methods=['POST'])
def cloud_serials():
    """Proxy the cloud's read-only registry list (GET /api/license/admin/serials)
    with the admin token, so the vendor can see what's actually registered live.
    POST (not GET) so the admin token is never placed in a URL or browser history."""
    data = request.json or {}
    cloud_url = str(data.get('cloud_url') or '').strip().rstrip('/')
    admin_token = str(data.get('admin_token') or '').strip()
    if not cloud_url:
        return jsonify({'error': 'cloud_url is required'}), 400
    if not admin_token:
        return jsonify({'error': 'admin_token is required'}), 400
    try:
        req = urllib.request.Request(
            f'{cloud_url}/api/license/admin/serials', method='GET',
            headers={'X-Admin-Token': admin_token})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode('utf-8') or '{}')
        return jsonify(body)
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode('utf-8') or '{}').get('error') or f'HTTP {exc.code}'
        except (ValueError, OSError):
            msg = f'HTTP {exc.code}'
        return jsonify({'error': msg}), (exc.code if exc.code in (401, 404) else 502)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return jsonify({'error': f'Could not reach the cloud node: {exc}'}), 502



@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('SERIAL_ADMIN_PORT', '8787')))
