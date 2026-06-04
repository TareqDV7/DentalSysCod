# Licensing D — Admin Serial-Minting GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A responsive, loopback-only vendor GUI (`serial_admin.py`) that wraps `serial_generator.py` to mint Ed25519-signed serials and generate/display the public key — with the private seed never leaving the machine.

**Architecture:** A standalone Flask app bound to `127.0.0.1`, distinct from `dental_clinic.py`. It imports `serial_generator` for all crypto (DRY), reads the seed server-side only at mint time, and exposes `/api/key/status`, `/api/key/generate`, `/api/mint`. A single dark "operator console" page drives it.

**Tech Stack:** Python 3.12, Flask, `serial_generator.py` (`cryptography` Ed25519). Tests: `pytest` (+ `node --check`).

**Spec:** `docs/superpowers/specs/2026-06-04-licensing-d-admin-minter-design.md`
**Depends on:** A1 (the `serial_generator.py` Ed25519 signer). No dependency on A2/A3/B/C.

---

## File Structure

- **Create** `serial_admin.py` — the localhost Flask app (app + routes + the inline page template).
- **Create** `tests/test_serial_admin_d.py` (backend) and `tests/test_serial_admin_ui_d.py` (page presence + JS sweep).
- **Update** `README.md` (document the vendor tool + test count) and `.gitignore` is already covering `*.csv`/key files (verify).

## Conventions

`rtk proxy python -m pytest tests/test_serial_admin_d.py -v` — check `$LASTEXITCODE`. (Use `rtk proxy python -m pytest`, not `rtk pytest <dir>`.)

---

### Task 1: App skeleton + loopback guard + key status

**Files:**
- Create: `serial_admin.py`
- Create: `tests/test_serial_admin_d.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_serial_admin_d.py
import json
import pytest
import serial_generator
import serial_admin


@pytest.fixture()
def vendor(tmp_path, monkeypatch):
    """serial_admin app with a temp vendor keypair on disk."""
    priv, pub = serial_generator.generate_keypair()
    key_file = tmp_path / 'backend_ed25519_key.json'
    key_file.write_text(json.dumps({'alg': 'ed25519', 'private': priv}), encoding='utf-8')
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(key_file))
    with serial_admin.app.test_client() as c:
        c.pub_b64 = pub
        c.priv_b64 = priv
        yield c


def test_key_status_returns_public_only(vendor):
    r = vendor.get('/api/key/status')
    assert r.status_code == 200
    body = r.get_json()
    assert body['has_key'] is True
    assert body['public_key'] == vendor.pub_b64
    # The private seed must NEVER appear in any response.
    assert 'private' not in r.get_data(as_text=True)
    assert vendor.priv_b64 not in r.get_data(as_text=True)


def test_key_status_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(tmp_path / 'missing.json'))
    with serial_admin.app.test_client() as c:
        assert c.get('/api/key/status').get_json()['has_key'] is False


def test_loopback_guard_blocks_remote(vendor):
    r = vendor.get('/api/key/status', environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_d.py -k "key_status or loopback" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'serial_admin'`.

- [ ] **Step 3: Implement the skeleton**

```python
# serial_admin.py
"""Vendor-side, LOOPBACK-ONLY GUI for minting Ed25519-signed serials.

Run on the vendor machine only:  python serial_admin.py
The private seed (backend_ed25519_key.json) is read server-side at mint time and
NEVER returned, logged, or rendered. Bound to 127.0.0.1; a before_request guard
rejects any non-loopback client.
"""
import base64
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
    # Defence in depth on top of the 127.0.0.1 bind: never serve a non-loopback client.
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
    except (ValueError, OSError, json.JSONDecodeError):
        return jsonify({'has_key': False, 'key_file': KEY_FILE})
    return jsonify({'has_key': True, 'public_key': pub, 'key_file': KEY_FILE})


if __name__ == '__main__':
    # LOOPBACK ONLY — the seed must never be reachable off-machine.
    app.run(host='127.0.0.1', port=int(os.environ.get('SERIAL_ADMIN_PORT', '8787')))
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_serial_admin_d.py -k "key_status or loopback" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_d.py
rtk git commit -m "feat(admin): D loopback-only serial-minting app + key status (public only)"
```

---

### Task 2: `POST /api/key/generate` (with clobber guard)

**Files:**
- Modify: `serial_admin.py`
- Test: `tests/test_serial_admin_d.py`

- [ ] **Step 1: Write the failing test**

