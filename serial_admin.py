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


INDEX_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Serial Minter — Vendor Console</title>
<style>
  :root { --bg:#0f1722; --panel:#16212e; --line:#243446; --ink:#e7eef6; --muted:#8aa0b4;
          --accent:#3ddc97; --warn:#ff6b6b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif; }
  header { padding:18px 22px; border-bottom:1px solid var(--line); display:flex;
           align-items:baseline; gap:12px; }
  header h1 { font-size:1.1rem; margin:0; letter-spacing:.3px; }
  header .tag { color:var(--muted); font-size:.85rem; }
  main { max-width:980px; margin:0 auto; padding:22px; display:grid; gap:18px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px; }
  .panel h2 { margin:0 0 12px; font-size:.95rem; color:var(--muted); text-transform:uppercase;
              letter-spacing:.6px; }
  label { display:block; font-size:.82rem; color:var(--muted); margin:10px 0 4px; }
  input, select, textarea { width:100%; background:#0c141d; color:var(--ink);
    border:1px solid var(--line); border-radius:8px; padding:9px 10px; font:inherit; }
  textarea { min-height:84px; font-family:ui-monospace,monospace; }
  .grid { display:grid; gap:12px; }
  @media (min-width:720px){ .grid-2 { grid-template-columns:1fr 1fr; } }
  button { background:var(--accent); color:#06281b; border:0; border-radius:8px;
    padding:10px 16px; font:inherit; font-weight:600; cursor:pointer; margin-top:14px; }
  button.ghost { background:transparent; color:var(--ink); border:1px solid var(--line); }
  .pub { font-family:ui-monospace,monospace; word-break:break-all; color:var(--accent); }
  table { width:100%; border-collapse:collapse; margin-top:8px; display:block; overflow-x:auto; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); font-size:.85rem; }
  .tok { font-family:ui-monospace,monospace; max-width:260px; overflow:hidden;
         text-overflow:ellipsis; white-space:nowrap; }
  .warn { color:var(--warn); font-size:.82rem; margin-top:8px; }
  .muted { color:var(--muted); }
