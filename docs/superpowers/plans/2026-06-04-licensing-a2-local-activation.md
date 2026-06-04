# Licensing A2 — Local-Server Activation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop server the local license authority — verify the vendor Ed25519 signature on activation, source license fields from the signed token (or the A1 cloud authority), cache that as local truth, fix the grace-date bypass, and enforce device membership so the serial string alone is not a credential.

**Architecture:** `POST /api/license/activate` branches on a signed `serial_token`. Primary (desktop) activation verifies the signature, derives a server-owned device fingerprint, calls the cloud `/api/license/validate` once (authoritative when reachable; the signed token is the offline fallback), and writes the local `licenses`/`license_devices` cache. A tokenless LAN-attach path lets phones join an already-activated license within the token-set device cap. `/login` and `/status` reject unknown devices.

**Tech Stack:** Python 3.12, Flask, SQLite (`sqlite3`), `cryptography` (Ed25519, already a dependency from A1), stdlib `urllib`. Tests in `pytest`.

**Spec:** `docs/superpowers/specs/2026-06-04-licensing-a2-local-activation-design.md`

---

## File Structure

- **Modify** `dental_clinic.py`:
  - `:234` — baked public-key fallback for `_SERIAL_PUBLIC_KEY_B64`.
  - new helpers near the other license helpers (`~:585`): `_get_or_create_device_fingerprint`, `_iso_to_window_date`, `_license_cloud_url`, `_validate_with_cloud`.
  - `:4732` `activate_license` — split into `_activate_primary` + `_activate_lan_attach`.
  - `:4848` `license_login` — device-membership gate.
  - `:4968` `license_status` — device-membership gate.
- **Create** `tests/test_license_activation_a2.py` — the A2 suite.
- **Update** `README.md` test-count line after the suite is green.

Each task is self-contained: a failing test, the minimal code to pass it, a verification run, and a commit.

---

## Conventions for every test run

Run the suite with (RTK collects 0 tests if you pass a dir to `rtk pytest`, so use `proxy`):

```bash
rtk proxy python -m pytest tests/test_license_activation_a2.py -v
```

pytest summary output is suppressed in this environment — **after each run, check `$LASTEXITCODE`** (`0` = all passed, non-zero = failure). On Windows PowerShell: `echo $LASTEXITCODE`.

---

### Task 1: A2 test harness + the signature gate

**Files:**
- Create: `tests/test_license_activation_a2.py`
- Modify: `dental_clinic.py:4732-4844` (`activate_license`)

- [ ] **Step 1: Write the failing test (harness + signature gate)**

```python
# tests/test_license_activation_a2.py
import sqlite3
import pytest
import serial_generator
import dental_clinic
from datetime import datetime, timedelta, timezone


@pytest.fixture()
def local(tmp_path, monkeypatch):
    """Desktop (LOCAL, non-cloud) server with a known vendor public key and a
    stubbable cloud. By default the cloud is 'offline' (returns None) so tests
    exercise the signed-token fallback unless they override _validate_with_cloud."""
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud', lambda *a, **k: None)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        c.priv_b64 = priv_b64
        yield c


def _sign(client, serial, **kw):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {
        'v': 2, 'serial': serial, 'clinic_name': kw.get('clinic_name', 'C'),
        'plan_name': kw.get('plan_name', 'standard'),
        'max_devices': kw.get('max_devices', 3),
        'issued_at': now.isoformat() + 'Z',
        'expires_at': (now + timedelta(days=kw.get('expiry_days', 365))).isoformat() + 'Z',
        'grace_until': (now + timedelta(days=kw.get('expiry_days', 365) + 14)).isoformat() + 'Z',
    }
    return serial_generator.sign_serial_token(payload, client.priv_b64)


def _activate(client, token, **extra):
    body = {'serial_token': token}
    body.update(extra)
    return client.post('/api/license/activate', json=body)


def test_activate_rejects_unsigned_token(local):
    r = _activate(local, 'not-a-real-token')
    assert r.status_code == 403
    assert r.get_json()['reason'] in ('malformed', 'bad_signature')


def test_activate_accepts_signed_token(local):
    r = _activate(local, _sign(local, 'DENTAL-A2-0001'))
    assert r.status_code == 200
    assert r.get_json()['success'] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -v`
