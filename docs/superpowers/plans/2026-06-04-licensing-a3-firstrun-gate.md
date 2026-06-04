# Licensing A3 — First-Run Gate UX + Renewal + Advisory Revocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate a fresh install behind activation, nudge renewal in grace, degrade to server-enforced view-only on revocation/expiry, and keep all of it decoupled from cloud sync — surfaced in the desktop SPA.

**Architecture:** A single `_license_gate_state(cursor)` derives `unlicensed|active|grace|view_only` from the A2-cached license. `GET /api/license/gate` exposes it. A `before_request` write-guard blocks clinical mutations in `view_only` (fail-open on error). A decoupled periodic `license_recheck_worker` refreshes cached status from the cloud via the A2 seam. The SPA renders an activation overlay / renewal banner / view-only lockout off the gate state.

**Tech Stack:** Python 3.12, Flask, SQLite, `threading`; vanilla JS in `templates.HTML_TEMPLATE`. Tests in `pytest` (+ a `node --check` JS sweep).

**Spec:** `docs/superpowers/specs/2026-06-04-licensing-a3-firstrun-gate-design.md`
**Depends on:** A2 (`_validate_with_cloud`, `_license_cloud_url`, hardened `/api/license/activate`).

---

## File Structure

- **Modify** `dental_clinic.py`:
  - new helper `_license_gate_state(cursor)` near `evaluate_license_window` (`~:1685`).
  - new route `GET /api/license/gate` near `license_status` (`~:5017`).
  - new `before_request` write-guard after `_require_login_for_portal` (`~:1778`).
  - new `license_recheck_once(http=None)` + `license_recheck_worker()` near `cloud_sync_worker` (`~:6098`); start the thread in `__main__` (`~:6190`).
- **Modify** `templates.py` (`HTML_TEMPLATE`): activation overlay, renewal banner, view-only banner + lockout, and the `DOMContentLoaded` gate fetch.
- **Create** `tests/test_license_gate_a3.py` (backend) and `tests/test_license_gate_ui_a3.py` (template presence + JS sweep).
- **Update** `README.md` test-count line.

## Conventions for every test run

```bash
rtk proxy python -m pytest tests/test_license_gate_a3.py -v
```
RTK collects 0 tests if you pass a dir to `rtk pytest`, so use `rtk proxy python -m pytest`. pytest summary is suppressed — **check `$LASTEXITCODE`** (`0` = pass).

---

### Task 1: `_license_gate_state` helper

**Files:**
- Modify: `dental_clinic.py` (add helper after `fetch_license_record`, `~:1705`)
- Create: `tests/test_license_gate_a3.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_license_gate_a3.py
import sqlite3
import pytest
import dental_clinic
from datetime import datetime, timedelta, timezone


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _seed_license(serial, status='active', days=365, grace_extra=14):
    today = datetime.now(timezone.utc).date()
    expires = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    grace = (today + timedelta(days=days + grace_extra)).strftime('%Y-%m-%d')
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute('''INSERT INTO licenses (serial_number, clinic_name, plan_name, status,
                    max_devices, expires_at, grace_until) VALUES (?,?,?,?,?,?,?)''',
                 (serial, 'C', 'standard', status, 3, expires, grace))
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('active_serial_number', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (serial,))
    conn.commit(); conn.close()


def _state(local):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    s = dental_clinic._license_gate_state(cur)
    conn.close()
    return s


def test_state_unlicensed_when_no_license(local):
    assert _state(local)['state'] == 'unlicensed'


def test_state_active_for_future_window(local):
    _seed_license('DENTAL-A3-ACT', days=365)
    assert _state(local)['state'] == 'active'


def test_state_grace_when_in_grace(local):
    _seed_license('DENTAL-A3-GRC', days=-5, grace_extra=14)   # expired 5d ago, 14d grace
    assert _state(local)['state'] == 'grace'


def test_state_view_only_past_grace(local):
    _seed_license('DENTAL-A3-EXP', days=-60, grace_extra=14)  # well past grace
    assert _state(local)['state'] == 'view_only'


def test_state_view_only_when_revoked(local):
    _seed_license('DENTAL-A3-REV', status='revoked', days=365)
    assert _state(local)['state'] == 'view_only'
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k state -v`
Expected: FAIL — `AttributeError: module 'dental_clinic' has no attribute '_license_gate_state'`.