</style></head>
<body>
<header><h1>Serial Minter</h1><span class="tag">vendor console · loopback only</span></header>
<main>
  <section class="panel" id="key-panel">
    <h2>Signing key</h2>
    <div id="key-status" class="muted">Checking…</div>
    <div id="key-pub" class="pub" style="display:none"></div>
    <button class="ghost" id="key-gen" onclick="generateKey()">Generate keypair</button>
    <div class="warn">The private seed never leaves this machine. Only the public key is shown.</div>
  </section>
  <section class="panel">
    <h2>Mint serials</h2>
    <form id="mint-form" onsubmit="return false;">
      <div class="grid grid-2">
        <div><label>Clinic name</label><input id="m-name" placeholder="Smile Dental"></div>
        <div><label>Clinic code (≤4)</label><input id="m-code" maxlength="4" placeholder="SMD"></div>
        <div><label>Plan</label>
          <select id="m-plan"><option>Standard</option><option>Premium</option><option>Enterprise</option></select></div>
        <div><label>Expiry (days)</label><input id="m-expiry" type="number" value="365"></div>
        <div><label>Max devices</label><input id="m-max" type="number" value="3"></div>
      </div>
      <label>Device IDs (one per line — blank = one clinic-level serial)</label>
      <textarea id="m-devices" placeholder="LAPTOP-01&#10;PHONE-02"></textarea>
      <button onclick="mint()">Mint</button>
    </form>
    <div class="warn">Minted tokens are secrets — don't commit the CSV/JSON you download.</div>
  </section>
  <section class="panel" id="results-panel" style="display:none">
    <h2>Results</h2>
    <div>
      <button class="ghost" onclick="downloadJson()">Download JSON</button>
      <button class="ghost" onclick="downloadCsv()">Download CSV</button>
    </div>
    <p style="font-size:.82rem;color:#8aa0b4;margin:8px 0 4px">Give the clinic owner the <b style="color:#3ddc97">Serial Number</b> only — they type it in the app and it activates online. (The full Activation Code is the offline fallback.)</p>
    <table id="results"><thead><tr><th>Serial Number</th><th>Expires</th><th>Activation Code</th><th></th></tr></thead><tbody></tbody></table>
    <div style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px;">
      <h2 style="margin-bottom:8px;">Publish to cloud (enable short-serial activation)</h2>
      <p class="muted" style="font-size:.82rem;margin:0 0 8px;">Uploads these serials to the cloud registry so the clinic can activate by typing the short serial only. Needs the cloud admin token.</p>
      <div class="grid grid-2">
        <div><label>Cloud URL</label><input id="c-url" value="https://app.dentacare.tech"></div>
        <div><label>Admin token (X-Admin-Token)</label><input id="c-token" type="password" placeholder="CLINIC_ADMIN_API_TOKEN"></div>
      </div>
      <button onclick="uploadCloud()">Upload minted serials to cloud</button>
      <div id="c-result" class="muted" style="margin-top:8px;font-size:.85rem;"></div>
    </div>
  </section>
  <section class="panel" id="history-panel">
    <h2>Serial history — this machine</h2>
    <p class="muted" style="font-size:.82rem;margin:0 0 8px;">Every serial minted here is logged locally (with its Activation Code) so you never lose track. Saved in <span class="pub" style="font-size:.8rem;">minted_serials.db</span> next to your signing key.</p>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <button class="ghost" style="margin-top:0" onclick="loadHistory()">Refresh</button>
      <button class="ghost" style="margin-top:0" onclick="exportHistory()">Export all (CSV)</button>
      <span id="hist-count" class="muted" style="font-size:.82rem;"></span>
    </div>
    <table id="history"><thead><tr><th>Serial Number</th><th>Clinic</th><th>Plan</th><th>Expires</th><th>Cloud</th><th></th></tr></thead><tbody></tbody></table>
  </section>
  <section class="panel" id="publish-panel">
    <h2>Publish an existing serial to the cloud</h2>
    <p class="muted" style="font-size:.82rem;margin:0 0 8px;">Paste a serial's full Activation Code to register it on the cloud so the clinic can activate by typing the short serial. Use this for serials minted before this machine kept a history. Needs the cloud admin token.</p>
    <div class="grid grid-2">
      <div><label>Cloud URL</label><input id="cloud-url" value="https://app.dentacare.tech"></div>
      <div><label>Admin token (X-Admin-Token)</label><input id="cloud-admin" type="password" placeholder="CLINIC_ADMIN_API_TOKEN"></div>
    </div>
    <label>Activation Code (full offline token)</label>
    <textarea id="pub-token" placeholder="eyJ..."></textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button onclick="publishToken()">Publish to cloud</button>
      <button class="ghost" onclick="viewCloud()">View cloud registry</button>
    </div>
    <div id="pub-result" class="muted" style="margin-top:8px;font-size:.85rem;"></div>
    <table id="cloud-reg" style="display:none;margin-top:10px;"><thead><tr><th>Serial Number</th><th>Clinic</th><th>Status</th><th>Devices</th><th>Expires</th></tr></thead><tbody></tbody></table>
  </section>
