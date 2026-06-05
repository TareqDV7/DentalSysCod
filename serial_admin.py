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
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template_string

import serial_generator

app = Flask(__name__)

KEY_FILE = os.environ.get('CLINIC_VENDOR_KEY_FILE', 'backend_ed25519_key.json')
_LOOPBACK = {'127.0.0.1', '::1', 'localhost'}


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
    <table id="results"><thead><tr><th>Serial</th><th>Expires</th><th>Token</th></tr></thead><tbody></tbody></table>
  </section>
</main>
<script>
  let lastRecords = [];
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
      const tok = document.createElement('td'); tok.className = 'tok'; tok.title = r.offline_token;
      tok.textContent = r.offline_token;
      const sc = document.createElement('td'); sc.textContent = r.serial;
      const ex = document.createElement('td'); ex.textContent = r.expires_at;
      tr.appendChild(sc); tr.appendChild(ex); tr.appendChild(tok);
      tb.appendChild(tr);
    }
    document.getElementById('results-panel').style.display = lastRecords.length ? '' : 'none';
  }
  function _download(name, type, text) {
    const blob = new Blob([text], { type: type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    URL.revokeObjectURL(a.href);
  }
  function downloadJson() { _download('serials.json', 'application/json', JSON.stringify(lastRecords, null, 2)); }
  function downloadCsv() {
    const head = ['Serial', 'Device ID', 'Plan', 'Max Devices', 'Issued At', 'Expires At', 'Offline Token'];
    const rows = lastRecords.map(r => [r.serial, r.device_id, r.plan_name, r.max_devices, r.issued_at, r.expires_at, r.offline_token]);
    const csv = [head].concat(rows).map(cols => cols.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    _download('serials.csv', 'text/csv', csv);
  }
  document.addEventListener('DOMContentLoaded', refreshKey);
</script>
</body></html>'''


@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('SERIAL_ADMIN_PORT', '8787')))
