# Licensing C — Toggle-Only Auto Cloud Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the Cloud Sync settings (URL + serial + Pair / Sync-now / Link-phone / Unpair) into a single *Cloud backup — On/Off* toggle that links with the baked URL + already-activated serial, zero typing.

**Architecture:** Extract `cloud_pair`'s core into `_link_clinic_to_cloud(...)`; add a zero-input `POST /api/cloud/enable` that reads `active_serial_number` + `active_serial_token` and delegates to it. Replace the typed pair form with one `cloud-toggle-row` switch (mirroring the BT toggle) bound to `cloudToggle(checked)` → enable/unpair. Sync stays automatic via the existing worker.

**Tech Stack:** Python 3.12, Flask, SQLite; vanilla JS in `templates.HTML_TEMPLATE`. Tests: `pytest` (+ `node --check`).

**Spec:** `docs/superpowers/specs/2026-06-04-licensing-c-toggle-sync-design.md`
**Depends on:** B (`_BAKED_CLOUD_BASE_URL`, `_license_cloud_url`), A2/A3 (`active_serial_number`, `active_serial_token`).

---

## File Structure

- **Modify** `dental_clinic.py`:
  - extract `_link_clinic_to_cloud(cloud_url, serial, offline_token)` from `cloud_pair` (`:4445`).
  - add `POST /api/cloud/enable` after `cloud_pair`.
- **Modify** `templates.py` (`HTML_TEMPLATE`): replace the pair form + paired-action buttons (`:2411-2433`) with one toggle + a secondary-actions block; update the JS (`:5584-5679`).
- **Create** `tests/test_cloud_toggle_c.py`, `tests/test_cloud_toggle_ui_c.py`.
- **Update** `README.md` test-count line.

## Conventions

`rtk proxy python -m pytest tests/test_cloud_toggle_c.py -v` — check `$LASTEXITCODE`. (RTK collects 0 tests if you pass a dir to `rtk pytest`; use `rtk proxy python -m pytest`.)

---

### Task 1: Extract `_link_clinic_to_cloud` (pure refactor, behaviour-preserving)

**Files:**
- Modify: `dental_clinic.py:4445-4495` (`cloud_pair`)
- Test: `tests/test_cloud_toggle_c.py`

- [ ] **Step 1: Write the failing test (helper exists + pair still works)**

```python
# tests/test_cloud_toggle_c.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.delenv('CLINIC_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_LICENSE_CLOUD_URL', raising=False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _stub_cloud_ok(monkeypatch, sink):
    def fake_http(method, url, headers=None, body=None, timeout=15):
        sink['url'] = url
        sink['body'] = body
        return 200, {'clinic_token': 'tok-xyz', 'clinic_id': 11}
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True, 'pulled': 0, 'pushed': 0})


def test_helper_exists():
    assert hasattr(dental_clinic, '_link_clinic_to_cloud')


def test_cloud_pair_still_works(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    r = local.post('/api/cloud/pair',
                   json={'cloud_url': 'https://c.example.test', 'serial_number': 'DENTAL-C-PAIR1'})
    assert r.status_code == 200
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    assert conn.execute("SELECT value FROM app_settings WHERE key='cloud_clinic_token'").fetchone()[0] == 'tok-xyz'
    conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_c.py -k "helper_exists or pair_still" -v`
Expected: `test_helper_exists` FAILS (`_link_clinic_to_cloud` undefined).

- [ ] **Step 3: Implement the extraction**

Add the helper just above `cloud_pair` (`:4445`):

```python
def _link_clinic_to_cloud(cloud_url, serial, offline_token):
    """Register this clinic with the cloud node, persist the returned token, and
    run a first sync. Returns (response_dict, None) on success or (error_dict,
    status_code) on failure. Shared by /api/cloud/pair and /api/cloud/enable."""
    cloud_url = (cloud_url or '').strip().rstrip('/')
    serial = (serial or '').strip().upper()
    if not cloud_url:
        return {'error': 'No cloud server configured'}, 400
    if len(serial) < 8:
        return {'error': 'serial_number must be at least 8 characters'}, 400
    clinic_name = str(CLINIC_CONFIG.get('CLINIC_NAME') or 'Clinic')
    register_body = {'serial_number': serial, 'clinic_name': clinic_name}
    if offline_token:
        register_body['offline_token'] = offline_token
    try:
        status, resp = _cloud_http_request('POST', f'{cloud_url}/api/clinics/register',
                                           body=register_body)
    except Exception as exc:  # noqa: BLE001 - connection error → can't reach
        return {'error': f'Could not reach the cloud node: {exc}'}, 502
    if status != 200 or not (isinstance(resp, dict) and resp.get('clinic_token')):
        return {'error': f'Cloud registration failed (HTTP {status})', 'detail': resp}, 502

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    write_app_setting(cur, 'cloud_url', cloud_url)
    write_app_setting(cur, 'cloud_clinic_token', resp['clinic_token'])
    write_app_setting(cur, 'cloud_clinic_id', str(resp.get('clinic_id') or ''))
    if offline_token:
        write_app_setting(cur, 'cloud_offline_token', offline_token)
    conn.commit()
    conn.close()

    first_sync = _run_cloud_sync_once(cloud_url, resp['clinic_token'])
    return {
        'success': True,
        'cloud_url': cloud_url,
        'clinic_id': resp.get('clinic_id'),
        'already_registered': resp.get('already_registered'),
        'first_sync': first_sync,
    }, None
```