Expected: `test_activate_rejects_unsigned_token` FAILS — the current endpoint ignores `serial_token`, treats the body as a legacy activation, and returns 400 (serial too short) or 200, not 403.

- [ ] **Step 3: Implement the signature-gated primary branch**

In `dental_clinic.py`, replace the body of `activate_license` (`:4733-4844`) with a dispatcher plus a primary handler. Replace the whole function with:

```python
def activate_license():
    data = request.json or {}
    serial_token = str(data.get('serial_token') or '').strip()
    device_name = str(data.get('device_name') or '').strip()
    if serial_token:
        return _activate_primary(serial_token, device_name)
    return _activate_lan_attach(data)


def _activate_primary(serial_token, device_name):
    payload, why = _decode_signed_serial_token(serial_token)
    if payload is None:
        msg = {
            'missing': 'serial token required',
            'no_key': 'server signing key not configured',
            'malformed': 'malformed serial token',
            'bad_signature': 'invalid serial token signature',
        }.get(why, 'invalid serial token')
        return jsonify({'error': msg, 'reason': why or 'invalid'}), 403

    serial_number = str(payload.get('serial') or '').strip().upper()
    if len(serial_number) < 8:
        return jsonify({'error': 'Serial number must be at least 8 characters'}), 400
    clinic_name = str(payload.get('clinic_name') or '').strip()
    plan_name = str(payload.get('plan_name') or 'starter').strip() or 'starter'
    try:
        max_devices = max(1, int(payload.get('max_devices') or 1))
    except (TypeError, ValueError):
        max_devices = 1
    status = 'active'
    expires_at = _iso_to_window_date(payload.get('expires_at'))
    grace_until = _iso_to_window_date(payload.get('grace_until')) or expires_at

    conn = get_db_connection()
    cursor = conn.cursor()
    fingerprint = _get_or_create_device_fingerprint(cursor)

    cloud = _validate_with_cloud(serial_token, fingerprint, device_name)
    if cloud is not None:
        if not cloud.get('valid'):
            conn.close()
            return jsonify({'error': 'License rejected by server',
                            'reason': str(cloud.get('reason') or 'invalid')}), 403
        status = str(cloud.get('status') or 'active')
        expires_at = _iso_to_window_date(cloud.get('expires_at')) or expires_at
        grace_until = _iso_to_window_date(cloud.get('grace_until')) or grace_until
        plan_name = str(cloud.get('plan_name') or plan_name).strip() or plan_name
        try:
            max_devices = max(1, int(cloud.get('max_devices') or max_devices))
        except (TypeError, ValueError):
            pass
    else:
        window = evaluate_license_window(status, expires_at, grace_until)
        if not window['licensed']:
            conn.close()
            return jsonify({'error': 'License expired', 'reason': 'expired'}), 403

    cursor.execute('''
        INSERT INTO licenses (
            serial_number, clinic_name, plan_name, status,
            max_devices, expires_at, grace_until, activated_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(serial_number) DO UPDATE SET
            clinic_name = excluded.clinic_name,
            plan_name   = excluded.plan_name,
            status      = excluded.status,
            max_devices = excluded.max_devices,
            expires_at  = excluded.expires_at,
            grace_until = excluded.grace_until,
            updated_at  = CURRENT_TIMESTAMP
    ''', (serial_number, clinic_name, plan_name, status, max_devices, expires_at, grace_until))

    cursor.execute('''
        INSERT INTO license_devices (serial_number, device_id, device_name, first_seen_at, last_seen_at, is_active)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        ON CONFLICT(serial_number, device_id) DO UPDATE SET
            device_name = excluded.device_name,
            last_seen_at = CURRENT_TIMESTAMP,
            is_active = 1
    ''', (serial_number, fingerprint, device_name or 'clinic-server'))

    write_app_setting(cursor, 'active_serial_number', serial_number)
    append_audit_log(cursor, 'activate', 'license', None, {
        'serial_number': serial_number, 'clinic_name': clinic_name,
        'plan_name': plan_name, 'device_id': fingerprint,
        'source': 'cloud' if cloud is not None else 'offline-token',
    })

    signing_key = get_or_create_license_signing_key(cursor)
    record = fetch_license_record(cursor, serial_number)
    offline_license_token = ''
    offline_license_payload = {}
    if record:
        validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
        offline_license_payload, offline_license_token = serialize_offline_license(
            record, validity, signing_key, device_id=fingerprint)

    conn.commit()
    conn.close()

    resp = {'success': True, 'serial_number': serial_number, 'plan_name': plan_name,
            'expires_at': expires_at, 'grace_until': grace_until}
    if offline_license_token:
        resp['offline_license_token'] = offline_license_token
        resp['offline_license'] = offline_license_payload
    return jsonify(resp)
```