- [ ] **Step 3: Implement the helper**

Add after `fetch_license_record` (`~:1705`):

```python
def _license_gate_state(cursor):
    """Single source of truth for the licensing gate. Returns a dict with 'state'
    in {unlicensed, active, grace, view_only} plus the window fields, derived from
    the A2-cached license row. Offline-tolerant: it reads cached state only."""
    active_serial = str(read_app_setting(cursor, 'active_serial_number', '') or '').strip()
    if not active_serial:
        cursor.execute("SELECT serial_number FROM licenses WHERE status='active' "
                       "ORDER BY updated_at DESC, activated_at DESC LIMIT 1")
        row = cursor.fetchone()
        active_serial = row[0] if row else ''
    if not active_serial:
        return {'state': 'unlicensed', 'licensed': False}

    record = fetch_license_record(cursor, active_serial)
    if not record:
        return {'state': 'unlicensed', 'licensed': False}

    validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
    status = str(record['status'] or '')
    if status in ('revoked', 'suspended') or not validity['licensed']:
        state = 'view_only'
    elif validity['in_grace']:
        state = 'grace'
    else:
        state = 'active'
    return {
        'state': state,
        'licensed': state in ('active', 'grace'),
        'status': status,
        'serial_number': record['serial_number'],
        'clinic_name': record['clinic_name'],
        'plan_name': record['plan_name'],
        'expires_at': record['expires_at'],
        'grace_until': record['grace_until'],
        'in_grace': bool(validity['in_grace']),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k state -v`
Expected: all 5 PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_gate_a3.py
rtk git commit -m "feat(license): A3 _license_gate_state state machine"
```

---

### Task 2: `GET /api/license/gate` endpoint

**Files:**
- Modify: `dental_clinic.py` (add route after `license_status`, `~:5017`)
- Test: `tests/test_license_gate_a3.py`

- [ ] **Step 1: Write the failing test**

```python
def test_gate_endpoint_reports_unlicensed(local):
    body = local.get('/api/license/gate').get_json()
    assert body['state'] == 'unlicensed' and body['licensed'] is False


def test_gate_endpoint_reports_active(local):
    _seed_license('DENTAL-A3-GATE', days=365)
    body = local.get('/api/license/gate').get_json()
    assert body['state'] == 'active'
    assert body['serial_number'] == 'DENTAL-A3-GATE'
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k gate_endpoint -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement the route**

Add after `license_status` (`~:5017`):

```python
@app.route('/api/license/gate')
def license_gate():
    conn = get_db_connection()
    cursor = conn.cursor()
    state = _license_gate_state(cursor)
    conn.close()
    return jsonify(state)
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k gate_endpoint -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_gate_a3.py
rtk git commit -m "feat(license): A3 GET /api/license/gate endpoint"
```

---

### Task 3: View-only write-guard (`before_request`)

**Files:**
- Modify: `dental_clinic.py` (new `before_request` after `_require_login_for_portal`, `~:1778`)
- Test: `tests/test_license_gate_a3.py`

- [ ] **Step 1: Write the failing test**

```python
def _login(local):
    with local.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def test_view_only_blocks_clinical_write(local):
    _seed_license('DENTAL-A3-VO', days=-60)   # view_only
    _login(local)
    r = local.post('/api/patients', json={'name': 'X'})
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'view_only'


def test_view_only_allows_reads(local):
    _seed_license('DENTAL-A3-VO2', days=-60)
    _login(local)
    assert local.get('/api/patients').status_code == 200


def test_view_only_allows_license_endpoints(local):
    _seed_license('DENTAL-A3-VO3', days=-60)
    _login(local)
    # license activate must NOT be blocked by the guard (it reaches its own handler).
    r = local.post('/api/license/activate', json={})
    assert r.status_code in (400, 403)
    assert (r.get_json() or {}).get('reason') != 'view_only'


def test_active_allows_clinical_write(local):
    _seed_license('DENTAL-A3-OK', days=365)   # active
    _login(local)
    r = local.post('/api/patients', json={'name': 'Jane Active', 'phone': '0590000000'})
    assert r.status_code in (200, 201)


def test_write_guard_fails_open_on_error(local, monkeypatch):
    _seed_license('DENTAL-A3-FO', days=-60)
    _login(local)
    def boom(_cur):
        raise RuntimeError('gate exploded')
    monkeypatch.setattr(dental_clinic, '_license_gate_state', boom)
    r = local.post('/api/patients', json={'name': 'FailOpen', 'phone': '0590000001'})
    assert r.status_code in (200, 201)   # a licensing bug must never brick data entry
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k view_only -v`
Expected: `test_view_only_blocks_clinical_write` FAILS (write currently succeeds, no guard).

