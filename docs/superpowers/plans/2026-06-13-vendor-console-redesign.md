# Vendor Console Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the confusing 5-panel vendor serial console into a premium enterprise-light SPA (sidebar nav, Dashboard / Issue / Licenses / Settings) with one shared cloud connection, full license management (search/filter/publish/revoke), and toast-based feedback — backed by the unchanged Ed25519 minting core.

**Architecture:** A single loopback-only Flask app (`serial_admin.py`) keeps all routes/logic; the large HTML+CSS+JS template moves into a new logic-free `serial_admin_ui.py` (`INDEX_TEMPLATE`). The frontend is a vanilla-JS SPA with a client-side view router. A single in-memory `conn = {cloud_url, admin_token}` (established in Settings, optionally persisted to a `0600` `console_settings.json`) is reused by every cloud action. Three new routes — `/api/settings`, `/api/cloud/ping`, `/api/cloud/revoke` — proxy the already-deployed cloud admin endpoints.

**Tech Stack:** Python 3 + Flask + `cryptography` + stdlib (`urllib`, `sqlite3`); vanilla JS/CSS frontend; pytest for tests; `node --check` to guard the inline-script escaping trap.

---

## Spec

`docs/superpowers/specs/2026-06-13-vendor-console-redesign-design.md`

## File structure

| File | Responsibility | Change |
|---|---|---|
| `serial_admin.py` | Flask routes, mint logic, ledger helpers, cloud proxies, settings persistence | Modify: extract template; add settings + ping + revoke routes |
| `serial_admin_ui.py` | `INDEX_TEMPLATE` string only (HTML+CSS+JS SPA). No logic, no import of `serial_admin` | **Create** |
| `console_settings.json` | Persisted connection settings (`0600`), next to the signing key | Created at runtime; gitignored |
| `.gitignore` | Ignore `console_settings.json` | Modify |
| `tests/test_serial_admin_console.py` | Tests for settings/ping/revoke routes + HTML/JS sanity | **Create** |

Existing behavior preserved: `/api/key/status`, `/api/key/generate`, `/api/mint`, `/api/history`, `/api/upload-cloud`, `/api/publish-token`, `/api/cloud/serials`, the `_loopback_only` guard, and the local mint ledger are unchanged.

---

### Task 1: Extract the template into `serial_admin_ui.py` (pure refactor)

Move the existing `INDEX_TEMPLATE` out of `serial_admin.py` with **zero behavior change**, and add a `node --check` guard so future edits to the inline script can't silently break it (the templates.py `\n` escaping trap).

**Files:**
- Create: `serial_admin_ui.py`
- Modify: `serial_admin.py:403-713` (remove the `INDEX_TEMPLATE = r'''...'''` block; import it instead)
- Create: `tests/test_serial_admin_console.py`

- [ ] **Step 1: Create `serial_admin_ui.py` with the current template**

Create `serial_admin_ui.py` containing exactly the current `INDEX_TEMPLATE` assignment (copy verbatim from `serial_admin.py` lines 403-708, the `INDEX_TEMPLATE = r'''<!doctype html>...</html>'''`). Header of the new file:

```python
"""Vendor console UI — the SPA template string only.

Holds INDEX_TEMPLATE (HTML + CSS + JS) for serial_admin.py. Deliberately
logic-free and free of any import from serial_admin (avoids an import cycle),
so the UI can be edited and visually reviewed without touching the routes.
"""

INDEX_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
... (paste the existing template body unchanged for now) ...
</body></html>'''
```

- [ ] **Step 2: Point `serial_admin.py` at the extracted template**

In `serial_admin.py`, delete the entire `INDEX_TEMPLATE = r'''...'''` block (lines 403-708) and add an import next to the existing `import serial_generator` (line 21):

```python
import serial_generator
from serial_admin_ui import INDEX_TEMPLATE
```

The `index()` route (now near the end of the file) stays:

```python
@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)
```

- [ ] **Step 3: Create the test file with a fixture + the sanity tests**

Create `tests/test_serial_admin_console.py`:

```python
"""Vendor console: settings persistence, cloud ping/revoke proxies, and HTML/JS
sanity. The console is loopback-only and the signing seed never leaves the box."""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

import serial_generator
import serial_admin
import serial_admin_ui


@pytest.fixture()
def vendor(tmp_path, monkeypatch):
    """serial_admin test client with an isolated temp key, ledger, and settings
    file (all derived from / overridden into tmp_path)."""
    priv, pub = serial_generator.generate_keypair()
    key_file = tmp_path / 'backend_ed25519_key.json'
    key_file.write_text(json.dumps({'alg': 'ed25519', 'private': priv}), encoding='utf-8')
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(key_file))
    monkeypatch.delenv(serial_admin.LEDGER_FILE_ENV, raising=False)
    # Literal env-var name (not serial_admin.SETTINGS_FILE_ENV) so the shared
    # fixture is stable in Task 1, before that constant exists. Task 2 adds the
    # constant equal to this same string.
    monkeypatch.setenv('CLINIC_CONSOLE_SETTINGS_FILE', str(tmp_path / 'console_settings.json'))
    with serial_admin.app.test_client() as c:
        c.pub_b64 = pub
        c.priv_b64 = priv
        c.settings_path = tmp_path / 'console_settings.json'
        yield c


def test_index_renders_with_four_views(vendor):
    html = vendor.get('/').get_data(as_text=True)
    assert vendor.get('/').status_code == 200
    for marker in ('id="view-dashboard"', 'id="view-issue"',
                   'id="view-licenses"', 'id="view-settings"'):
        assert marker in html


def test_inline_script_is_valid_js():
    """Guards the templates.py escaping trap: a stray real newline inside a JS
    string literal is a syntax error that node --check catches."""
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    m = re.search(r'<script>(.*)</script>', serial_admin_ui.INDEX_TEMPLATE, re.S)
    assert m, 'no <script> block found in INDEX_TEMPLATE'
    fd, path = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(m.group(1))
        res = subprocess.run([node, '--check', path], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
    finally:
        os.unlink(path)
```

Note: `test_index_renders_with_four_views` is **expected to FAIL** at this task (the old template has no `view-*` ids). That is intentional — it is the failing test that drives the frontend rewrite in Tasks 5-7. Mark it xfail for now so Task 1 commits green, and remove the xfail in Task 5:

```python
@pytest.mark.xfail(reason='views land in the frontend rewrite (Task 5)', strict=False)
def test_index_renders_with_four_views(vendor):
    ...
```

- [ ] **Step 4: Run the tests**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py tests/test_serial_mint_ledger.py -q`
Expected: PASS (the four-views test xfails; the node check passes or skips; all existing ledger tests still pass against the extracted template).

- [ ] **Step 5: Verify nothing else regressed**

Run: `rtk proxy python -m pytest tests/ -q`
Expected: same green baseline as before the change (`$LASTEXITCODE` == 0).

- [ ] **Step 6: Commit**

```bash
rtk git add serial_admin.py serial_admin_ui.py tests/test_serial_admin_console.py
rtk git commit -m "refactor(console): extract vendor console template into serial_admin_ui.py"
```

---

### Task 2: Settings persistence + `/api/settings` routes

Add the single shared cloud-connection store: a `0600` `console_settings.json` next to the signing key, read/written through `GET`/`POST /api/settings`. The token is persisted **only** when `remember` is true.

**Files:**
- Modify: `serial_admin.py` (add `SETTINGS_FILE_ENV`, `_settings_path`, `_read_settings`, `_write_settings`, and the two routes — place after the `cloud_serials` route, before `INDEX_TEMPLATE`'s import usage / `index`)
- Modify: `.gitignore`
- Test: `tests/test_serial_admin_console.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_serial_admin_console.py`:

```python
import stat


def test_get_settings_default_when_no_file(vendor):
    body = vendor.get('/api/settings').get_json()
    assert body['cloud_url'] == serial_admin._BAKED_CLOUD_URL
    assert body['remember'] is False
    assert 'admin_token' not in body