> This references `_iso_to_window_date`, `_get_or_create_device_fingerprint`, `_validate_with_cloud`, and `_activate_lan_attach`, which are defined in Tasks 2–4 and 6. Define them in those tasks **before running their tests**; if you implement strictly top-to-bottom, add temporary `def _iso_to_window_date(v): return ''` etc. stubs now and replace them in their tasks. (Recommended: implement Tasks 2–4 first, then this — the test for Task 1 only needs the signature gate, but the function body imports the helper names at call time, so the helpers must exist as names.)

**To keep Task 1 runnable on its own**, also add the four helper stubs from Tasks 2–4 now (they get their real bodies + tests next). Place them just after `serialize_offline_license` (`~:572`):

```python
def _get_or_create_device_fingerprint(cursor):
    fp = str(read_app_setting(cursor, 'device_fingerprint', '') or '').strip()
    if fp:
        return fp
    fp = secrets.token_hex(16)
    write_app_setting(cursor, 'device_fingerprint', fp)
    return fp


def _iso_to_window_date(value):
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return datetime.fromisoformat(text.rstrip('Z')).strftime('%Y-%m-%d')
    except ValueError:
        return ''


def _license_cloud_url():
    url = os.environ.get('CLINIC_LICENSE_CLOUD_URL', '').strip()
    if not url:
        url = _cloud_sync_config()[0] or ''
    return (url.rstrip('/') or None)


def _validate_with_cloud(serial_token, fingerprint, device_name=''):
    base = _license_cloud_url()
    if not base:
        return None
    body = {'serial_token': serial_token, 'device_fingerprint': fingerprint}
    if device_name:
        body['device_name'] = device_name
    try:
        _status, payload = _cloud_http_request('POST', f'{base}/api/license/validate', None, body)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None
```

And add `_activate_lan_attach` as a temporary reject-stub (Task 6 fills it in):

```python
def _activate_lan_attach(data):
    return jsonify({'error': 'Activate on the clinic server first', 'reason': 'not_activated'}), 403
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -v`
Expected: both Task 1 tests PASS. Check `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_license_activation_a2.py dental_clinic.py
rtk git commit -m "feat(license): A2 signature-gated /activate + helper scaffolding"
```

---

### Task 2: Baked-in public key fallback

**Files:**
- Modify: `dental_clinic.py:234`
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_baked_public_key_is_present():
    # The desktop must verify vendor serials with no env setup: a build always
    # carries SOME serial public key (the baked constant if the env var is unset).
    import os
    assert dental_clinic._SERIAL_PUBLIC_KEY_B64, 'no serial public key baked or configured'
    # And the baked constant must be a real key, not the placeholder.
    assert dental_clinic._BAKED_SERIAL_PUBLIC_KEY != 'REPLACE_WITH_REAL_VENDOR_PUBLIC_KEY_BASE64'