- [ ] **Step 3: Implement the write-guard**

Add immediately after `_require_login_for_portal` (`~:1778`):

```python
# Endpoints that stay writable even in view-only mode: licensing (so you can renew),
# auth (login/logout), cloud connectivity, and health. Everything else clinical is
# read-only once the subscription lapses.
_VIEW_ONLY_WRITE_ALLOW_PREFIXES = ('/api/license/', '/api/auth/', '/api/cloud/')
_VIEW_ONLY_WRITE_ALLOW_EXACT = {'/healthz'}


@app.before_request
def _enforce_view_only():
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None
    path = request.path or '/'
    if not path.startswith('/api/'):
        return None
    if path in _VIEW_ONLY_WRITE_ALLOW_EXACT or path.startswith(_VIEW_ONLY_WRITE_ALLOW_PREFIXES):
        return None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        state = _license_gate_state(cur)['state']
        conn.close()
    except Exception:  # noqa: BLE001 - fail OPEN: never brick data entry over a licensing bug
        return None
    if state == 'view_only':
        return jsonify({'error': 'License expired — view only. Renew to make changes.',
                        'reason': 'view_only'}), 403
    return None
```

> `before_request` callbacks run in registration order; defining this **after**
> `_require_login_for_portal` keeps auth-first semantics (an unauthenticated write still 401s
> before the license check matters).

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k "view_only or active_allows or fails_open" -v`
Expected: PASS. `$LASTEXITCODE` == 0. If `test_active_allows_clinical_write` fails on a 400 (validation), adjust the test body to a valid patient payload for this schema — the guard must let it through to the handler (a 400 from the handler is fine; a 403 view_only is not).

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_gate_a3.py
rtk git commit -m "feat(license): A3 server-enforced view-only write-guard (fail-open)"
```

---

### Task 4: Decoupling guarantee (license path never enables sync)

**Files:**
- Test: `tests/test_license_gate_a3.py`

- [ ] **Step 1: Write the failing test**

```python
def _has_cloud_setting(key):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    row = conn.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
    conn.close()
    return bool(row and str(row[0] or '').strip())


def test_activation_does_not_enable_cloud_sync(local, monkeypatch):
    # Even a fully successful cloud-validated activation must not write the sync keys.
    import serial_generator
    priv, pub = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub)
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud',
                        lambda *a, **k: {'valid': True, 'status': 'active'})
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {'v': 2, 'serial': 'DENTAL-A3-DECOUP', 'clinic_name': 'C', 'plan_name': 'standard',
               'max_devices': 3, 'issued_at': now.isoformat() + 'Z',
               'expires_at': (now + timedelta(days=365)).isoformat() + 'Z',
               'grace_until': (now + timedelta(days=379)).isoformat() + 'Z'}
    token = serial_generator.sign_serial_token(payload, priv)
    r = local.post('/api/license/activate', json={'serial_token': token})
    assert r.status_code == 200
    assert not _has_cloud_setting('cloud_url')
    assert not _has_cloud_setting('cloud_clinic_token')
```

- [ ] **Step 2: Run to verify it passes (regression guard)**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k decoup -v`
Expected: PASS — A2's `activate_license` only reads the cloud URL, never writes sync keys. This test **locks that decoupling in** so a future edit can't silently couple them.

- [ ] **Step 3: Implement**

No code change. If this test ever fails, a regression coupled licensing to sync — fix the
offending writer, not the test.

- [ ] **Step 4: Re-run**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k decoup -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_license_gate_a3.py
rtk git commit -m "test(license): A3 lock licensing↔cloud-sync decoupling"
```

---

### Task 5: License re-check worker (decoupled, offline-safe)

**Files:**
- Modify: `dental_clinic.py` (add `license_recheck_once` + `license_recheck_worker` near `cloud_sync_worker`, `~:6098`; start thread in `__main__`)
- Test: `tests/test_license_gate_a3.py`

- [ ] **Step 1: Write the failing test**