Replace the body of `cloud_pair` (`:4446`) after its `CLOUD_MODE` guard with delegation:

```python
@app.route('/api/cloud/pair', methods=['POST'])
def cloud_pair():
    if CLOUD_MODE:
        return jsonify({'error': 'Not applicable on the cloud node'}), 400
    data = request.json or {}
    cloud_url = str(data.get('cloud_url') or os.environ.get('CLINIC_CLOUD_URL')
                    or _BAKED_CLOUD_BASE_URL or '').strip().rstrip('/')
    serial = str(data.get('serial_number') or '').strip().upper()
    offline_token = _resolve_offline_token(data)
    result, err = _link_clinic_to_cloud(cloud_url, serial, offline_token)
    return jsonify(result), (err or 200)
```

> This preserves B's baked-URL fallback (Task 2 of B) and the existing `_resolve_offline_token`
> behaviour. The `if not cloud_url` / serial-length checks now live in the helper.

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_c.py -k "helper_exists or pair_still" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_cloud_toggle_c.py
rtk git commit -m "refactor(cloud): extract _link_clinic_to_cloud shared by pair + enable"
```

---

### Task 2: `POST /api/cloud/enable` (zero-input toggle-on)

**Files:**
- Modify: `dental_clinic.py` (add route after `cloud_pair`)
- Test: `tests/test_cloud_toggle_c.py`

- [ ] **Step 1: Write the failing test**

```python
def _set_setting(key, value):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def test_enable_without_license_409(local):
    r = local.post('/api/cloud/enable')
    assert r.status_code == 409
    assert r.get_json()['reason'] == 'not_activated'