```

> Keep the second assertion **xfail until the real key is filled** (see Step 3). It is a guard so a placeholder build can't ship silently.

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py::test_baked_public_key_is_present -v`
Expected: FAIL with `AttributeError: module 'dental_clinic' has no attribute '_BAKED_SERIAL_PUBLIC_KEY'`.

- [ ] **Step 3: Implement the baked fallback**

In `dental_clinic.py`, replace line 234:

```python
_SERIAL_PUBLIC_KEY_B64 = os.environ.get('CLINIC_SERIAL_PUBLIC_KEY', '').strip()
```

with:

```python
# Real vendor Ed25519 public key, baked into the build so the desktop can verify
# vendor serials with zero env setup. PUBLIC key only — it verifies, never mints.
# Generate the keypair with `python serial_generator.py --genkey` and paste the
# printed public key here. The private seed (backend_ed25519_key.json) stays on the
# vendor machine and is NEVER committed.
_BAKED_SERIAL_PUBLIC_KEY = 'REPLACE_WITH_REAL_VENDOR_PUBLIC_KEY_BASE64'
_SERIAL_PUBLIC_KEY_B64 = os.environ.get('CLINIC_SERIAL_PUBLIC_KEY', '').strip() or _BAKED_SERIAL_PUBLIC_KEY
```

Mark the real-key guard xfail so the suite is green pre-fill (remove the marker once the real key is pasted):

```python
@pytest.mark.xfail(reason='real vendor public key not yet baked', strict=False)
def test_baked_public_key_is_real():
    assert dental_clinic._BAKED_SERIAL_PUBLIC_KEY != 'REPLACE_WITH_REAL_VENDOR_PUBLIC_KEY_BASE64'
```

And simplify the first test to just assert presence:

```python
def test_baked_public_key_is_present():
    assert dental_clinic._SERIAL_PUBLIC_KEY_B64, 'no serial public key baked or configured'
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k baked -v`
Expected: `test_baked_public_key_is_present` PASS, `test_baked_public_key_is_real` XFAIL. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_activation_a2.py
rtk git commit -m "feat(license): A2 bake vendor public key into the desktop build"
```

---

### Task 3: `_iso_to_window_date` + token-sourced fields (anti-spoof)

**Files:**
- Modify: `dental_clinic.py` (helper finalised in Task 1; this task proves the behaviour)
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def _license_row(serial):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    row = conn.execute(
        'SELECT max_devices, expires_at, grace_until, plan_name FROM licenses WHERE serial_number=?',
        (serial.upper(),)).fetchone()
    conn.close()
    return row


def test_fields_come_from_token_not_client_json(local):
    # Token says max_devices=5; the client lies with max_devices=99 + a bogus window.
    tok = _sign(local, 'DENTAL-A2-SRC1', max_devices=5)
    r = _activate(local, tok, max_devices=99, expires_at='2099-01-01', plan_name='enterprise')
    assert r.status_code == 200
    max_devices, expires_at, _grace, plan = _license_row('DENTAL-A2-SRC1')
    assert max_devices == 5            # token wins, not 99
    assert not expires_at.startswith('2099')  # client window ignored
    assert plan == 'standard'          # token plan, not client 'enterprise'


def test_iso_to_window_date_normalises_and_tolerates_garbage():
    assert dental_clinic._iso_to_window_date('2027-06-03T00:00:00Z') == '2027-06-03'
    assert dental_clinic._iso_to_window_date('') == ''
    assert dental_clinic._iso_to_window_date('not-a-date') == ''
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "from_token or iso_to_window" -v`
Expected: PASS if Task 1 was implemented with the real helper bodies. If you used stubs in Task 1, `test_iso_to_window_date_normalises_and_tolerates_garbage` FAILS (`'' != '2027-06-03'`) — that confirms the stub is still in place.

- [ ] **Step 3: Implement**