</main>
<script>
  let lastRecords = [];
  let histRows = [];
  function fmtDate(s) { return s ? String(s).slice(0, 10) : ''; }
  function _cloudConn() {
    return { cloud_url: document.getElementById('cloud-url').value.trim(),
             admin_token: document.getElementById('cloud-admin').value.trim() };
  }
  async function loadHistory() {
    let body;
    try { body = await fetch('/api/history').then(r => r.json()); }
    catch (e) { document.getElementById('hist-count').textContent = 'Could not load history.'; return; }
    histRows = (body && body.records) || [];
    const tb = document.querySelector('#history tbody');
    tb.innerHTML = '';
    for (const r of histRows) {
      const tr = document.createElement('tr');
      const cells = [r.serial, r.clinic_name || '', r.plan_name || '', fmtDate(r.expires_at), r.published ? 'published' : 'local only'];
      for (let i = 0; i < cells.length; i++) {
        const td = document.createElement('td'); td.textContent = cells[i];
        if (i === 0) { td.style.fontFamily = 'ui-monospace,monospace'; td.style.fontWeight = '600'; }
        if (i === 4 && !r.published) td.style.color = 'var(--warn)';
        tr.appendChild(td);
      }
      const act = document.createElement('td');
      const copy = document.createElement('button'); copy.className = 'ghost'; copy.textContent = 'Copy Code';
      copy.style.cssText = 'padding:5px 10px;font-size:.8rem;margin:0';
      copy.onclick = () => { navigator.clipboard.writeText(r.offline_token || '').then(() => { copy.textContent = 'Copied!'; setTimeout(() => copy.textContent = 'Copy Code', 2000); }); };
      act.appendChild(copy);
      if (!r.published) {
        const pb = document.createElement('button'); pb.className = 'ghost'; pb.textContent = 'Publish';
        pb.style.cssText = 'padding:5px 10px;font-size:.8rem;margin:0 0 0 6px';
        pb.onclick = () => publishExisting(r.offline_token, pb); act.appendChild(pb);
      }
      tr.appendChild(act); tb.appendChild(tr);
    }
    document.getElementById('hist-count').textContent = histRows.length + ' serial(s) logged.';
  }
  async function publishExisting(token, btn) {
    const conn = _cloudConn();
    if (!conn.admin_token) { alert('Enter the cloud admin token (in the panel below) first.'); return; }
    if (btn) { btn.disabled = true; btn.textContent = 'Publishing…'; }
    try {
      const res = await fetch('/api/publish-token', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ offline_token: token }, conn)) });
      const body = await res.json();
      if (!res.ok || !(body.result && body.result.ok)) { alert(body.error || (body.result && body.result.error) || 'Publish failed.'); }
    } catch (e) { alert('Network error: ' + e); }
    if (btn) { btn.disabled = false; btn.textContent = 'Publish'; }
    loadHistory();
  }
  async function publishToken() {
    const token = document.getElementById('pub-token').value.trim();
    const out = document.getElementById('pub-result');
    if (!token) { out.textContent = 'Paste an Activation Code first.'; return; }
    const conn = _cloudConn();
    if (!conn.admin_token) { out.textContent = 'Enter the cloud admin token first.'; return; }
    out.textContent = 'Publishing…';
    try {
      const res = await fetch('/api/publish-token', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ offline_token: token }, conn)) });
      const body = await res.json();
      if (!res.ok || !(body.result && body.result.ok)) { out.textContent = body.error || (body.result && body.result.error) || 'Publish failed.'; return; }
      out.textContent = 'Published ' + (body.serial || 'serial') + ' to the cloud. The clinic can now activate by short serial.';
      document.getElementById('pub-token').value = '';
      loadHistory();
    } catch (e) { out.textContent = 'Network error: ' + e; }
  }
  async function viewCloud() {
    const conn = _cloudConn();
    const out = document.getElementById('pub-result');
    if (!conn.admin_token) { out.textContent = 'Enter the cloud admin token first.'; return; }
    out.textContent = 'Loading cloud registry…';
    try {
      const res = await fetch('/api/cloud/serials', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(conn) });
      const body = await res.json();
      if (!res.ok) { out.textContent = body.error || 'Could not load registry.'; return; }
      const rows = body.serials || [];
      const tbl = document.getElementById('cloud-reg'); const tb = tbl.querySelector('tbody'); tb.innerHTML = '';
      for (const r of rows) {
        const tr = document.createElement('tr');
        const cells = [r.serial, r.clinic_name || '', r.status || '', (r.used_devices + '/' + r.max_devices), fmtDate(r.expires_at)];
        for (let i = 0; i < cells.length; i++) { const td = document.createElement('td'); td.textContent = cells[i]; if (i === 0) { td.style.fontFamily = 'ui-monospace,monospace'; } tr.appendChild(td); }
        tb.appendChild(tr);
      }
      tbl.style.display = rows.length ? '' : 'none';
      out.textContent = rows.length + ' serial(s) in the cloud registry.';
    } catch (e) { out.textContent = 'Network error: ' + e; }
  }
  function exportHistory() {
    if (!histRows.length) { alert('No history yet — mint a serial first.'); return; }
    const head = ['Serial', 'Clinic', 'Code', 'Device ID', 'Plan', 'Max Devices', 'Issued At', 'Expires At', 'Published', 'Offline Token'];
    const rows = histRows.map(r => [r.serial, r.clinic_name, r.clinic_code, r.device_id, r.plan_name, r.max_devices, r.issued_at, r.expires_at, (r.published ? 'yes' : 'no'), r.offline_token]);
    const csv = [head].concat(rows).map(cols => cols.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    _download('minted_serials_history.csv', 'text/csv', csv);
  }
  async function refreshKey() {
    const st = await fetch('/api/key/status').then(r => r.json());
    const el = document.getElementById('key-status');
    const pub = document.getElementById('key-pub');
    const gen = document.getElementById('key-gen');
    if (st.has_key) {
      el.textContent = 'Key loaded (' + (st.key_file || '') + '). Public key:';
      pub.style.display = ''; pub.textContent = st.public_key || '';
      gen.textContent = 'Rotate keypair';
    } else {
      el.textContent = 'No signing key yet — generate one to start minting.';
      pub.style.display = 'none'; gen.textContent = 'Generate keypair';
    }
  }
  async function generateKey() {
    const exists = document.getElementById('key-pub').style.display !== 'none';
    if (exists && !confirm('Rotating the key invalidates every serial already issued. Continue?')) return;
    const res = await fetch('/api/key/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm_overwrite: exists })
    });
    const body = await res.json();
    if (!res.ok) { alert(body.error || 'Could not generate a key.'); return; }
    await refreshKey();
  }
  function collectBody() {
    return {
      clinic_name: document.getElementById('m-name').value.trim(),
      clinic_code: document.getElementById('m-code').value.trim(),
      plan_name: document.getElementById('m-plan').value,
      expiry_days: parseInt(document.getElementById('m-expiry').value || '365', 10),
      max_devices: parseInt(document.getElementById('m-max').value || '1', 10),
      devices: document.getElementById('m-devices').value
    };
  }
  async function mint() {
    const res = await fetch('/api/mint', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectBody())
    });
    const body = await res.json();
    if (!res.ok) { alert(body.error || 'Mint failed.'); return; }
    lastRecords = body.records || [];
    const tb = document.querySelector('#results tbody');
    tb.innerHTML = '';
    for (const r of lastRecords) {
      const tr = document.createElement('tr');
      const sc = document.createElement('td'); sc.textContent = r.serial; sc.style.fontFamily = 'ui-monospace,monospace'; sc.style.fontWeight = '600';
      const ex = document.createElement('td'); ex.textContent = r.expires_at;
      const tok = document.createElement('td'); tok.className = 'tok'; tok.title = r.offline_token; tok.textContent = r.offline_token;
      const cp = document.createElement('td');
      const btn = document.createElement('button'); btn.className = 'ghost'; btn.textContent = 'Copy Code';
      btn.style.cssText = 'padding:5px 10px;font-size:.8rem;margin:0';
      btn.onclick = () => { navigator.clipboard.writeText(r.offline_token).then(() => { btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = 'Copy Code', 2000); }); };
      cp.appendChild(btn);
      tr.appendChild(sc); tr.appendChild(ex); tr.appendChild(tok); tr.appendChild(cp);
      tb.appendChild(tr);
    }
    document.getElementById('results-panel').style.display = lastRecords.length ? '' : 'none';
    loadHistory();
  }
  function _download(name, type, text) {
    const blob = new Blob([text], { type: type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    URL.revokeObjectURL(a.href);
  }
  async function uploadCloud() {
    if (!lastRecords.length) { alert('Mint serials first.'); return; }
    const out = document.getElementById('c-result');
    out.textContent = 'Uploading…';
    try {
      const res = await fetch('/api/upload-cloud', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: lastRecords,
          cloud_url: document.getElementById('c-url').value.trim(),
          admin_token: document.getElementById('c-token').value.trim()
        })
      });
      const body = await res.json();
      if (!res.ok) { out.textContent = body.error || 'Upload failed.'; return; }
      const fails = (body.results || []).filter(r => !r.ok);
      out.textContent = 'Uploaded ' + body.ok_count + ' / ' + body.total + ' serial(s).'
        + (fails.length ? ' Failed: ' + fails.map(f => f.serial + ' (' + (f.error || 'error') + ')').join(', ') : ' All good.');
      loadHistory();
    } catch (e) { out.textContent = 'Network error: ' + e; }
  }
  function downloadJson() { _download('serials.json', 'application/json', JSON.stringify(lastRecords, null, 2)); }
  function downloadCsv() {
    const head = ['Serial', 'Device ID', 'Plan', 'Max Devices', 'Issued At', 'Expires At', 'Offline Token'];
    const rows = lastRecords.map(r => [r.serial, r.device_id, r.plan_name, r.max_devices, r.issued_at, r.expires_at, r.offline_token]);
    const csv = [head].concat(rows).map(cols => cols.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    _download('serials.csv', 'text/csv', csv);
  }
  document.addEventListener('DOMContentLoaded', () => { refreshKey(); loadHistory(); });
</script>
</body></html>'''


@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('SERIAL_ADMIN_PORT', '8787')))