def test_post_settings_remember_persists_token(vendor):
    r = vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': True})
    assert r.get_json()['success'] is True
    saved = json.loads(vendor.settings_path.read_text(encoding='utf-8'))
    assert saved == {'cloud_url': 'https://cloud.test', 'remember': True, 'admin_token': 'sek'}
    # GET returns the token back only because it was remembered
    got = vendor.get('/api/settings').get_json()
    assert got['admin_token'] == 'sek' and got['remember'] is True


def test_post_settings_no_remember_strips_token(vendor):
    vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': True})
    vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': False})
    saved = json.loads(vendor.settings_path.read_text(encoding='utf-8'))
    assert saved == {'cloud_url': 'https://cloud.test', 'remember': False}
    got = vendor.get('/api/settings').get_json()
    assert 'admin_token' not in got


def test_post_settings_chmod_0600(vendor, monkeypatch):
    """The settings file holds the admin token when remembered, so it must be
    written 0600. (chmod is a no-op on Windows, so assert the call, not the bits.)"""
    seen = {}
    real_chmod = os.chmod
    monkeypatch.setattr(serial_admin.os, 'chmod',
                        lambda p, m: seen.update(mode=m) or real_chmod(p, m))
    vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': True})
    assert seen.get('mode') == 0o600


def test_get_settings_unreadable_file_returns_default(vendor):
    vendor.settings_path.write_text('not valid json {{{', encoding='utf-8')
    body = vendor.get('/api/settings').get_json()
    assert body['cloud_url'] == serial_admin._BAKED_CLOUD_URL
    assert body['remember'] is False


def test_settings_loopback_guarded(vendor):
    assert vendor.get('/api/settings',
                      environ_overrides={'REMOTE_ADDR': '203.0.113.9'}).status_code == 403
    assert vendor.post('/api/settings', json={'cloud_url': 'x', 'remember': False},
                       environ_overrides={'REMOTE_ADDR': '203.0.113.9'}).status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k settings`
Expected: FAIL — `AttributeError: module 'serial_admin' has no attribute 'SETTINGS_FILE_ENV'` / 404 on `/api/settings`.

- [ ] **Step 3: Implement the settings helpers + routes**

In `serial_admin.py`, add the env constant next to `LEDGER_FILE_ENV` (line 31):

```python
LEDGER_FILE_ENV = 'CLINIC_MINT_LEDGER_FILE'
SETTINGS_FILE_ENV = 'CLINIC_CONSOLE_SETTINGS_FILE'
```

Then add, after the `cloud_serials` route (after line 400):

```python
# ── Console settings (single shared cloud connection) ─────────────────────────
# The cloud URL + admin token are entered once in Settings and reused by every
# cloud action. Session-only by default; persisted to a 0600 file next to the
# signing key ONLY when the vendor opts into "Remember on this machine". The
# token is never logged and only echoed back into the password field on rehydrate.

def _settings_path():
    override = os.environ.get(SETTINGS_FILE_ENV, '').strip()
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(KEY_FILE)), 'console_settings.json')


def _read_settings():
    """Return {cloud_url, remember, admin_token?}. Missing/unreadable/malformed
    file → baked default, not remembered. admin_token is present only when the
    file recorded remember=true."""
    try:
        with open(_settings_path(), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {'cloud_url': _BAKED_CLOUD_URL, 'remember': False}
    if not isinstance(data, dict):
        return {'cloud_url': _BAKED_CLOUD_URL, 'remember': False}
    out = {
        'cloud_url': str(data.get('cloud_url') or _BAKED_CLOUD_URL).strip(),
        'remember': bool(data.get('remember')),
    }
    if out['remember'] and data.get('admin_token'):
        out['admin_token'] = str(data.get('admin_token'))
    return out


def _write_settings(cloud_url, admin_token, remember):
    """Persist settings. remember=True → {cloud_url, remember, admin_token} at 0600;
    remember=False → {cloud_url, remember:false} (token dropped). Best-effort:
    returns (True, None) or (False, error_message) on a read-only profile."""
    payload = {'cloud_url': str(cloud_url or '').strip(), 'remember': bool(remember)}
    if remember and admin_token:
        payload['admin_token'] = str(admin_token)
    try:
        with open(_settings_path(), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh)
        try:
            os.chmod(_settings_path(), 0o600)
        except OSError:
            pass
        return True, None
    except OSError as exc:
        return False, str(exc)


@app.route('/api/settings')
def get_settings():
    return jsonify(_read_settings())


@app.route('/api/settings', methods=['POST'])
def post_settings():
    data = request.json or {}
    ok, err = _write_settings(data.get('cloud_url'), data.get('admin_token'),
                              bool(data.get('remember')))
    if not ok:
        return jsonify({'success': False, 'error': err})
    return jsonify({'success': True})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k settings`
Expected: PASS (all six settings tests green).

- [ ] **Step 5: Gitignore the settings file**

In `.gitignore`, under the "Generated license artefacts" block (after line 80 `minted_serials_history.csv`), add:

```
console_settings.json
```

- [ ] **Step 6: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_console.py .gitignore
rtk git commit -m "feat(console): single shared cloud connection via /api/settings (0600, opt-in remember)"
```

---

### Task 3: `POST /api/cloud/ping` (connection health)

Probe the cloud admin API and classify the result so the SPA can show a status dot and a "Test connection" result: reachable? authorized? serial count?

**Files:**
- Modify: `serial_admin.py` (add `cloud_ping` route after `post_settings`)
- Test: `tests/test_serial_admin_console.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_serial_admin_console.py`:

```python
import urllib.error


class _Resp:
    def __init__(self, body): self._b = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._b


def test_cloud_ping_authorized(vendor, monkeypatch):
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen',
                        lambda req, timeout=15: _Resp(b'{"serials": [], "count": 4}'))
    body = vendor.post('/api/cloud/ping',
                       json={'cloud_url': 'https://cloud.test', 'admin_token': 'sek'}).get_json()
    assert body == {'reachable': True, 'authorized': True, 'count': 4}


def test_cloud_ping_unauthorized(vendor, monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    body = vendor.post('/api/cloud/ping',
                       json={'cloud_url': 'https://cloud.test', 'admin_token': 'bad'}).get_json()
    assert body['reachable'] is True and body['authorized'] is False


def test_cloud_ping_unreachable(vendor, monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.URLError('no route to host')
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    body = vendor.post('/api/cloud/ping',
                       json={'cloud_url': 'https://cloud.test', 'admin_token': 'sek'}).get_json()
    assert body['reachable'] is False and body['authorized'] is False


def test_cloud_ping_requires_url(vendor):
    assert vendor.post('/api/cloud/ping', json={'admin_token': 'sek'}).status_code == 400


def test_cloud_ping_loopback_guarded(vendor):
    r = vendor.post('/api/cloud/ping', json={'cloud_url': 'x', 'admin_token': 't'},
                    environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k ping`
Expected: FAIL — 404 on `/api/cloud/ping`.

- [ ] **Step 3: Implement the ping route**

In `serial_admin.py`, after `post_settings`:

```python
@app.route('/api/cloud/ping', methods=['POST'])
def cloud_ping():
    """Probe the cloud admin API: reachable? authorized? serial count? Drives the
    Settings 'Test connection' button and the sidebar cloud status dot. Never
    raises — every failure maps to a clean reachable/authorized verdict."""
    data = request.json or {}
    cloud_url = str(data.get('cloud_url') or '').strip().rstrip('/')
    admin_token = str(data.get('admin_token') or '').strip()
    if not cloud_url:
        return jsonify({'reachable': False, 'authorized': False,
                        'error': 'cloud_url is required'}), 400
    try:
        req = urllib.request.Request(
            f'{cloud_url}/api/license/admin/serials', method='GET',
            headers={'X-Admin-Token': admin_token})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode('utf-8') or '{}')
        return jsonify({'reachable': True, 'authorized': True,
                        'count': int(body.get('count') or 0)})
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return jsonify({'reachable': True, 'authorized': False})
        return jsonify({'reachable': True, 'authorized': False, 'error': f'HTTP {exc.code}'})
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return jsonify({'reachable': False, 'authorized': False, 'error': str(exc)})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k ping`
Expected: PASS (five ping tests green).

- [ ] **Step 5: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_console.py
rtk git commit -m "feat(console): /api/cloud/ping connection-health probe"
```

---

### Task 4: `POST /api/cloud/revoke` (status change proxy)

Proxy the cloud's `POST /api/license/admin/revoke` so the console can revoke / suspend / re-activate a serial. Map cloud 401 to a clear "admin token rejected" message.

**Files:**
- Modify: `serial_admin.py` (add `cloud_revoke` route after `cloud_ping`)
- Test: `tests/test_serial_admin_console.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_serial_admin_console.py`:

```python
def test_cloud_revoke_success(vendor, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=15):
        seen['url'] = req.full_url
        seen['admin'] = req.headers.get('X-admin-token')
        seen['body'] = json.loads(req.data.decode('utf-8'))
        return _Resp(b'{"success": true}')

    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', fake_urlopen)
    body = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'https://cloud.test/', 'admin_token': 'sek',
        'serial': 'dental-khk-clini-00001', 'status': 'revoked'}).get_json()
    assert body['success'] is True
    assert seen['url'] == 'https://cloud.test/api/license/admin/revoke'
    assert seen['admin'] == 'sek'
    assert seen['body'] == {'serial': 'DENTAL-KHK-CLINI-00001', 'status': 'revoked'}