Ensure the real `_iso_to_window_date` body from Task 1, Step 3 is in place (not the `return ''` stub). No further change if Task 1 used the real bodies.

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "from_token or iso_to_window" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_activation_a2.py
rtk git commit -m "test(license): A2 prove license fields are token-sourced, not client-sourced"
```

---

### Task 4: Grace-date bypass fix

**Files:**
- Modify: `dental_clinic.py` (the `ON CONFLICT … DO UPDATE` window write in `_activate_primary`)
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_reactivation_overwrites_stale_window(local):
    s = 'DENTAL-A2-GRACE'
    _activate(local, _sign(local, s, expiry_days=10))     # short window first
    first = _license_row(s)[1]
    _activate(local, _sign(local, s, expiry_days=400))    # renew with a longer window
    second = _license_row(s)[1]
    assert second > first, f'window did not extend: {first} -> {second}'


def test_reactivation_does_not_resurrect_old_generous_window(local):
    s = 'DENTAL-A2-GRACE2'
    _activate(local, _sign(local, s, expiry_days=400))    # generous first
    _activate(local, _sign(local, s, expiry_days=10))     # then a short token
    # The cached window must reflect the SHORT token, not stay at +400d.
    expires_at = _license_row(s)[1]
    today = datetime.now(timezone.utc).date()
    assert (datetime.strptime(expires_at, '%Y-%m-%d').date() - today).days < 60
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "window" -v`
Expected: With the **old** `existing[3] or expires_at` logic these would fail. With the Task 1 `ON CONFLICT … DO UPDATE SET expires_at = excluded.expires_at` they PASS — this task is the regression guard that locks the fix in.

- [ ] **Step 3: Implement**

No new code if Task 1 wrote the `ON CONFLICT(serial_number) DO UPDATE SET … expires_at = excluded.expires_at, grace_until = excluded.grace_until` upsert. Confirm there is **no** surviving `expires_at = existing[...] or expires_at` line anywhere in `_activate_primary`.

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "window" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_license_activation_a2.py
rtk git commit -m "test(license): A2 lock the grace-date-bypass fix with regression tests"
```

---

### Task 5: Cloud authoritative when reachable; offline fallback

**Files:**
- Modify: `dental_clinic.py` (logic already in `_activate_primary` from Task 1)
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cloud_revoked_blocks_activation(local, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud',
                        lambda *a, **k: {'valid': False, 'reason': 'revoked'})
    r = _activate(local, _sign(local, 'DENTAL-A2-CLOUD1'))
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'revoked'


def test_cloud_window_overrides_token(local, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud',
                        lambda *a, **k: {'valid': True, 'status': 'active',
                                         'expires_at': '2031-01-01T00:00:00Z'})
    r = _activate(local, _sign(local, 'DENTAL-A2-CLOUD2', expiry_days=10))
    assert r.status_code == 200
    assert _license_row('DENTAL-A2-CLOUD2')[1] == '2031-01-01'


def test_offline_expired_token_is_rejected(local):
    # cloud stub returns None (offline) → the signed token IS the authority.
    r = _activate(local, _sign(local, 'DENTAL-A2-OFF1', expiry_days=-60))
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'expired'


def test_offline_valid_token_activates(local):
    r = _activate(local, _sign(local, 'DENTAL-A2-OFF2', expiry_days=365))
    assert r.status_code == 200
    assert r.get_json()['success'] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "cloud or offline" -v`
Expected: PASS if Task 1's `_activate_primary` implemented the cloud branch + offline `evaluate_license_window` gate. If any fails, the branch is missing — fix `_activate_primary` to match Task 1, Step 3.

- [ ] **Step 3: Implement**