```python
def _license_status_value(serial):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    row = conn.execute('SELECT status FROM licenses WHERE serial_number=?', (serial.upper(),)).fetchone()
    conn.close()
    return row[0] if row else None


def test_recheck_applies_cloud_revocation(local, monkeypatch):
    _seed_license('DENTAL-A3-RC', status='active', days=365)
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud',
                        lambda *a, **k: {'valid': False, 'reason': 'revoked'})
    dental_clinic.license_recheck_once()
    # Cached status now maps to view_only.
    assert _license_status_value('DENTAL-A3-RC') in ('revoked', 'suspended')
    conn = sqlite3.connect(dental_clinic.DB_NAME); cur = conn.cursor()
    assert dental_clinic._license_gate_state(cur)['state'] == 'view_only'
    conn.close()


def test_recheck_offline_does_not_downgrade(local, monkeypatch):
    _seed_license('DENTAL-A3-RC2', status='active', days=365)
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud', lambda *a, **k: None)  # offline
    dental_clinic.license_recheck_once()
    assert _license_status_value('DENTAL-A3-RC2') == 'active'   # unchanged


def test_recheck_noops_without_license(local, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud', lambda *a, **k: {'valid': False})
    # Must not raise when there is no active serial.
    dental_clinic.license_recheck_once()
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k recheck -v`
Expected: FAIL — `AttributeError: … 'license_recheck_once'`.

- [ ] **Step 3: Implement the worker**

Add near `cloud_sync_worker` (`~:6098`):

```python
LICENSE_RECHECK_HOURS = float(os.environ.get('CLINIC_LICENSE_RECHECK_HOURS', '24') or 24)


def license_recheck_once(http=None):
    """Refresh the cached license status from the cloud authority, decoupled from
    cloud sync. Offline (no URL / network down) is a no-op — offline NEVER downgrades
    a clinic to view-only. Never raises."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        serial = str(read_app_setting(cur, 'active_serial_number', '') or '').strip()
        token = str(read_app_setting(cur, 'active_serial_token', '') or '').strip()
        fingerprint = _get_or_create_device_fingerprint(cur)
        if not serial:
            conn.close()
            return
        result = _validate_with_cloud(token, fingerprint) if token else None
        if not isinstance(result, dict):
            write_app_setting(cur, 'license_last_recheck_at', utc_now_iso())
            write_app_setting(cur, 'license_last_recheck_result', 'offline')
            conn.commit(); conn.close()
            return
        if result.get('valid'):
            status = str(result.get('status') or 'active')
            expires_at = _iso_to_window_date(result.get('expires_at'))
            grace_until = _iso_to_window_date(result.get('grace_until'))
            sets, vals = ['status = ?'], [status]
            if expires_at:
                sets.append('expires_at = ?'); vals.append(expires_at)
            if grace_until:
                sets.append('grace_until = ?'); vals.append(grace_until)
            vals.append(serial)
            cur.execute(f"UPDATE licenses SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP "
                        f"WHERE serial_number = ?", vals)
        else:
            reason = str(result.get('reason') or 'revoked')
            new_status = 'suspended' if reason == 'suspended' else 'revoked'
            cur.execute("UPDATE licenses SET status=?, updated_at=CURRENT_TIMESTAMP "
                        "WHERE serial_number = ?", (new_status, serial))
        write_app_setting(cur, 'license_last_recheck_at', utc_now_iso())
        write_app_setting(cur, 'license_last_recheck_result', 'ok')
        conn.commit(); conn.close()
    except Exception as exc:  # noqa: BLE001 - a re-check failure must never crash the server
        try:
            app.logger.warning('license_recheck_once failed: %s', exc)
        except Exception:
            pass


def license_recheck_worker():
    """Background loop: re-check the license every CLINIC_LICENSE_RECHECK_HOURS.
    Runs independently of cloud sync (it starts even when sync is unpaired)."""
    interval = max(1.0, LICENSE_RECHECK_HOURS) * 3600.0
    while True:
        license_recheck_once()
        time.sleep(interval)
```

> `active_serial_token` is the retained vendor serial token. **Add one line to A2's
> `_activate_primary`** so the re-check can re-send it: right after
> `write_app_setting(cursor, 'active_serial_number', serial_number)`, add
> `write_app_setting(cursor, 'active_serial_token', serial_token)`. (This is the only A2 edit A3
> needs; it stores the *vendor-signed* token, which is not a secret beyond the serial itself.)