def test_cloud_revoke_maps_401(vendor, monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    body = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'bad',
        'serial': 'DENTAL-X-0001', 'status': 'revoked'}).get_json()
    assert body['success'] is False
    assert body['error'] == 'admin token rejected'


def test_cloud_revoke_validates_fields(vendor):
    assert vendor.post('/api/cloud/revoke', json={
        'admin_token': 't', 'serial': 'DENTAL-X-0001', 'status': 'revoked'}).status_code == 400
    assert vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'serial': 'DENTAL-X-0001', 'status': 'revoked'}).status_code == 400
    assert vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'admin_token': 't', 'status': 'revoked'}).status_code == 400
    assert vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'admin_token': 't', 'serial': 'DENTAL-X-0001',
        'status': 'nonsense'}).status_code == 400


def test_cloud_revoke_loopback_guarded(vendor):
    r = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'admin_token': 't', 'serial': 'DENTAL-X-0001', 'status': 'revoked'},
        environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k revoke`
Expected: FAIL — 404 on `/api/cloud/revoke`.

- [ ] **Step 3: Implement the revoke route**

In `serial_admin.py`, after `cloud_ping`:

```python
@app.route('/api/cloud/revoke', methods=['POST'])
def cloud_revoke():
    """Proxy the cloud's admin status-change endpoint so the vendor can revoke,
    suspend, or re-activate a serial. Maps cloud 401 to a clear message; never
    raises. Returns 400 only for missing/invalid local input."""
    data = request.json or {}
    cloud_url = str(data.get('cloud_url') or '').strip().rstrip('/')
    admin_token = str(data.get('admin_token') or '').strip()
    serial = str(data.get('serial') or '').strip().upper()
    status = str(data.get('status') or '').strip()
    if not cloud_url:
        return jsonify({'success': False, 'error': 'cloud_url is required'}), 400
    if not admin_token:
        return jsonify({'success': False, 'error': 'admin_token is required'}), 400
    if not serial:
        return jsonify({'success': False, 'error': 'serial is required'}), 400
    if status not in ('active', 'revoked', 'suspended'):
        return jsonify({'success': False, 'error': 'invalid status'}), 400
    try:
        payload = json.dumps({'serial': serial, 'status': status}).encode('utf-8')
        req = urllib.request.Request(
            f'{cloud_url}/api/license/admin/revoke', data=payload, method='POST',
            headers={'Content-Type': 'application/json', 'X-Admin-Token': admin_token})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode('utf-8') or '{}')
        return jsonify({'success': bool(body.get('success'))})
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return jsonify({'success': False, 'error': 'admin token rejected'})
        try:
            msg = json.loads(exc.read().decode('utf-8') or '{}').get('error') or f'HTTP {exc.code}'
        except (ValueError, OSError):
            msg = f'HTTP {exc.code}'
        return jsonify({'success': False, 'error': msg})
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return jsonify({'success': False, 'error': f'Could not reach the cloud node: {exc}'})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k revoke`
Expected: PASS (four revoke tests green).

- [ ] **Step 5: Commit**

```bash
rtk git add serial_admin.py tests/test_serial_admin_console.py
rtk git commit -m "feat(console): /api/cloud/revoke status-change proxy (revoke/suspend/reactivate)"
```

---

### Task 5: Frontend shell — design system, router, JS core, Settings view

Replace the body of `INDEX_TEMPLATE` with the new enterprise-light SPA: sidebar + main, the design-token CSS, the JS core (`api`/`toast`/`showView`/`conn`/settings rehydrate/`pingCloud`/key status), and a working **Settings** view. Dashboard / Issue / Licenses sections exist as empty placeholders that Tasks 6-7 fill.

**Files:**
- Modify: `serial_admin_ui.py` (rewrite `INDEX_TEMPLATE`)
- Modify: `tests/test_serial_admin_console.py` (remove the xfail from `test_index_renders_with_four_views`)

- [ ] **Step 1: Remove the xfail marker**

In `tests/test_serial_admin_console.py`, delete the `@pytest.mark.xfail(...)` decorator above `test_index_renders_with_four_views` so it becomes a real (currently failing) assertion that the four views exist.

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py::test_index_renders_with_four_views -q`
Expected: FAIL — the old template has no `id="view-*"`.

- [ ] **Step 3: Rewrite `INDEX_TEMPLATE` — head + design system + shell**