No new code beyond Task 1; this task proves the cloud/offline branches. If `test_offline_expired_token_is_rejected` fails, confirm the `else:` offline branch calls `evaluate_license_window` and returns 403 on `not licensed`.

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "cloud or offline" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_license_activation_a2.py
rtk git commit -m "test(license): A2 cloud-authoritative + offline-token-fallback activation"
```

---

### Task 6: LAN-attach path (phones join an activated license)

**Files:**
- Modify: `dental_clinic.py` (`_activate_lan_attach` — replace the Task 1 stub)
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_lan_attach_requires_prior_activation(local):
    r = local.post('/api/license/activate',
                   json={'serial_number': 'DENTAL-A2-LAN0', 'device_id': 'phone-1'})
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'not_activated'


def test_lan_attach_enforces_device_cap(local):
    s = 'DENTAL-A2-LAN1'
    _activate(local, _sign(local, s, max_devices=2))   # desktop consumes slot 1
    ok = local.post('/api/license/activate', json={'serial_number': s, 'device_id': 'phone-2'})
    assert ok.status_code == 200                       # slot 2
    full = local.post('/api/license/activate', json={'serial_number': s, 'device_id': 'phone-3'})
    assert full.status_code == 403
    assert 'Max active devices' in full.get_json()['error']


def test_lan_attach_returns_offline_token(local):
    s = 'DENTAL-A2-LAN2'
    _activate(local, _sign(local, s, max_devices=3))
    r = local.post('/api/license/activate', json={'serial_number': s, 'device_id': 'phone-9'})
    assert r.status_code == 200
    assert r.get_json()['offline_license_token']
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "lan_attach" -v`
Expected: `test_lan_attach_enforces_device_cap` and `test_lan_attach_returns_offline_token` FAIL — the Task 1 stub returns 403 `not_activated` for every tokenless call.

- [ ] **Step 3: Implement `_activate_lan_attach`**

Replace the Task 1 stub with:

```python
def _activate_lan_attach(data):
    serial_number = str(data.get('serial_number') or '').strip().upper()
    device_id = str(data.get('device_id') or '').strip()
    device_name = str(data.get('device_name') or '').strip()
    if len(serial_number) < 8:
        return jsonify({'error': 'Serial number must be at least 8 characters'}), 400
    if not device_id:
        return jsonify({'error': 'device_id is required to attach a device'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    record = fetch_license_record(cursor, serial_number)
    if not record:
        conn.close()
        return jsonify({'error': 'Activate on the clinic server first',
                        'reason': 'not_activated'}), 403

    validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
    if not validity['licensed']:
        conn.close()
        return jsonify({'error': 'License is not active', 'status': record['status']}), 403

    limit_count = max(1, int(record['max_devices'] or 1))
    cursor.execute('SELECT 1 FROM license_devices WHERE serial_number = ? AND device_id = ?',
                   (serial_number, device_id))
    is_member = cursor.fetchone() is not None
    if not is_member:
        cursor.execute('SELECT COUNT(*) FROM license_devices WHERE serial_number = ? AND is_active = 1',
                       (serial_number,))
        if int(cursor.fetchone()[0] or 0) >= limit_count:
            conn.close()
            return jsonify({'error': f'Max active devices reached ({limit_count})'}), 403

    cursor.execute('''
        INSERT INTO license_devices (serial_number, device_id, device_name, first_seen_at, last_seen_at, is_active)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        ON CONFLICT(serial_number, device_id) DO UPDATE SET
            device_name = excluded.device_name,
            last_seen_at = CURRENT_TIMESTAMP,
            is_active = 1
    ''', (serial_number, device_id, device_name))
    append_audit_log(cursor, 'attach', 'license', None,
                     {'serial_number': serial_number, 'device_id': device_id})

    signing_key = get_or_create_license_signing_key(cursor)
    record = fetch_license_record(cursor, serial_number)
    validity = evaluate_license_window(record['status'], record['expires_at'], record['grace_until'])
    offline_license_payload, offline_license_token = serialize_offline_license(
        record, validity, signing_key, device_id=device_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'serial_number': serial_number,
                    'offline_license_token': offline_license_token,
                    'offline_license': offline_license_payload})
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "lan_attach" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_activation_a2.py
rtk git commit -m "feat(license): A2 LAN-attach path for phones under the token device cap"
```

---

### Task 7: Device-membership gate on `/api/license/login`