Then start the worker beside the sync worker in `__main__` (`~:6190`), guarded so it only runs in
the real server process (mirror how `cloud_sync_worker` is started):

```python
        threading.Thread(target=license_recheck_worker, daemon=True).start()
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_gate_a3.py -k recheck -v`
Expected: PASS. `$LASTEXITCODE` == 0. (Tests call `license_recheck_once` directly — they never
start the thread.)

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_gate_a3.py
rtk git commit -m "feat(license): A3 decoupled periodic license re-check worker"
```

---

### Task 6: SPA gate — activation overlay, renewal + view-only banners

**Files:**
- Modify: `templates.py` (`HTML_TEMPLATE`)
- Create: `tests/test_license_gate_ui_a3.py`

- [ ] **Step 1: Write the failing test (template presence + JS sweep)**

```python
# tests/test_license_gate_ui_a3.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import templates


def test_template_has_gate_markup():
    html = templates.HTML_TEMPLATE
    assert 'id="license-gate-overlay"' in html
    assert 'id="license-renew-banner"' in html
    assert 'id="license-viewonly-banner"' in html
    assert "fetch('/api/license/gate'" in html or 'fetch("/api/license/gate"' in html


def test_template_wires_activation_post():
    html = templates.HTML_TEMPLATE
    assert '/api/license/activate' in html
    assert 'view-only' in html   # the body class hook for the lockout


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_template_scripts_pass_node_check():
    # Guards the templates.py JS-escaping trap: a literal '\n' inside HTML_TEMPLATE
    # collapses to a real newline and breaks the inline script. node --check catches it.
    html = templates.HTML_TEMPLATE
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    assert scripts, 'no inline <script> blocks found'
    blob = '\n;\n'.join(scripts)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
        fh.write(blob)
        path = fh.name
    try:
        proc = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_gate_ui_a3.py -v`
Expected: `test_template_has_gate_markup` FAILS (markers absent).

- [ ] **Step 3: Implement the gate UI in `HTML_TEMPLATE`**

3a. **Markup** — add near the top of `<body>` (before the main app container):

```html
    <div id="license-renew-banner" class="license-banner hidden">
      <span id="license-renew-text"></span>
      <button type="button" onclick="openLicenseActivation()">Renew</button>
      <button type="button" onclick="dismissRenewBanner()">Dismiss</button>
    </div>
    <div id="license-viewonly-banner" class="license-banner license-banner--warn hidden">
      <span>License inactive — view only. Renew to make changes.</span>
      <button type="button" onclick="openLicenseActivation()">Renew</button>
    </div>
    <div id="license-gate-overlay" class="license-overlay hidden">
      <div class="license-overlay__card">
        <h2>Activate this clinic</h2>
        <p>Paste the serial token from your vendor to activate.</p>
        <textarea id="license-gate-token" rows="4" placeholder="serial token"></textarea>
        <button type="button" onclick="submitLicenseActivation()">Activate</button>
        <div id="license-gate-status" class="license-overlay__status"></div>
      </div>
    </div>