Replace the whole `INDEX_TEMPLATE = r'''...'''` in `serial_admin_ui.py` with the structure below. Begin with the head, the CSS design system (tokens from the spec, plus components), and the app shell:

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DentaCare — License Console</title>
<style>
  :root{
    --bg:#f6f8fb; --surface:#ffffff; --line:#e3e9f0; --ink:#16212e; --muted:#64748b;
    --brand:#0f6d7b; --accent:#13b5a7; --ok:#1f9d6b; --warn:#c2410c; --danger:#dc2626;
    --radius:12px; --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.10);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif}
  .app{display:flex;min-height:100vh}
  .sidebar{width:230px;flex:0 0 230px;background:var(--surface);border-right:1px solid var(--line);
           display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
  .brand{display:flex;align-items:center;gap:10px;padding:18px 18px 14px;font-weight:700}
  .brand .dot{width:10px;height:10px;border-radius:50%;background:var(--accent)}
  .brand small{display:block;font-weight:500;color:var(--muted);font-size:.72rem;letter-spacing:.4px}
  nav.nav{display:flex;flex-direction:column;gap:2px;padding:8px}
  .nav a{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;
         color:var(--ink);text-decoration:none;font-size:.9rem;cursor:pointer}
  .nav a:hover{background:#eef3f8}
  .nav a.active{background:var(--brand);color:#fff}
  .sidebar .foot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--line);
                 font-size:.78rem;color:var(--muted);display:flex;flex-direction:column;gap:6px}
  .statusdot{display:inline-flex;align-items:center;gap:7px}
  .statusdot .d{width:9px;height:9px;border-radius:50%;background:var(--muted)}
  .statusdot.ok .d{background:var(--ok)} .statusdot.bad .d{background:var(--danger)}
  .statusdot.warn .d{background:var(--warn)}
  .content{flex:1;min-width:0;padding:26px 30px;max-width:1100px}
  .view[hidden]{display:none}
  .page-h{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 18px}
  .page-h h1{font-size:1.35rem;margin:0} .page-h p{margin:2px 0 0;color:var(--muted);font-size:.88rem}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
        box-shadow:var(--shadow);padding:18px}
  .grid{display:grid;gap:16px}
  @media(min-width:680px){.grid-2{grid-template-columns:1fr 1fr}.grid-3{grid-template-columns:repeat(3,1fr)}}
  .stat{display:flex;flex-direction:column;gap:4px}
  .stat .n{font-size:1.9rem;font-weight:700;line-height:1}
  .stat .l{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.5px}
  label{display:block;font-size:.82rem;color:var(--muted);margin:12px 0 4px}
  input,select,textarea{width:100%;background:#fff;color:var(--ink);border:1px solid var(--line);
    border-radius:9px;padding:9px 11px;font:inherit}
  input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:var(--accent)}
  textarea{min-height:84px;font-family:ui-monospace,monospace}
  .btn{display:inline-flex;align-items:center;gap:7px;background:var(--brand);color:#fff;border:0;
       border-radius:9px;padding:10px 16px;font:inherit;font-weight:600;cursor:pointer}
  .btn:hover{filter:brightness(1.06)} .btn:disabled{opacity:.55;cursor:not-allowed}
  .btn.secondary{background:transparent;color:var(--ink);border:1px solid var(--line)}
  .btn.danger{background:var(--danger)} .btn.sm{padding:5px 10px;font-size:.8rem;font-weight:600}
  .row-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:14px}
  .mono{font-family:ui-monospace,monospace}
  .muted{color:var(--muted)} .field-err{color:var(--danger);font-size:.78rem;margin-top:4px}
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.74rem;font-weight:600;
         border:1px solid transparent}
  .badge.active{background:#e7f6ef;color:var(--ok);border-color:#bfe6d3}
  .badge.revoked{background:#fdeaea;color:var(--danger);border-color:#f4c5c5}
  .badge.suspended{background:#fdeede;color:var(--warn);border-color:#f3d4a8}
  .badge.expired{background:#eef1f5;color:var(--muted);border-color:var(--line)}
  .badge.local{background:#eef1f5;color:#475569;border-color:var(--line)}
  .badge.published{background:#e6f6f4;color:var(--brand);border-color:#bfe6e0}
  table{width:100%;border-collapse:collapse;margin-top:4px}
  thead th{position:sticky;top:0;background:var(--surface);text-align:left;padding:10px;
           font-size:.74rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);
           border-bottom:1px solid var(--line)}
  tbody td{padding:10px;border-bottom:1px solid var(--line);font-size:.86rem;vertical-align:middle}
  tbody tr:hover{background:#f9fbfd}
  .bar{height:6px;border-radius:4px;background:#eef1f5;overflow:hidden;min-width:60px}
  .bar > i{display:block;height:100%;background:var(--accent)}
  .chips{display:flex;gap:7px;flex-wrap:wrap;margin:6px 0 14px}
  .chip{padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;
        font-size:.8rem;cursor:pointer;color:var(--muted)}
  .chip.on{background:var(--brand);color:#fff;border-color:var(--brand)}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
  .toolbar input[type=search]{max-width:300px}
  .empty{text-align:center;color:var(--muted);padding:40px 16px}
  .table-wrap{overflow-x:auto}
  .toasts{position:fixed;right:18px;bottom:18px;display:flex;flex-direction:column;gap:10px;z-index:50}
  .toast{background:var(--ink);color:#fff;padding:11px 15px;border-radius:10px;box-shadow:var(--shadow);
         font-size:.86rem;max-width:340px;animation:slidein .18s ease-out}
  .toast.ok{background:#0d3b2e} .toast.err{background:#5b1414}
  @keyframes slidein{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}
  .drawer{position:fixed;inset:0;background:rgba(16,24,40,.34);display:flex;justify-content:flex-end;z-index:40}
  .drawer[hidden]{display:none}
  .drawer .panel{width:min(440px,92vw);background:var(--surface);height:100%;padding:22px;overflow:auto;box-shadow:var(--shadow)}
  .drawer dl{display:grid;grid-template-columns:auto 1fr;gap:8px 14px;font-size:.85rem;margin:14px 0}
  .drawer dt{color:var(--muted)} .drawer dd{margin:0;word-break:break-all}
  @media(max-width:760px){
    .app{flex-direction:column}
    .sidebar{width:100%;height:auto;flex:none;position:static;flex-direction:row;flex-wrap:wrap;align-items:center}
    nav.nav{flex-direction:row;flex:1} .sidebar .foot{margin:0;border:0;flex-direction:row;gap:14px}
    .content{padding:18px}
  }
</style></head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand"><span class="dot"></span><div>DentaCare<small>License Console</small></div></div>
    <nav class="nav" id="nav">
      <a data-view="dashboard" class="active" onclick="showView('dashboard')">Dashboard</a>
      <a data-view="issue" onclick="showView('issue')">Issue serials</a>
      <a data-view="licenses" onclick="showView('licenses')">Licenses</a>
      <a data-view="settings" onclick="showView('settings')">Settings</a>
    </nav>
    <div class="foot">
      <span class="statusdot" id="dot-key"><span class="d"></span><span id="dot-key-t">Key…</span></span>
      <span class="statusdot" id="dot-cloud"><span class="d"></span><span id="dot-cloud-t">Cloud…</span></span>
      <span style="opacity:.7">loopback only</span>
    </div>
  </aside>
  <main class="content">
    <section id="view-dashboard" class="view"></section>
    <section id="view-issue" class="view" hidden></section>
    <section id="view-licenses" class="view" hidden></section>
    <section id="view-settings" class="view" hidden></section>
  </main>
</div>
<div class="toasts" id="toasts"></div>
<div class="drawer" id="drawer" hidden onclick="if(event.target===this)closeDrawer()">
  <div class="panel" id="drawer-panel"></div>
</div>
<script>
/* JS CORE — Task 5 */
const state = { conn:{cloud_url:'', admin_token:''}, remember:false,
                key:{has_key:false}, cloud:{reachable:false, authorized:false, count:0},
                history:[], registry:[] };

function el(id){ return document.getElementById(id); }
function fmtDate(s){ return s ? String(s).slice(0,10) : ''; }
function esc(s){ const d=document.createElement('div'); d.textContent = s==null?'':String(s); return d.innerHTML; }

function toast(msg, kind){
  const t = document.createElement('div');
  t.className = 'toast ' + (kind==='err'?'err':kind==='ok'?'ok':'');
  t.textContent = msg;
  el('toasts').appendChild(t);
  setTimeout(()=>{ t.remove(); }, 4200);
}

async function api(path, opts){
  try{
    const res = await fetch(path, opts);
    let body = {};
    try{ body = await res.json(); }catch(e){ body = {}; }
    return { ok: res.ok, status: res.status, body };
  }catch(e){
    return { ok:false, status:0, body:{ error:'Network error: ' + e } };
  }
}
function jsonPost(payload){
  return { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) };
}

const VIEW_LOADERS = {
  dashboard: loadDashboard, issue: loadIssue, licenses: loadLicenses, settings: loadSettingsView
};
function showView(name){
  for(const sec of document.querySelectorAll('.view')) sec.hidden = (sec.id !== 'view-'+name);
  for(const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.view===name);
  (VIEW_LOADERS[name] || function(){})();
}

function connReady(){ return !!(state.conn.cloud_url && state.conn.admin_token); }
function requireConn(){
  if(connReady()) return true;
  toast('Connect to the cloud in Settings first.', 'err');
  showView('settings');
  return false;
}

/* settings rehydrate + cloud status */
async function loadSettings(){
  const { body } = await api('/api/settings');
  state.conn.cloud_url = body.cloud_url || '';
  state.remember = !!body.remember;
  if(body.admin_token) state.conn.admin_token = body.admin_token;
  if(connReady()) pingCloud();
  else setCloudDot(false, false);
}
function setCloudDot(reachable, authorized, count){
  const dot = el('dot-cloud'), t = el('dot-cloud-t');
  dot.className = 'statusdot ' + (authorized ? 'ok' : reachable ? 'warn' : 'bad');
  t.textContent = authorized ? ('Cloud · ' + (count||0)) : reachable ? 'Cloud · unauthorized' : 'Cloud · offline';
}
async function pingCloud(){
  const { body } = await api('/api/cloud/ping', jsonPost(state.conn));
  state.cloud = { reachable:!!body.reachable, authorized:!!body.authorized, count:body.count||0 };
  setCloudDot(state.cloud.reachable, state.cloud.authorized, state.cloud.count);
  return state.cloud;
}

/* signing key */
async function refreshKey(){
  const { body } = await api('/api/key/status');
  state.key = body;
  const dot = el('dot-key'), t = el('dot-key-t');
  dot.className = 'statusdot ' + (body.has_key ? 'ok' : 'warn');
  t.textContent = body.has_key ? 'Key loaded' : 'No key';
}
async function generateKey(){
  const exists = state.key && state.key.has_key;
  if(exists && !confirm('Rotating the key invalidates every serial already issued. Continue?')) return;
  const { ok, body } = await api('/api/key/generate', jsonPost({ confirm_overwrite: exists }));
  if(!ok){ toast(body.error || 'Could not generate a key.', 'err'); return; }
  toast('Signing key ready.', 'ok');
  await refreshKey();
  if(!document.getElementById('view-settings').hidden) loadSettingsView();
}

document.addEventListener('DOMContentLoaded', async ()=>{
  await refreshKey();
  await loadSettings();
  showView('dashboard');
});
</script>
</body></html>
```

- [ ] **Step 4: Append the Settings view render to the `<script>` (before `</script>`)**

Add these functions inside the same `<script>` block (just before the `document.addEventListener('DOMContentLoaded'...` line). This renders and wires the Settings view, plus stubs the other three loaders so the router never calls an undefined function:

```javascript
/* ---- Settings view ---- */
function loadSettingsView(){
  const keyBlock = state.key && state.key.has_key
    ? '<div class="muted">Key loaded.</div>'
      + '<label>Public key</label><div class="mono" style="word-break:break-all;font-size:.8rem">'
        + esc(state.key.public_key||'') + '</div>'
      + '<div class="row-actions"><button class="btn secondary" onclick="copyText(this,\'' + esc(state.key.public_key||'') + '\')">Copy public key</button>'
      + '<button class="btn secondary" onclick="generateKey()">Rotate keypair</button></div>'
      + '<div class="field-err">Rotating invalidates every serial already issued.</div>'
    : '<div class="muted">No signing key yet — generate one to start minting.</div>'
      + '<div class="row-actions"><button class="btn" onclick="generateKey()">Generate keypair</button></div>';
  el('view-settings').innerHTML =
    '<div class="page-h"><div><h1>Settings</h1><p>Signing key and the shared cloud connection.</p></div></div>'
    + '<div class="grid grid-2">'
    + '  <div class="card"><h3 style="margin-top:0">Signing key</h3>' + keyBlock + '</div>'
    + '  <div class="card"><h3 style="margin-top:0">Cloud connection</h3>'
    + '    <label>Cloud URL</label><input id="s-url" value="' + esc(state.conn.cloud_url) + '">'
    + '    <label>Admin token (X-Admin-Token)</label><input id="s-token" type="password" placeholder="CLINIC_ADMIN_API_TOKEN" value="' + esc(state.conn.admin_token) + '">'
    + '    <label style="display:flex;gap:8px;align-items:center;margin-top:12px;color:var(--ink)">'
    + '      <input type="checkbox" id="s-remember" style="width:auto" ' + (state.remember?'checked':'') + '> Remember on this machine</label>'
    + '    <div class="muted" style="font-size:.78rem">Saves the token to a 0600 file next to your signing key. Leave off to keep it in memory for this session only.</div>'
    + '    <div class="row-actions"><button class="btn" onclick="saveSettings()">Save</button>'
    + '      <button class="btn secondary" onclick="testConnection(this)">Test connection</button>'
    + '      <span id="s-conn" class="muted" style="font-size:.84rem"></span></div>'
    + '  </div>'
    + '</div>'
    + '<div class="card" style="margin-top:16px"><h3 style="margin-top:0">Security</h3>'
    + '  <ul class="muted" style="font-size:.85rem;margin:0;padding-left:18px">'
    + '    <li>The private signing seed never leaves this machine.</li>'
    + '    <li>Activation codes are secrets — don\'t commit the CSV/JSON you download.</li>'
    + '    <li>The settings file is 0600 and gitignored.</li></ul></div>';
}
function readSettingsForm(){
  state.conn.cloud_url = el('s-url').value.trim();
  state.conn.admin_token = el('s-token').value.trim();
  state.remember = el('s-remember').checked;
}
async function saveSettings(){
  readSettingsForm();
  const { body } = await api('/api/settings', jsonPost({
    cloud_url: state.conn.cloud_url, admin_token: state.conn.admin_token, remember: state.remember }));
  if(body.success){ toast('Settings saved.', 'ok'); pingCloud(); }
  else toast(body.error || 'Could not save settings.', 'err');
}
async function testConnection(btn){
  readSettingsForm();
  const out = el('s-conn');
  if(!state.conn.cloud_url){ out.textContent = 'Enter a cloud URL first.'; return; }
  btn.disabled = true; out.textContent = 'Testing…';
  const c = await pingCloud();
  btn.disabled = false;
  out.textContent = c.authorized ? ('Connected — ' + c.count + ' serial(s).')
    : c.reachable ? 'Reachable, but the admin token was rejected.'
    : 'Could not reach the cloud node.';
}
function copyText(btn, text){
  navigator.clipboard.writeText(text||'').then(()=>{ const o=btn.textContent; btn.textContent='Copied!';
    setTimeout(()=>btn.textContent=o, 1600); });
}
function closeDrawer(){ el('drawer').hidden = true; }

/* placeholder loaders — replaced in Tasks 6 & 7 */
function loadDashboard(){ el('view-dashboard').innerHTML = '<div class="page-h"><h1>Dashboard</h1></div><div class="card empty">Coming up next.</div>'; }
function loadIssue(){ el('view-issue').innerHTML = '<div class="page-h"><h1>Issue serials</h1></div><div class="card empty">Coming up next.</div>'; }
function loadLicenses(){ el('view-licenses').innerHTML = '<div class="page-h"><h1>Licenses</h1></div><div class="card empty">Coming up next.</div>'; }
```

- [ ] **Step 5: Run the render + sanity tests**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k "views or valid_js"`
Expected: PASS — four views present; `node --check` accepts the inline script (no bare-`\n` breakage).

- [ ] **Step 6: Manual smoke (optional but recommended)**

Run: `python serial_admin.py` then open `http://127.0.0.1:8787`. Confirm: sidebar nav switches views, Settings shows key + connection, "Test connection" reports a verdict, the cloud dot updates. Ctrl+C to stop.

- [ ] **Step 7: Commit**

```bash
rtk git add serial_admin_ui.py tests/test_serial_admin_console.py
rtk git commit -m "feat(console): enterprise-light SPA shell, router, JS core, and Settings view"
```

---

### Task 6: Dashboard + Issue views

Fill the Dashboard (stat cards + recent serials + quick actions + empty state) and the Issue view (guided mint form with inline validation, results card with copy/download, publish-all using the shared `conn`).

**Files:**
- Modify: `serial_admin_ui.py` (replace the `loadDashboard` and `loadIssue` placeholder functions)
- Test: `tests/test_serial_admin_console.py`

- [ ] **Step 1: Write a failing render-marker test**

Add to `tests/test_serial_admin_console.py`:

```python
def test_issue_and_dashboard_markup_present(vendor):
    html = vendor.get('/').get_data(as_text=True)
    # Issue form field ids the JS builds against must exist in the served template
    # OR be created by JS we can't run here — so assert the loader functions exist.
    for fn in ('function loadDashboard', 'function loadIssue', 'function mint(',
               'function publishAll(', 'function downloadCsv(', 'function validateIssue('):
        assert fn in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py::test_issue_and_dashboard_markup_present -q`
Expected: FAIL — `mint(`, `publishAll(`, `validateIssue(` not yet defined.

- [ ] **Step 3: Replace `loadDashboard` with the real dashboard**

In `serial_admin_ui.py`, replace the placeholder `function loadDashboard(){...}` with:

```javascript
async function loadDashboard(){
  const { body } = await api('/api/history');
  state.history = (body && body.records) || [];
  const total = state.history.length;
  const published = state.history.filter(r=>r.published).length;
  const local = total - published;
  const keyTxt = state.key && state.key.has_key ? 'Loaded' : 'None';
  const cloudTxt = state.cloud.authorized ? ('Connected · ' + state.cloud.count)
                 : state.cloud.reachable ? 'Unauthorized' : 'Offline';
  const recent = state.history.slice(0,5);
  const recentRows = recent.map(r=>
    '<tr><td class="mono">' + esc(r.serial) + '</td><td>' + esc(r.clinic_name||'') + '</td>'
    + '<td>' + statusBadge(r.published?'published':'local') + '</td>'
    + '<td>' + fmtDate(r.expires_at) + '</td></tr>').join('');
  const recentBlock = total
    ? '<div class="card table-wrap"><h3 style="margin-top:0">Recent serials</h3><table>'
      + '<thead><tr><th>Serial</th><th>Clinic</th><th>Status</th><th>Expires</th></tr></thead>'
      + '<tbody>' + recentRows + '</tbody></table></div>'
    : '<div class="card empty"><h3>No serials yet</h3><p>Mint your first serial to get started.</p>'
      + '<button class="btn" onclick="showView(\'issue\')">Issue serials</button></div>';
  el('view-dashboard').innerHTML =
    '<div class="page-h"><div><h1>Dashboard</h1><p>Issued and published serials on this machine.</p></div>'
    + '<div class="row-actions" style="margin:0"><button class="btn" onclick="showView(\'issue\')">Issue serials</button>'
    + '<button class="btn secondary" onclick="showView(\'licenses\')">View licenses</button></div></div>'
    + '<div class="grid grid-3" style="margin-bottom:16px">'
    + statCard(total, 'Issued') + statCard(published, 'Published') + statCard(local, 'Local-only')
    + '</div>'
    + '<div class="grid grid-2" style="margin-bottom:16px">'
    + '<div class="card stat"><span class="l">Signing key</span><span class="n" style="font-size:1.2rem">' + keyTxt + '</span></div>'
    + '<div class="card stat"><span class="l">Cloud</span><span class="n" style="font-size:1.2rem">' + cloudTxt + '</span></div>'
    + '</div>'
    + recentBlock;
}
function statCard(n, label){
  return '<div class="card stat"><span class="n">' + n + '</span><span class="l">' + label + '</span></div>';
}
function statusBadge(kind){
  const map = { active:'active', revoked:'revoked', suspended:'suspended', expired:'expired',
                local:'local', published:'published' };
  const cls = map[kind] || 'local';
  const txt = kind==='local' ? 'local only' : kind;
  return '<span class="badge ' + cls + '">' + txt + '</span>';
}
```

- [ ] **Step 4: Replace `loadIssue` with the real guided-mint view**

Replace the placeholder `function loadIssue(){...}` with:

```javascript
let lastRecords = [];
function loadIssue(){
  el('view-issue').innerHTML =
    '<div class="page-h"><div><h1>Issue serials</h1><p>Mint signed serials for a clinic and publish them for short-serial activation.</p></div></div>'
    + '<div class="card">'
    + '  <div class="grid grid-2">'
    + '    <div><label>Clinic name</label><input id="m-name" placeholder="Smile Dental"><div class="field-err" id="e-name" hidden></div></div>'
    + '    <div><label>Clinic code (≤4)</label><input id="m-code" maxlength="4" placeholder="SMD"><div class="field-err" id="e-code" hidden></div></div>'
    + '    <div><label>Plan</label><select id="m-plan"><option>Standard</option><option>Premium</option><option>Enterprise</option></select></div>'
    + '    <div><label>Expiry (days)</label><input id="m-expiry" type="number" value="365"></div>'
    + '    <div><label>Max devices</label><input id="m-max" type="number" value="3"></div>'
    + '  </div>'
    + '  <label>Device IDs (one per line — blank = one clinic-level serial)</label>'
    + '  <textarea id="m-devices" placeholder="LAPTOP-01&#10;PHONE-02"></textarea>'
    + '  <div class="row-actions"><button class="btn" onclick="mint()">Mint serials</button></div>'
    + '  <div class="muted" style="font-size:.8rem;margin-top:8px">Give the clinic owner the <b>Serial Number</b> — they type it in the app to activate online. The full Activation Code is the offline fallback.</div>'
    + '</div>'
    + '<div id="results" style="margin-top:16px"></div>';
}
function validateIssue(b){
  let ok = true;
  const setErr = (id, msg)=>{ const e=el(id); e.hidden=!msg; e.textContent=msg||''; if(msg) ok=false; };
  setErr('e-name', b.clinic_name ? '' : 'Clinic name is required.');
  setErr('e-code', (b.clinic_code && b.clinic_code.length<=4) ? '' : 'Clinic code is required (1–4 characters).');
  return ok;
}
function collectIssue(){
  return {
    clinic_name: el('m-name').value.trim(),
    clinic_code: el('m-code').value.trim(),
    plan_name: el('m-plan').value,
    expiry_days: parseInt(el('m-expiry').value || '365', 10),
    max_devices: parseInt(el('m-max').value || '1', 10),
    devices: el('m-devices').value
  };
}
async function mint(){
  const b = collectIssue();
  if(!validateIssue(b)) return;
  const { ok, body } = await api('/api/mint', jsonPost(b));
  if(!ok){ toast(body.error || 'Mint failed.', 'err'); return; }
  lastRecords = body.records || [];
  renderResults();
  toast('Minted ' + lastRecords.length + ' serial(s).', 'ok');
}
function renderResults(){
  if(!lastRecords.length){ el('results').innerHTML = ''; return; }
  const rows = lastRecords.map((r,i)=>
    '<tr><td class="mono">' + esc(r.serial) + '</td><td>' + fmtDate(r.expires_at) + '</td>'
    + '<td><button class="btn secondary sm" onclick="copyText(this,' + jsArg(r.serial) + ')">Copy serial</button> '
    + '<button class="btn secondary sm" onclick="copyText(this,' + jsArg(r.offline_token) + ')">Copy activation code</button></td></tr>').join('');
  el('results').innerHTML =
    '<div class="card table-wrap"><div class="toolbar"><h3 style="margin:0;flex:1">Results</h3>'
    + '<button class="btn secondary sm" onclick="downloadJson()">Download JSON</button>'
    + '<button class="btn secondary sm" onclick="downloadCsv()">Download CSV</button>'
    + '<button class="btn sm" onclick="publishAll(this)">Publish all to cloud</button></div>'
    + '<table><thead><tr><th>Serial number</th><th>Expires</th><th>Actions</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
}
function jsArg(s){ return JSON.stringify(String(s==null?'':s)).replace(/&/g,'&amp;').replace(/"/g,'&quot;'); }  /* JSON-encode for the JS layer, then HTML-encode &/" so the result is safe spliced inside a double-quoted onclick="..." attribute — the browser decodes &quot; back to " before the handler runs. Used by mint-results AND licenses row buttons. */
async function publishAll(btn){
  if(!lastRecords.length){ toast('Mint serials first.', 'err'); return; }
  if(!requireConn()) return;
  btn.disabled = true; btn.textContent = 'Publishing…';
  const { ok, body } = await api('/api/upload-cloud', jsonPost(Object.assign(
    { records: lastRecords }, state.conn)));
  btn.disabled = false; btn.textContent = 'Publish all to cloud';
  if(!ok){ toast(body.error || 'Upload failed.', 'err'); return; }
  const fails = (body.results || []).filter(r=>!r.ok);
  toast('Published ' + body.ok_count + '/' + body.total + ' serial(s).' + (fails.length?' Some failed.':''),
        fails.length ? 'err' : 'ok');
  pingCloud();
}
function _download(name, type, text){
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}
function downloadJson(){ _download('serials.json', 'application/json', JSON.stringify(lastRecords, null, 2)); }
function downloadCsv(){
  const head = ['Serial','Device ID','Plan','Max Devices','Issued At','Expires At','Offline Token'];
  const rows = lastRecords.map(r=>[r.serial,r.device_id,r.plan_name,r.max_devices,r.issued_at,r.expires_at,r.offline_token]);
  const csv = [head].concat(rows).map(c=>c.map(x=>'"'+String(x==null?'':x).replace(/"/g,'""')+'"').join(',')).join('\r\n');
  _download('serials.csv', 'text/csv', csv);
}
```

- [ ] **Step 5: Run the marker test + sanity**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q -k "markup or valid_js"`
Expected: PASS — loader/`mint`/`publishAll`/`validateIssue`/`downloadCsv` present; `node --check` still accepts the script.

- [ ] **Step 6: Commit**

```bash
rtk git add serial_admin_ui.py tests/test_serial_admin_console.py
rtk git commit -m "feat(console): dashboard stats + guided issue/mint view with publish-all"
```

---

### Task 7: Licenses view (unified management)

The centerpiece: join the local ledger with the live cloud registry, render a searchable/filterable table with status badges + device usage, and wire row actions (copy code, publish, revoke/suspend/re-activate, details drawer). Cloud-dependent actions disabled when not connected.

**Files:**
- Modify: `serial_admin_ui.py` (replace the `loadLicenses` placeholder; add render/filter/action helpers)
- Test: `tests/test_serial_admin_console.py`

- [ ] **Step 1: Write a failing render-marker test**

Add to `tests/test_serial_admin_console.py`:

```python
def test_licenses_view_functions_present(vendor):
    html = vendor.get('/').get_data(as_text=True)
    for fn in ('function loadLicenses', 'function renderLicenses(', 'function joinLicenses(',
               'function licenseRowActions(', 'function revokeRow(', 'function publishRow(',
               'function openDetails(', 'function applyLicenseFilter('):
        assert fn in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py::test_licenses_view_functions_present -q`
Expected: FAIL — those functions are not defined yet.

- [ ] **Step 3: Replace `loadLicenses` and add the licenses helpers**

In `serial_admin_ui.py`, replace the placeholder `function loadLicenses(){...}` with the block below (the join, render, filter, and actions):

```javascript
let licenseState = { rows: [], filter: 'all', q: '' };

async function loadLicenses(){
  const hist = await api('/api/history');
  state.history = (hist.body && hist.body.records) || [];
  state.registry = [];
  if(connReady()){
    const reg = await api('/api/cloud/serials', jsonPost(state.conn));
    if(reg.ok) state.registry = (reg.body && reg.body.serials) || [];
    else toast(reg.body.error || 'Could not read the cloud registry.', 'err');
  }
  licenseState.rows = joinLicenses(state.history, state.registry);
  renderLicensesShell();
  applyLicenseFilter();
}
function joinLicenses(local, cloud){
  const bySerial = {};
  for(const r of local){
    bySerial[r.serial] = {
      serial:r.serial, clinic_name:r.clinic_name||'', plan_name:r.plan_name||'',
      max_devices:r.max_devices, used_devices:0, has_token:!!r.offline_token,
      offline_token:r.offline_token||'', expires_at:r.expires_at, issued_at:r.issued_at,
      status:null, source:'local'
    };
  }
  for(const c of cloud){
    const cur = bySerial[c.serial] || { serial:c.serial, offline_token:'', source:'cloud' };
    cur.clinic_name = cur.clinic_name || c.clinic_name || '';
    cur.plan_name = cur.plan_name || c.plan_name || '';
    cur.max_devices = (c.max_devices!=null) ? c.max_devices : cur.max_devices;
    cur.used_devices = c.used_devices || 0;
    cur.has_token = !!c.has_token || cur.has_token;
    cur.status = c.status || 'active';
    cur.expires_at = cur.expires_at || c.expires_at;
    cur.issued_at = cur.issued_at || c.issued_at;
    cur.grace_until = c.grace_until;
    cur.source = bySerial[c.serial] ? 'both' : 'cloud';
    bySerial[c.serial] = cur;
  }
  return Object.values(bySerial);
}
function effectiveStatus(r){
  if(r.status === 'revoked' || r.status === 'suspended') return r.status;
  if(r.expires_at && new Date(r.expires_at) < new Date()) return 'expired';
  if(r.status === 'active') return 'active';
  return 'local';   // local-only, never published
}
function renderLicensesShell(){
  const chips = ['all','published','local','active','revoked','suspended','expired'];
  const labels = { all:'All', published:'Published', local:'Local-only', active:'Active',
                   revoked:'Revoked', suspended:'Suspended', expired:'Expired' };
  el('view-licenses').innerHTML =
    '<div class="page-h"><div><h1>Licenses</h1><p>Local ledger joined with the live cloud registry.</p></div>'
    + '<div class="row-actions" style="margin:0"><button class="btn secondary" onclick="loadLicenses()">Refresh</button></div></div>'
    + (connReady() ? '' : '<div class="card" style="margin-bottom:14px;border-color:#f3d4a8;background:#fffaf2">'
        + '<b>Not connected to the cloud.</b> <span class="muted">Showing local serials only. Connect in '
        + '<a onclick="showView(\'settings\')" style="cursor:pointer;color:var(--brand)">Settings</a> to manage status and see device usage.</span></div>')
    + '<div class="toolbar"><input type="search" id="lic-q" placeholder="Search serial or clinic…" oninput="onLicenseSearch(this.value)"></div>'
    + '<div class="chips" id="lic-chips">' + chips.map(c=>
        '<span class="chip' + (licenseState.filter===c?' on':'') + '" onclick="setLicenseFilter(\'' + c + '\')">' + labels[c] + '</span>').join('') + '</div>'
    + '<div class="card table-wrap"><table><thead><tr>'
    + '<th>Serial</th><th>Clinic</th><th>Plan</th><th>Status</th><th>Devices</th><th>Short-serial</th><th>Expiry</th><th>Source</th><th></th>'
    + '</tr></thead><tbody id="lic-body"></tbody></table><div id="lic-empty"></div></div>';
}
function onLicenseSearch(v){ licenseState.q = (v||'').trim().toLowerCase(); applyLicenseFilter(); }
function setLicenseFilter(f){ licenseState.filter = f; renderLicensesShell(); el('lic-q').value = licenseState.q; applyLicenseFilter(); }
function applyLicenseFilter(){
  const f = licenseState.filter, q = licenseState.q;
  const rows = licenseState.rows.filter(r=>{
    const eff = effectiveStatus(r);
    const matchF = f==='all'
      || (f==='published' && (r.source==='both'||r.source==='cloud'))
      || (f==='local' && r.source==='local')
      || (f===eff);
    const matchQ = !q || (r.serial+' '+(r.clinic_name||'')).toLowerCase().includes(q);
    return matchF && matchQ;
  });
  renderLicenses(rows);
}
function renderLicenses(rows){
  const body = el('lic-body'), empty = el('lic-empty');
  if(!rows.length){
    body.innerHTML = '';
    empty.innerHTML = '<div class="empty">No serials match.</div>';
    return;
  }
  empty.innerHTML = '';
  body.innerHTML = rows.map(r=>{
    const eff = effectiveStatus(r);
    const max = r.max_devices || 0, used = r.used_devices || 0;
    const pct = max ? Math.min(100, Math.round(used/max*100)) : 0;
    const devCell = max
      ? '<div style="display:flex;align-items:center;gap:8px">' + used + '/' + max
        + '<span class="bar" style="flex:1"><i style="width:' + pct + '%"></i></span></div>'
      : '<span class="muted">—</span>';
    const src = r.source==='both' ? 'local + cloud' : r.source;
    return '<tr>'
      + '<td class="mono">' + esc(r.serial) + '</td>'
      + '<td>' + esc(r.clinic_name||'') + '</td>'
      + '<td>' + esc(r.plan_name||'') + '</td>'
      + '<td>' + statusBadge(eff) + '</td>'
      + '<td>' + devCell + '</td>'
      + '<td>' + (r.has_token ? '✓' : '<span class="muted">—</span>') + '</td>'
      + '<td>' + fmtDate(r.expires_at) + '</td>'
      + '<td class="muted">' + src + '</td>'
      + '<td style="text-align:right">' + licenseRowActions(r, eff) + '</td>'
      + '</tr>';
  }).join('');
}
function licenseRowActions(r, eff){
  const conn = connReady();
  const dis = conn ? '' : ' disabled title="Connect in Settings"';
  let btns = '';
  if(r.offline_token)
    btns += '<button class="btn secondary sm" onclick="copyText(this,' + jsArg(r.offline_token) + ')">Copy code</button> ';
  if(r.source==='local' && r.offline_token)
    btns += '<button class="btn sm" onclick="publishRow(' + jsArg(r.serial) + ', this)"' + dis + '>Publish</button> ';
  if(r.source!=='local'){
    if(eff==='active' || eff==='expired'){
      btns += '<button class="btn secondary sm" onclick="revokeRow(' + jsArg(r.serial) + ',\'suspended\',this)"' + dis + '>Suspend</button> ';
      btns += '<button class="btn danger sm" onclick="revokeRow(' + jsArg(r.serial) + ',\'revoked\',this)"' + dis + '>Revoke</button> ';
    } else {
      btns += '<button class="btn sm" onclick="revokeRow(' + jsArg(r.serial) + ',\'active\',this)"' + dis + '>Re-activate</button> ';
    }
  }
  btns += '<button class="btn secondary sm" onclick="openDetails(' + jsArg(r.serial) + ')">Details</button>';
  return btns;
}
async function publishRow(serial, btn){
  if(!requireConn()) return;
  const row = licenseState.rows.find(r=>r.serial===serial);
  if(!row || !row.offline_token){ toast('No activation code on file for this serial.', 'err'); return; }
  btn.disabled = true; btn.textContent = 'Publishing…';
  const { ok, body } = await api('/api/publish-token', jsonPost(Object.assign(
    { offline_token: row.offline_token }, state.conn)));
  if(!ok || !(body.result && body.result.ok)){
    toast(body.error || (body.result && body.result.error) || 'Publish failed.', 'err');
    btn.disabled = false; btn.textContent = 'Publish'; return;
  }
  toast('Published ' + serial + '.', 'ok');
  loadLicenses();
}
async function revokeRow(serial, status, btn){
  if(!requireConn()) return;
  const verb = status==='revoked' ? 'revoke' : status==='suspended' ? 'suspend' : 're-activate';
  if((status==='revoked' || status==='suspended') && !confirm('Really ' + verb + ' ' + serial + '?')) return;
  btn.disabled = true;
  const { body } = await api('/api/cloud/revoke', jsonPost(Object.assign(
    { serial, status }, state.conn)));
  if(!body.success){ toast(body.error || (verb + ' failed.'), 'err'); btn.disabled = false; return; }
  toast(serial + ' → ' + status + '.', 'ok');
  loadLicenses();
}
function openDetails(serial){
  const r = licenseState.rows.find(x=>x.serial===serial);
  if(!r) return;
  const row = (k,v)=> '<dt>' + k + '</dt><dd>' + esc(v==null||v===''?'—':v) + '</dd>';
  el('drawer-panel').innerHTML =
    '<div class="toolbar"><h3 style="margin:0;flex:1">Serial details</h3>'
    + '<button class="btn secondary sm" onclick="closeDrawer()">Close</button></div>'
    + '<div class="mono" style="word-break:break-all;font-weight:600">' + esc(r.serial) + '</div>'
    + '<dl>'
    + row('Clinic', r.clinic_name) + row('Plan', r.plan_name)
    + row('Status', effectiveStatus(r)) + row('Source', r.source)
    + row('Devices', (r.max_devices? (r.used_devices||0)+' / '+r.max_devices : '—'))
    + row('Short-serial ready', r.has_token ? 'yes' : 'no')
    + row('Issued', fmtDate(r.issued_at)) + row('Expires', fmtDate(r.expires_at))
    + row('Grace until', fmtDate(r.grace_until))
    + '</dl>'
    + (r.offline_token ? '<button class="btn secondary sm" onclick="copyText(this,' + jsArg(r.offline_token) + ')">Copy activation code</button>' : '');
  el('drawer').hidden = false;
}
```

- [ ] **Step 4: Run the marker test + full console suite + sanity**

Run: `rtk proxy python -m pytest tests/test_serial_admin_console.py -q`
Expected: PASS — licenses functions present, all settings/ping/revoke tests green, `node --check` accepts the script.

- [ ] **Step 5: Manual smoke (recommended)**

Run: `python serial_admin.py`, open the console, mint a serial, then open Licenses: confirm the row appears as **local-only**, search/filter chips work, Details drawer opens. With a real cloud token in Settings, confirm published serials show status + device usage and Revoke/Suspend/Re-activate work. Ctrl+C to stop.

- [ ] **Step 6: Commit**

```bash
rtk git add serial_admin_ui.py tests/test_serial_admin_console.py
rtk git commit -m "feat(console): unified Licenses view — search, filter, publish, revoke/suspend/reactivate, details"
```

---

### Task 8: Full-suite verification + line-count check

Confirm the whole project is green and the module-size goal is met.

- [ ] **Step 1: Run the entire test suite**

Run: `rtk proxy python -m pytest tests/ -q`
Expected: exit 0 (`$LASTEXITCODE` == 0). The new console tests pass; nothing else regressed.

- [ ] **Step 2: Lint the changed Python**

Run: `rtk proxy python -m ruff check serial_admin.py serial_admin_ui.py tests/test_serial_admin_console.py`
Expected: no errors. Fix any flagged issue (unused import, line length) and re-run.

- [ ] **Step 3: Confirm `serial_admin.py` shrank under target**

Run: `python -c "print(sum(1 for _ in open('serial_admin.py', encoding='utf-8')))"`
Expected: under ~500 lines (template extracted). If meaningfully over, that's a signal logic crept in that belongs elsewhere — review, don't pad.

- [ ] **Step 4: Final commit (only if Steps 2 produced fixes)**

```bash
rtk git add serial_admin.py serial_admin_ui.py
rtk git commit -m "chore(console): lint fixes for the vendor console redesign"
```

---

## Self-review (completed during planning)

**Spec coverage:**
- Single cloud connection / opt-in remember (0600) → Task 2 (`_read/_write_settings`, `/api/settings`) + Task 5 (Settings view, `conn`, rehydrate).
- `/api/cloud/ping` → Task 3. `/api/cloud/revoke` → Task 4.
- Template extraction into `serial_admin_ui.py` → Task 1.
- Sidebar shell + router + design tokens + toasts → Task 5.
- Dashboard (stats, recent, empty state) + Issue (guided mint, validation, results, publish-all) → Task 6.
- Licenses (local⨝cloud join, badges, device bar, search/filter chips, publish/revoke/suspend/reactivate, details drawer, not-connected guard) → Task 7.
- Security (loopback retained, seed never returned, token 0600/never logged, gitignore) → unchanged guard + Task 2 (`.gitignore`, chmod) + Settings security notes.
- Testing (settings/ping/revoke/loopback + HTML render + `node --check`) → Tasks 1-7; full suite + ruff → Task 8.
- Per-device release explicitly deferred → not implemented (matches spec non-goal).

**Placeholder scan:** No "TBD"/"add error handling"-style steps; every code step carries real code. The Task 5 view loaders are real (working) stubs intentionally replaced in Tasks 6-7, each replacement shown in full.

**Type/name consistency:** `state`, `conn={cloud_url,admin_token}`, `api()`, `jsonPost()`, `toast()`, `showView()`, `statusBadge()`, `jsArg()`, `_download()` are defined in Task 5 and reused unchanged in Tasks 6-7. Backend `SETTINGS_FILE_ENV`, `_BAKED_CLOUD_URL`, `_settings_path/_read_settings/_write_settings` names match across tasks and tests. The cloud revoke proxy body `{serial, status}` matches `dental_clinic.py:5147` (`license_admin`), which expects `serial` + `status ∈ {active,revoked,suspended}` and returns `{success:true}` / 401 `{error:'admin token required'}`.