**Files:**
- Modify: `dental_clinic.py:4848-4894` (`license_login`)
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_login_rejects_unknown_device(local):
    s = 'DENTAL-A2-LOGIN'
    _activate(local, _sign(local, s, max_devices=3))     # desktop enrolled
    local.post('/api/license/activate', json={'serial_number': s, 'device_id': 'phone-known'})
    ok = local.post('/api/license/login', json={'serial_number': s, 'device_id': 'phone-known'})
    assert ok.status_code == 200
    bad = local.post('/api/license/login', json={'serial_number': s, 'device_id': 'phone-stranger'})
    assert bad.status_code == 403
    assert bad.get_json()['reason'] == 'device_not_recognized'


def test_login_without_device_is_authority(local):
    s = 'DENTAL-A2-LOGIN2'
    _activate(local, _sign(local, s))
    r = local.post('/api/license/login', json={'serial_number': s})   # desktop portal, no device_id
    assert r.status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "login" -v`
Expected: `test_login_rejects_unknown_device` FAILS — current `license_login` issues a token to any caller who knows the serial.

- [ ] **Step 3: Implement the membership gate**

In `license_login` (`:4848`), immediately after the `if not validity['licensed']:` block that returns 403, insert:

```python
    device_id = str(data.get('device_id') or '').strip()
    if device_id:
        cursor.execute(
            'SELECT 1 FROM license_devices WHERE serial_number = ? AND device_id = ? AND is_active = 1',
            (serial_number, device_id))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'error': 'Device not enrolled',
                            'reason': 'device_not_recognized'}), 403
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "login" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_activation_a2.py
rtk git commit -m "feat(license): A2 enforce device membership on /api/license/login"
```

---

### Task 8: Device-membership gate on `/api/license/status`

**Files:**
- Modify: `dental_clinic.py:4968-5016` (`license_status`)
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_status_rejects_unknown_device(local):
    s = 'DENTAL-A2-STAT'
    _activate(local, _sign(local, s, max_devices=3))
    local.post('/api/license/activate', json={'serial_number': s, 'device_id': 'phone-ok'})
    known = local.get('/api/license/status?device_id=phone-ok').get_json()
    assert known['licensed'] is True
    stranger = local.get('/api/license/status?device_id=phone-nope').get_json()
    assert stranger['licensed'] is False
    assert stranger['reason'] == 'device_not_recognized'


def test_status_without_device_answers_from_state(local):
    s = 'DENTAL-A2-STAT2'
    _activate(local, _sign(local, s))
    body = local.get('/api/license/status').get_json()   # desktop portal
    assert body['licensed'] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "status" -v`
Expected: `test_status_rejects_unknown_device` FAILS — current `license_status` ignores `device_id`.

- [ ] **Step 3: Implement the membership gate**

In `license_status` (`:4968`), after `record = fetch_license_record(cursor, active_serial)` and its `if not record:` guard, insert:

```python
    device_id = str(request.args.get('device_id') or '').strip()
    if device_id:
        cursor.execute(
            'SELECT 1 FROM license_devices WHERE serial_number = ? AND device_id = ? AND is_active = 1',
            (record['serial_number'], device_id))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'licensed': False, 'reason': 'device_not_recognized',
                            'serial_number': record['serial_number']})
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "status" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_license_activation_a2.py
rtk git commit -m "feat(license): A2 enforce device membership on /api/license/status"
```

---

### Task 9: Server-derived fingerprint + no-500 fuzz

**Files:**
- Test: `tests/test_license_activation_a2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_server_fingerprint_is_stable_and_client_cannot_override(local):
    s = 'DENTAL-A2-FP'
    _activate(local, _sign(local, s, max_devices=3), device_id='attacker-claims-this')
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    fp = conn.execute("SELECT value FROM app_settings WHERE key='device_fingerprint'").fetchone()[0]
    # The desktop's own slot is bound to the server fingerprint, never the client claim.
    rows = [r[0] for r in conn.execute(
        'SELECT device_id FROM license_devices WHERE serial_number=?', (s,)).fetchall()]
    conn.close()
    assert fp in rows
    assert 'attacker-claims-this' not in rows


@pytest.mark.parametrize('body', [
    {}, {'serial_token': ''}, {'serial_token': 'x' * 5000},
    {'serial_number': 'DENTAL-A2-FUZZ'}, {'serial_number': 'DENTAL-A2-FUZZ', 'device_id': 'd' * 5000},
])
def test_activate_never_500s(local, body):
    r = local.post('/api/license/activate', json=body)
    assert r.status_code in (200, 400, 403)
```