```python
def test_generate_refuses_to_clobber(vendor):
    r = vendor.post('/api/key/generate', json={})
    assert r.status_code == 409
    assert r.get_json()['reason'] == 'exists'
    assert vendor.priv_b64 not in r.get_data(as_text=True)


def test_generate_with_confirm_rotates_key(vendor):
    r = vendor.post('/api/key/generate', json={'confirm_overwrite': True})
    assert r.status_code == 200
    body = r.get_json()
    assert body['public_key'] and body['public_key'] != vendor.pub_b64  # new key
    assert 'private' not in r.get_data(as_text=True)


def test_generate_when_absent(tmp_path, monkeypatch):
    path = tmp_path / 'new_key.json'
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(path))
    with serial_admin.app.test_client() as c:
        r = c.post('/api/key/generate', json={})
        assert r.status_code == 200
        assert r.get_json()['public_key']
        assert path.exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_d.py -k generate -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement**

Add to `serial_admin.py`:

```python
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
        os.chmod(KEY_FILE, 0o600)   # best-effort; no-op on platforms without POSIX perms
    except OSError:
        pass
    # Return the PUBLIC key only — the seed stays on disk, never in a response.
    return jsonify({'public_key': pub_b64, 'key_file': KEY_FILE})
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_serial_admin_d.py -k generate -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_d.py
rtk git commit -m "feat(admin): D generate keypair with clobber guard (public-only response)"
```

---

### Task 3: `POST /api/mint` (single, batch, clinic-level)

**Files:**
- Modify: `serial_admin.py`
- Test: `tests/test_serial_admin_d.py`

- [ ] **Step 1: Write the failing test**

```python
def _mint(client, **body):
    base = {'clinic_name': 'Smile Dental', 'clinic_code': 'SMD', 'plan_name': 'Standard',
            'expiry_days': 365, 'max_devices': 3}
    base.update(body)
    return client.post('/api/mint', json=base)


def test_mint_single_verifies(vendor):
    r = _mint(vendor, devices=['LAPTOP-01'])
    assert r.status_code == 200
    recs = r.get_json()['records']
    assert len(recs) == 1
    ok, payload = serial_generator.verify_serial_token(recs[0]['offline_token'], vendor.pub_b64)
    assert ok is True
    assert payload['max_devices'] == 3
    assert payload['plan_name'] == 'Standard'
    assert payload['serial'] == recs[0]['serial']


def test_mint_batch_distinct_and_valid(vendor):
    recs = _mint(vendor, devices=['A', 'B', 'C']).get_json()['records']
    assert len(recs) == 3
    serials = {x['serial'] for x in recs}
    assert len(serials) == 3
    for x in recs:
        ok, _ = serial_generator.verify_serial_token(x['offline_token'], vendor.pub_b64)
        assert ok is True


def test_mint_clinic_level_when_no_devices(vendor):
    recs = _mint(vendor, devices=[]).get_json()['records']
    assert len(recs) == 1
    ok, _ = serial_generator.verify_serial_token(recs[0]['offline_token'], vendor.pub_b64)
    assert ok is True


def test_mint_without_key_400(tmp_path, monkeypatch):
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(tmp_path / 'missing.json'))
    with serial_admin.app.test_client() as c:
        r = c.post('/api/mint', json={'clinic_name': 'X', 'clinic_code': 'X', 'devices': ['D']})
        assert r.status_code == 400
        assert r.get_json()['reason'] == 'no_key'


def test_mint_csv_format(vendor):
    r = _mint(vendor, devices=['A', 'B'], **{}) if False else vendor.post(
        '/api/mint?format=csv',
        json={'clinic_name': 'Smile', 'clinic_code': 'SMD', 'devices': ['A', 'B'],
              'plan_name': 'Standard', 'expiry_days': 365, 'max_devices': 1})
    assert r.status_code == 200
    assert 'text/csv' in r.headers['Content-Type']
    text = r.get_data(as_text=True)
    assert 'Serial' in text and text.count('\n') >= 2  # header + 2 rows


@pytest.mark.parametrize('body', [
    {}, {'clinic_name': '', 'clinic_code': 'SMD'},
    {'clinic_name': 'X', 'clinic_code': 'TOOLONG'},
    {'clinic_name': 'X', 'clinic_code': 'SMD', 'devices': 'x' * 5000},
])
def test_mint_never_500s(vendor, body):
    r = vendor.post('/api/mint', json=body)
    assert r.status_code in (200, 400)
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_d.py -k mint -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement**

Add to `serial_admin.py`:

```python
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
        devices = [f'CLINIC-{clinic_code.upper()}']   # clinic-level (non-device-locked) serial

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
        resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    return jsonify({'records': records})
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_serial_admin_d.py -k mint -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_d.py
rtk git commit -m "feat(admin): D POST /api/mint (single/batch/clinic-level + CSV)"
```

---

### Task 4: The responsive operator-console page

**Files:**
- Modify: `serial_admin.py` (add `INDEX_TEMPLATE` + `GET /`)
- Create: `tests/test_serial_admin_ui_d.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_serial_admin_ui_d.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import serial_admin


def test_index_has_key_and_mint_surfaces():
    with serial_admin.app.test_client() as c:
        html = c.get('/').get_data(as_text=True)
    assert 'id="key-panel"' in html
    assert 'id="mint-form"' in html
    assert "fetch('/api/mint'" in html or 'fetch("/api/mint"' in html
    assert "fetch('/api/key/status'" in html or 'fetch("/api/key/status"' in html
    # The page must never embed the seed; only the public key is ever shown.
    assert 'private' not in html.lower() or 'private key' not in html.lower()


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_index_scripts_pass_node_check():
    with serial_admin.app.test_client() as c:
        html = c.get('/').get_data(as_text=True)
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    assert scripts
    blob = '\n;\n'.join(scripts)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
        fh.write(blob); path = fh.name
    try:
        proc = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_ui_d.py -v`
Expected: FAIL — `GET /` 404 (no index route).

- [ ] **Step 3: Implement the page**

Add to `serial_admin.py` an `INDEX_TEMPLATE` string and a route. Keep it a deliberate dark console
(not a default template); mind the JS-escaping rule (no literal `'\n'` inside strings):

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_serial_admin_ui_d.py -v`
Expected: PASS (node sweep runs if `node` present). `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_ui_d.py
rtk git commit -m "feat(admin): D responsive operator-console page for minting"
```

---

### Task 5: Full regression + docs + gitignore check

**Files:**
- Modify: `README.md`; verify `.gitignore`

- [ ] **Step 1: Byte-compile + full suite**

```bash
rtk proxy python -m py_compile serial_admin.py
rtk proxy python -m pytest tests/ -q
```
Expected: clean; full suite green (D is a separate app, so it can't regress the clinic app). `$LASTEXITCODE` == 0.

- [ ] **Step 2: Verify gitignore covers minted artifacts + the key**

Confirm `.gitignore` already ignores `backend_ed25519_key.json`, `*.csv`, and any `serials*.json`.
If `serials*.json` / a vendor key path isn't covered, add it (do not commit real tokens or the seed).

- [ ] **Step 3: Document the vendor tool**

Add a short README/`docs/SERIAL_GENERATOR_README.md` note: "Run `python serial_admin.py` on the
vendor machine for a GUI at http://127.0.0.1:8787 (loopback only). The private seed stays on the
machine; copy the shown **public** key into `CLINIC_SERIAL_PUBLIC_KEY` / the baked constant."
Bump the README test-count line for the two new suites.

- [ ] **Step 4: Commit + push**

```bash
rtk git add README.md docs/SERIAL_GENERATOR_README.md .gitignore
rtk git commit -m "docs: D — vendor serial-minting console usage + test suites"
rtk git push
```

---

## Self-Review

1. **Spec coverage:** loopback app + key status (T1), generate with clobber guard (T2), mint
   single/batch/clinic-level/CSV/no-key/fuzz (T3), responsive console + JS sweep (T4),
   regression+docs+gitignore (T5). Every "In" bullet maps to a task. ✅
2. **Placeholder scan:** none. `KEY_FILE` defaults to the real `backend_ed25519_key.json` and is
   env-overridable for tests; no fake constants.
3. **Type/name consistency:** `KEY_FILE`, `_public_key_b64`, `_mint_records(data) -> (records,
   err)` used identically across routes and tests; the page ids (`key-panel`, `mint-form`,
   `results-panel`) match the presence tests; the JSON record fields (`serial`, `offline_token`,
   `device_id`, `expires_at`) match what the page renders and the CSV builder reads.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-licensing-d-admin-minter.md`. Two options:

1. **Subagent-Driven (recommended)** — fresh subagent per task; run them **one at a time** (the earlier 5-way parallel fan-out hit the account session limit).
2. **Inline Execution** — implement T1–T5 in-session with checkpoints.

**Which approach?** All five sub-project specs + plans (A2, A3, B, C, D) now exist under `docs/superpowers/{specs,plans}/2026-06-04-licensing-*`.