```

3b. **CSS** — add to the `<style>` block:

```css
    .license-banner { display:flex; gap:12px; align-items:center; padding:10px 16px;
      background:#fff4ce; color:#5c4400; font-size:.9rem; }
    .license-banner--warn { background:#ffe2e5; color:#8d1f33; }
    .license-overlay { position:fixed; inset:0; background:rgba(15,23,42,.78);
      display:flex; align-items:center; justify-content:center; z-index:9999; }
    .license-overlay__card { background:#fff; padding:28px; border-radius:14px;
      width:min(440px,92vw); box-shadow:0 24px 60px rgba(0,0,0,.35); }
    .license-overlay__card textarea { width:100%; margin:12px 0; font-family:monospace; }
    .license-overlay__status { margin-top:10px; min-height:18px; font-size:.85rem; }
    body.view-only [data-write] { pointer-events:none; opacity:.5; }
    .hidden { display:none; }
```

> If `.hidden` already exists in `HTML_TEMPLATE`, do **not** redefine it — reuse it.

3c. **JS** — add this block inside the SPA `<script>` (mind the escaping trap: any newline you
want *inside a string* must be `'\\n'`; the code below has none):

```javascript
        async function applyLicenseGate() {
            try {
                const res = await fetch('/api/license/gate');
                const g = await res.json();
                const state = g.state || 'active';
                const overlay = document.getElementById('license-gate-overlay');
                const renew = document.getElementById('license-renew-banner');
                const vo = document.getElementById('license-viewonly-banner');
                document.body.classList.toggle('view-only', state === 'view_only');
                overlay.classList.toggle('hidden', state !== 'unlicensed');
                vo.classList.toggle('hidden', state !== 'view_only');
                if (state === 'grace') {
                    document.getElementById('license-renew-text').textContent =
                        'Subscription expired — in grace period until ' + (g.grace_until || '') + '. Renew to avoid interruption.';
                    renew.classList.remove('hidden');
                } else {
                    renew.classList.add('hidden');
                }
            } catch (e) { /* offline: leave the app usable, never gate on a fetch error */ }
        }
        function openLicenseActivation() {
            document.getElementById('license-gate-overlay').classList.remove('hidden');
        }
        function dismissRenewBanner() {
            document.getElementById('license-renew-banner').classList.add('hidden');
        }
        async function submitLicenseActivation() {
            const token = (document.getElementById('license-gate-token').value || '').trim();
            const status = document.getElementById('license-gate-status');
            if (!token) { status.textContent = 'Please paste your serial token.'; return; }
            status.textContent = 'Activating...';
            try {
                const res = await fetch('/api/license/activate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ serial_token: token })
                });
                const body = await res.json();
                if (!res.ok) { status.textContent = body.error || 'Activation failed.'; return; }
                window.location.reload();
            } catch (e) { status.textContent = 'Network error during activation.'; }
        }
        document.addEventListener('DOMContentLoaded', applyLicenseGate);
```

> The `[data-write]` lockout is best-effort UI. The **server** write-guard (Task 3) is the real
> enforcement, so unmarked controls are still safe. Optionally tag obvious create/edit/delete
> buttons with `data-write` for the visual disable — not required for correctness.

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_gate_ui_a3.py -v`
Expected: PASS (the `node --check` test runs if `node` is installed; else it skips). `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add templates.py tests/test_license_gate_ui_a3.py
rtk git commit -m "feat(license): A3 SPA first-run gate, renewal + view-only banners"
```

---

### Task 7: Full regression + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Byte-compile + full suite**

```bash
rtk proxy python -m py_compile dental_clinic.py templates.py
rtk proxy python -m pytest tests/ -q
```
Expected: `py_compile` silent; the whole suite passes (A1 + A2 + A3). Check `$LASTEXITCODE` == 0.
If an A1/A2 test regressed (e.g. the new `before_request` blocking something), fix the
implementation, not the test. **Watch the write-guard**: confirm existing API tests that POST in
local mode without a license still pass — with no license the state is `unlicensed` (not
`view_only`), so writes are allowed; only `view_only` blocks. Verify this assumption holds in the
suite, and if any test seeds a lapsed license and then writes, that is the guard working.

- [ ] **Step 2: Update README test count**

Bump the "tests across N suites" line to include `tests/test_license_gate_a3.py` and
`tests/test_license_gate_ui_a3.py` (two new suites). Keep the existing wording style.

- [ ] **Step 3: Commit + push**

```bash
rtk git add README.md
rtk git commit -m "docs: A3 — record first-run gate + view-only test suites"
rtk git push
```

---

## Self-Review

1. **Spec coverage:** gate state machine (T1), `/api/license/gate` (T2), view-only write-guard
   + fail-open (T3), decoupling (T4), re-check worker offline-safe (T5), SPA overlay/banners/
   lockout + JS sweep (T6), regression + docs (T7). Every "In" bullet maps to a task. ✅
2. **Placeholder scan:** none — every step has concrete code/markup/commands. The one A2 edit
   (`active_serial_token` write) is spelled out in T5 Step 3.
3. **Type/name consistency:** `_license_gate_state` returns a dict with `state` everywhere it is
   read (endpoint, guard, recheck test, SPA `g.state`); `license_recheck_once(http=None)` matches
   its callers; gate JSON field names (`state`, `grace_until`, `serial_number`) match the SPA
   reads and the spec response shape.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-licensing-a3-firstrun-gate.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Run subagents **one at a time** (the earlier 5-way parallel fan-out hit the account session limit).
2. **Inline Execution** — implement Tasks 1–7 in-session with checkpoints.

**Which approach?** (Or continue to the next plan — B — since you asked for all five.)