- [ ] **Step 2: Run to verify it fails (or passes)**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -k "fingerprint or never_500" -v`
Expected: PASS if Tasks 1–6 are correct. If `test_activate_never_500s` surfaces a 500, harden the offending branch (most likely a missing `.strip()`/`int()` guard) until it returns 400/403.

- [ ] **Step 3: Implement (only if a 500 surfaced)**

Add guards where the fuzz test found a 500. No change if green.

- [ ] **Step 4: Run the whole A2 suite**

Run: `rtk proxy python -m pytest tests/test_license_activation_a2.py -v`
Expected: all PASS (one XFAIL: `test_baked_public_key_is_real`). `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_license_activation_a2.py dental_clinic.py
rtk git commit -m "test(license): A2 server-fingerprint binding + no-500 fuzz"
```

---

### Task 10: Full regression + py_compile + README

**Files:**
- Modify: `README.md` (test-count line)

- [ ] **Step 1: Byte-compile + run the FULL suite (no regressions)**

```bash
rtk proxy python -m py_compile dental_clinic.py
rtk proxy python -m pytest tests/ -q
```
Expected: `py_compile` silent (exit 0); the full suite passes (A1's 321 + the new A2 tests). Check `$LASTEXITCODE` == 0. If any A1 test regressed, fix the implementation — not the A1 test.

- [ ] **Step 2: Update the README test count**

Open `README.md`, find the "tests across N suites" line (last set during A1) and bump it to include `tests/test_license_activation_a2.py` (one new suite, +~20 tests). Keep the wording style identical.

- [ ] **Step 3: Commit**

```bash
rtk git add README.md
rtk git commit -m "docs: A2 — record local-activation hardening test suite"
```

- [ ] **Step 4: Push + note on PR #3 (or a new PR)**

```bash
rtk git push
```
If A2 should ride on the existing `feat/licensing-overhaul` branch / PR #3, push there; otherwise open a follow-up PR `feat(license): A2 local-server activation hardening` summarising the signature gate, token-sourced fields, cloud-validate-and-cache, grace-bypass fix, and membership gates.

---

## Self-Review (run after the plan is implemented)

1. **Spec coverage:** signature gate (T1), baked key (T2), token-sourced fields (T3), grace fix (T4), cloud-authoritative + offline fallback (T5), LAN attach + device cap (T6), `/login` membership (T7), `/status` membership (T8), server fingerprint + no-500 (T9), regression + docs (T10). Every "In" bullet of the spec maps to a task. ✅
2. **Placeholder scan:** the only intentional placeholder is `_BAKED_SERIAL_PUBLIC_KEY = 'REPLACE_WITH_REAL_VENDOR_PUBLIC_KEY_BASE64'`, guarded by an xfail test and a code comment telling the vendor to paste the real key. Tests never depend on it (they monkeypatch `_SERIAL_PUBLIC_KEY_B64`).
3. **Type/name consistency:** `_activate_primary`, `_activate_lan_attach`, `_get_or_create_device_fingerprint`, `_iso_to_window_date`, `_license_cloud_url`, `_validate_with_cloud` are named identically across the dispatcher and all tasks; `_validate_with_cloud(serial_token, fingerprint, device_name='')` signature matches every call and every monkeypatch stub (`lambda *a, **k: …`).

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-licensing-a2-local-activation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks. Note the prior 5-way parallel fan-out hit the account session limit, so run subagents **one at a time**, not in parallel.
2. **Inline Execution** — implement Tasks 1–10 in-session with checkpoints (recommended given the budget situation; I already hold the activation-code context).

**Which approach?** (Or continue to the next plan — A3 — first, since you asked for all five.)