def test_enable_uses_active_serial_and_baked_url(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    _set_setting('active_serial_number', 'DENTAL-C-EN1')
    _set_setting('active_serial_token', 'signed.token.here')
    r = local.post('/api/cloud/enable')
    assert r.status_code == 200
    # registered against the baked base, with the active serial + retained token forwarded
    assert sink['url'].startswith(dental_clinic._BAKED_CLOUD_BASE_URL)
    assert sink['body']['serial_number'] == 'DENTAL-C-EN1'
    assert sink['body']['offline_token'] == 'signed.token.here'
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    assert conn.execute("SELECT value FROM app_settings WHERE key='cloud_clinic_token'").fetchone()[0] == 'tok-xyz'
    conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_c.py -k enable -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement the route**

Add after `cloud_pair`:

```python
@app.route('/api/cloud/enable', methods=['POST'])
def cloud_enable():
    """Toggle-on: link to the cloud using the already-activated serial + retained
    signed token and the baked/configured URL. Zero inputs — sync only, no license
    change."""
    if CLOUD_MODE:
        return jsonify({'error': 'Not applicable on the cloud node'}), 400
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    serial = str(read_app_setting(cur, 'active_serial_number', '') or '').strip().upper()
    token = str(read_app_setting(cur, 'active_serial_token', '') or '').strip()
    conn.close()
    if not serial:
        return jsonify({'error': 'Activate a license first', 'reason': 'not_activated'}), 409
    cloud_url = _license_cloud_url()
    result, err = _link_clinic_to_cloud(cloud_url, serial, token)
    return jsonify(result), (err or 200)
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_c.py -k enable -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_cloud_toggle_c.py
rtk git commit -m "feat(cloud): C zero-input POST /api/cloud/enable (toggle-on)"
```

---

### Task 3: Decoupling regression (sync toggle ⟂ license)

**Files:**
- Test: `tests/test_cloud_toggle_c.py`

- [ ] **Step 1: Write the failing test**

```python
def _license_count():
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    n = conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
    conn.close()
    return n


def test_enable_does_not_touch_license(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    _set_setting('active_serial_number', 'DENTAL-C-DEC')
    before = _license_count()
    local.post('/api/cloud/enable')
    assert _license_count() == before                  # enable never writes licenses
    assert dental_clinic_active_serial() == 'DENTAL-C-DEC'


def test_unpair_does_not_touch_license(local):
    _set_setting('active_serial_number', 'DENTAL-C-DEC2')
    local.post('/api/cloud/unpair')
    assert dental_clinic_active_serial() == 'DENTAL-C-DEC2'   # unpair leaves the license alone


def dental_clinic_active_serial():
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    row = conn.execute("SELECT value FROM app_settings WHERE key='active_serial_number'").fetchone()
    conn.close()
    return row[0] if row else None
```

- [ ] **Step 2: Run to verify it passes (regression guard)**

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_c.py -k "does_not_touch" -v`
Expected: PASS — `cloud_enable`/`cloud_unpair` only touch cloud_* settings. Locks the decoupling.

- [ ] **Step 3: Implement** — no code change. If it fails, a regression coupled sync to license; fix the writer, not the test.

- [ ] **Step 4: Re-run** — `rtk proxy python -m pytest tests/test_cloud_toggle_c.py -k "does_not_touch" -v` → PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_cloud_toggle_c.py
rtk git commit -m "test(cloud): C lock sync-toggle ⟂ license decoupling"
```

---

### Task 4: Toggle UI — replace the pair form with one switch

**Files:**
- Modify: `templates.py` (`HTML_TEMPLATE` markup `:2411-2433` + JS `:5584-5679`)
- Create: `tests/test_cloud_toggle_ui_c.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cloud_toggle_ui_c.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import templates


def test_template_has_cloud_toggle():
    html = templates.HTML_TEMPLATE
    assert 'id="cloud-enabled"' in html
    assert 'cloudToggle(' in html
    assert "fetch('/api/cloud/enable'" in html or 'fetch("/api/cloud/enable"' in html


def test_template_drops_typed_pairing():
    html = templates.HTML_TEMPLATE
    assert 'id="cloud-url-input"' not in html
    assert 'id="cloud-serial-input"' not in html
    assert 'function cloudPair(' not in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_template_scripts_pass_node_check():
    html = templates.HTML_TEMPLATE
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
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

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_ui_c.py -v`
Expected: `test_template_has_cloud_toggle` and `test_template_drops_typed_pairing` FAIL.

- [ ] **Step 3a: Replace the markup**

In `templates.py`, replace the `#cloud-pair-form` block and the button cluster inside
`#cloud-paired-actions` (`:2411-2433`) with:

```html
                    <div class="cloud-toggle-row bt-toggle-row">
                        <label>
                            <input type="checkbox" id="cloud-enabled" onchange="cloudToggle(this.checked)"/>
                            <span data-en="Cloud backup" data-ar="النسخ الاحتياطي السحابي">Cloud backup</span>
                        </label>
                    </div>
                    <div id="cloud-secondary" style="display:none;margin-top:12px;">
                        <button class="btn btn-secondary" type="button" onclick="cloudSyncNow(this)" data-en="Sync now" data-ar="مزامنة الآن">Sync now</button>
                        <button class="btn btn-secondary" type="button" onclick="cloudShowPairingQr()" data-en="Link a phone" data-ar="ربط هاتف">Link a phone</button>
                        <div id="cloud-pairing-qr" style="display:none;margin-top:14px;">
                            <p style="margin:0 0 10px;color:var(--muted);font-size:0.9em;line-height:1.6;"
                               data-en="Open the mobile app, then Settings, then Scan QR."
                               data-ar="افتح تطبيق الهاتف، ثم الإعدادات، ثم مسح رمز QR.">Open the mobile app, then Settings, then Scan QR.</p>
                            <img id="cloud-pairing-qr-img" alt="Pairing QR"
                                 style="width:220px;height:220px;background:#fff;padding:10px;border-radius:8px;border:1px solid var(--border,#d8e0e2);">
                        </div>
                    </div>
```

> Keep `#cloud-status-line` and the section `<p>` intro above it as-is.

- [ ] **Step 3b: Update the JS**

In `loadCloudSyncSettings` (`:5584`), replace the `pairForm`/`pairedActions` show/hide logic with
the toggle + secondary block. Replace the function body's branching with:

```javascript
        async function loadCloudSyncSettings() {
            const st = await fetchCloudStatus();
            renderCloudBadge(st);
            const line = document.getElementById('cloud-status-line');
            const toggle = document.getElementById('cloud-enabled');
            const secondary = document.getElementById('cloud-secondary');
            if (!line) return;
            const show = (el, on) => { if (el) el.style.display = on ? '' : 'none'; };
            if (!st) { line.textContent = ''; if (toggle) toggle.checked = false; show(secondary, false); return; }
            if (st.cloud_mode) {
                line.innerHTML = '<em>' + (_ar() ? 'هذا هو الخادم السحابي.' : 'This is the cloud node.') + '</em>';
                if (toggle) { toggle.checked = false; toggle.disabled = true; }
                show(secondary, false);
                return;
            }
            if (toggle) toggle.checked = !!st.configured;
            show(secondary, !!st.configured);
            if (st.configured) {
                const parts = [];
                parts.push((_ar() ? 'مرتبط بـ ' : 'Backing up to ') + '<strong>' + (st.cloud_url || '') + '</strong>');
                if (st.last_sync_at) {
                    const ok = String(st.last_sync_result) === 'ok';
                    parts.push((_ar() ? 'آخر مزامنة: ' : 'Last sync: ') + _relativeTime(st.last_sync_at)
                               + (ok ? ' ✓' : ' — ' + (st.last_sync_result || '')));
                } else {
                    parts.push(_ar() ? 'لم تتم أي مزامنة بعد' : 'No sync yet');
                }
                line.innerHTML = parts.join('<br>');
            } else {
                line.innerHTML = '<em>' + (_ar() ? 'النسخ الاحتياطي السحابي غير مفعّل.' : 'Cloud backup is off.') + '</em>';
            }
        }
```

Replace the old `cloudPair` function entirely with `cloudToggle`:

```javascript
        async function cloudToggle(checked) {
            const toggle = document.getElementById('cloud-enabled');
            if (checked) {
                try {
                    const resp = await fetch('/api/cloud/enable', { method: 'POST' });
                    const payload = await resp.json().catch(() => ({}));
                    if (!resp.ok) {
                        if (toggle) toggle.checked = false;
                        if (payload.reason === 'not_activated') {
                            alert(_ar() ? 'فعّل الترخيص أولاً.' : 'Activate a license first.');
                        } else {
                            alert(payload.error || (_ar() ? 'تعذّر تفعيل النسخ السحابي.' : 'Could not enable cloud backup.'));
                        }
                        return;
                    }
                } catch (_) {
                    if (toggle) toggle.checked = false;
                    alert(_ar() ? 'تعذّر الوصول إلى الخادم.' : 'Could not reach the server.');
                }
            } else {
                if (!confirm(_ar() ? 'إيقاف النسخ الاحتياطي السحابي؟' : 'Turn off cloud backup?')) {
                    if (toggle) toggle.checked = true;
                    return;
                }
                try { await fetch('/api/cloud/unpair', { method: 'POST' }); } catch (_) {}
            }
            await loadCloudSyncSettings();
        }
```

Leave `cloudSyncNow`, `cloudUnpair` (still referenced? remove if now unused), and
`cloudShowPairingQr` intact. If `cloudUnpair` is no longer referenced anywhere, delete it to avoid
dead code (the toggle's OFF path now calls `/api/cloud/unpair` directly).

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_cloud_toggle_ui_c.py -v`
Expected: PASS (node sweep runs if `node` present). `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add templates.py tests/test_cloud_toggle_ui_c.py
rtk git commit -m "feat(cloud): C collapse Cloud Sync settings into one toggle"
```

---

### Task 5: Full regression + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Byte-compile + full suite**

```bash
rtk proxy python -m py_compile dental_clinic.py templates.py
rtk proxy python -m pytest tests/ -q
```
Expected: clean; whole suite (A1+A2+A3+B+C) green. `$LASTEXITCODE` == 0. Pay attention to any
existing cloud-sync test that posted to `/api/cloud/pair` with a URL — those still pass (pair is
unchanged behaviourally). If a test asserted the old `#cloud-url-input` markup, update that test to
the toggle (the markup intentionally changed).

- [ ] **Step 2: Update README test count** (add the two new suites) in the existing wording style.

- [ ] **Step 3: Commit + push**

```bash
rtk git add README.md
rtk git commit -m "docs: C — record toggle-only cloud sync test suites"
rtk git push
```

---

## Self-Review

1. **Spec coverage:** `_link_clinic_to_cloud` refactor (T1), `/api/cloud/enable` zero-input (T2),
   decoupling regression (T3), toggle UI + dropped typed inputs + JS sweep (T4), regression+docs
   (T5). Every "In" bullet maps to a task. ✅
2. **Placeholder scan:** none — all code/markup/commands are concrete.
3. **Type/name consistency:** `_link_clinic_to_cloud(cloud_url, serial, offline_token)` returns
   `(dict, status_or_None)` and is called identically by `cloud_pair` and `cloud_enable`; the
   toggle id `cloud-enabled`, handler `cloudToggle`, and `/api/cloud/enable` match across markup,
   JS, and tests; `cloud_secondary` visibility keyed off `st.configured` consistently.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-licensing-c-toggle-sync.md`. Two options:

1. **Subagent-Driven (recommended)** — fresh subagent per task; run them **one at a time** (the earlier 5-way parallel fan-out hit the account session limit).
2. **Inline Execution** — implement T1–T5 in-session with checkpoints.

**Which approach?** (Or continue to the final plan — D — since you asked for all five.)
