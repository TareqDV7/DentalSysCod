# Licensing A1 — Cloud License Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cloud node the cryptographic authority for serial validity, device caps, and subscription/revocation state, exposed via `POST /api/license/validate`.

**Architecture:** Replace the HMAC serial signature with Ed25519 (vendor private key signs, public key verifies). Add two tables to `cloud_master.db` (`license_serials`, `license_device_slots`). Add a cloud-only `/api/license/validate` endpoint that verifies the signature, registers the serial on first use, enforces subscription/revocation status, and claims a device slot inside one atomic transaction. Add an admin revoke endpoint and `ProxyFix`. Backend only — no client/UX change (those are A2/A3).

**Tech Stack:** Python 3.10+, Flask, SQLite (`cloud_master.db`), `cryptography` (Ed25519), pytest. Spec: `docs/superpowers/specs/2026-06-03-licensing-a1-cloud-authority-design.md`.

---

## File structure

- `requirements.txt` — add `cryptography`.
- `serial_generator.py` — Ed25519 keypair generation + signing primitives; remove the demo-key fallback. (The vendor signer; A1 lands the crypto core, sub-project D adds the GUI.)
- `dental_clinic.py` — Ed25519 verifier (`_serial_public_key`, rewritten `_verify_serial_token`); two new cloud tables in `init_database`; `POST /api/license/validate`; `POST /api/license/admin/revoke`; `ProxyFix` on the WSGI app; register call-site update.
- `tests/test_serial_ed25519.py` — NEW: keypair + sign/verify round-trip, demo-key removal.
- `tests/test_license_authority.py` — NEW: the validate + admin endpoints.
- `tests/test_cloud_mode.py` — MODIFY: the existing HMAC signed-serial tests switch to Ed25519.

Conventions to follow (verified in the codebase):
- Cloud tests use a `cloud` fixture that monkeypatches `CLOUD_MODE`, `_DATA_DIR`, `MASTER_DB_PATH`, `DB_NAME` and runs `init_database()` (see `tests/test_cloud_mode.py:16-33`). There is **no `conftest.py`** — each test file defines its own fixture.
- Cloud-only endpoints connect directly to `MASTER_DB_PATH` and are listed in `_CLOUD_OPEN_EXACT` (`dental_clinic.py:192`) so they bypass tenant-token routing (pattern: `register_clinic`, `dental_clinic.py:4135`).
- Run a single test: `python -m pytest tests/test_x.py::test_name -v`. The full suite: `python -m pytest tests/ -q` (check `$LASTEXITCODE`; summary output is suppressed by the local harness).

---

### Task 1: Ed25519 dependency + signing primitives in `serial_generator.py`

**Files:**
- Modify: `requirements.txt`
- Modify: `serial_generator.py`
- Test: `tests/test_serial_ed25519.py` (create)

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add a line:

```
cryptography>=42.0
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_serial_ed25519.py`:

```python
import base64
import pytest
import serial_generator


def test_generate_keypair_roundtrips():
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    assert isinstance(priv_b64, str) and isinstance(pub_b64, str)
    # 32-byte raw seed / public key
    assert len(base64.b64decode(priv_b64)) == 32
    assert len(base64.b64decode(pub_b64)) == 32


def test_sign_and_verify_token():
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    payload = {'v': 2, 'serial': 'DENTAL-AAAA-0001', 'max_devices': 3}
    token = serial_generator.sign_serial_token(payload, priv_b64)
    assert token.count('.') == 1
    ok, got = serial_generator.verify_serial_token(token, pub_b64)
    assert ok is True
    assert got['serial'] == 'DENTAL-AAAA-0001'


def test_tampered_token_fails():
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    token = serial_generator.sign_serial_token({'serial': 'X'}, priv_b64)
    payload_part, sig_part = token.split('.')
    bad = base64.urlsafe_b64encode(b'{"serial":"Y"}').decode().rstrip('=')
    ok, _ = serial_generator.verify_serial_token(f'{bad}.{sig_part}', pub_b64)
    assert ok is False


def test_random_string_fails():
    _, pub_b64 = serial_generator.generate_keypair()
    ok, _ = serial_generator.verify_serial_token('not-a-token', pub_b64)
    assert ok is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_serial_ed25519.py -v`
Expected: FAIL — `AttributeError: module 'serial_generator' has no attribute 'generate_keypair'`.

- [ ] **Step 4: Implement the primitives**

In `serial_generator.py`, add near the top (after the existing imports):

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def generate_keypair():
    """Return (private_seed_b64, public_key_b64) for a fresh Ed25519 keypair.
    The private seed is 32 raw bytes, base64 (std) encoded."""
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
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    sig = priv.sign(payload_json)
    return f'{_b64u(payload_json)}.{_b64u(sig)}'


def verify_serial_token(token: str, public_key_b64: str):
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
        return True, json.loads(payload_bytes.decode('utf-8'))
    except (InvalidSignature, ValueError, UnicodeDecodeError):
        return False, None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_serial_ed25519.py -v`
Expected: PASS (4 passed). If `cryptography` isn't installed: `pip install -r requirements.txt`.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt serial_generator.py tests/test_serial_ed25519.py
git commit -m "feat(license): Ed25519 keypair + serial token sign/verify primitives"
```

---

### Task 2: Ed25519 verifier in `dental_clinic.py` (replace the HMAC path)

**Files:**
- Modify: `dental_clinic.py:222-233` (env + key helper), `:236-279` (`_verify_serial_token`), `:4163-4170` (register call site)
- Test: `tests/test_serial_ed25519.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_serial_ed25519.py`:

```python
import dental_clinic


def test_dental_verifier_accepts_valid_token(monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    token = serial_generator.sign_serial_token(
        {'serial': 'DENTAL-AAAA-0001', 'max_devices': 3,
         'grace_until': '2999-01-01T00:00:00Z'}, priv_b64)
    ok, reason, payload = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', token)
    assert ok is True, reason
    assert payload['max_devices'] == 3


def test_dental_verifier_rejects_random(monkeypatch):
    _, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    ok, reason, payload = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', 'garbage')
    assert ok is False and payload is None


def test_dental_verifier_rejects_serial_mismatch(monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    token = serial_generator.sign_serial_token({'serial': 'OTHER-0002'}, priv_b64)
    ok, reason, _ = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', token)
    assert ok is False


def test_dental_verifier_malformed_grace_is_rejected(monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    token = serial_generator.sign_serial_token(
        {'serial': 'DENTAL-AAAA-0001', 'grace_until': 'never'}, priv_b64)
    ok, reason, _ = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', token)
    assert ok is False  # malformed grace must hard-fail, not silently pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_serial_ed25519.py -k dental -v`
Expected: FAIL — `_verify_serial_token` takes 3 args / returns 2-tuple, and `_SERIAL_PUBLIC_KEY_B64` doesn't exist yet.

- [ ] **Step 3: Replace the env + key helper**

In `dental_clinic.py`, replace lines 222-233 (the `_SERIAL_SIGNING_KEY_B64` block and `_serial_signing_key`) with:

```python
# Ed25519 public key used to verify vendor-signed serials. Base64 (std) of the
# 32-byte raw public key. The matching private seed never leaves the vendor
# machine (serial_generator.py). When unset, the signature gate can't run.
_SERIAL_PUBLIC_KEY_B64 = os.environ.get('CLINIC_SERIAL_PUBLIC_KEY', '').strip()
_REQUIRE_SIGNED_SERIAL = os.environ.get('CLINIC_REQUIRE_SIGNED_SERIAL', '1').strip().lower() in ('1', 'true', 'yes', 'on')


def _serial_public_key():
    """Return an Ed25519PublicKey, or None if not configured."""
    if not _SERIAL_PUBLIC_KEY_B64:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(_SERIAL_PUBLIC_KEY_B64))
    except Exception:  # noqa: BLE001 - any decode/lib error → treat as unconfigured
        return None
```

Note: `_REQUIRE_SIGNED_SERIAL` now defaults to **on** (`'1'`) — A1 makes the signature mandatory at the authority.

- [ ] **Step 4: Rewrite `_verify_serial_token`**

Replace `dental_clinic.py:236-279` with:

```python
def _verify_serial_token(serial, token):
    """Return (ok, reason, payload). Verifies the Ed25519 vendor signature on
    ``token`` (payload.signature, base64url), that its payload's ``serial`` equals
    ``serial``, and that grace_until (if present) is in the future and well-formed."""
    if not token:
        return False, 'serial token required', None
    pub = _serial_public_key()
    if pub is None:
        return False, 'server signing key not configured', None
    try:
        from cryptography.exceptions import InvalidSignature
        payload_part, sig_part = str(token).split('.', 1)
        payload_bytes = base64.urlsafe_b64decode(payload_part + '=' * (-len(payload_part) % 4))
        sig = base64.urlsafe_b64decode(sig_part + '=' * (-len(sig_part) % 4))
    except (ValueError, binascii.Error):
        return False, 'malformed serial token', None
    try:
        pub.verify(sig, payload_bytes)
    except InvalidSignature:
        return False, 'invalid serial token signature', None
    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return False, 'malformed serial token payload', None
    if str(payload.get('serial') or '').strip().upper() != serial.strip().upper():
        return False, 'serial token does not match this serial', None
    grace = str(payload.get('grace_until') or '').strip()
    if grace:
        try:
            if _naive_utc_now() > datetime.fromisoformat(grace.rstrip('Z')):
                return False, 'serial token has expired', None
        except ValueError:
            return False, 'malformed grace_until in serial token', None  # hard-fail
    return True, '', payload
```

- [ ] **Step 5: Update the register call site**

In `dental_clinic.py`, replace lines 4163-4170 (the signing gate inside `register_clinic`) with:

```python
    # Ed25519 vendor-signature gate. Mandatory by default (A1). The validate
    # endpoint is the primary authority; register still verifies for safety.
    pub = _serial_public_key()
    if _REQUIRE_SIGNED_SERIAL or offline_token:
        if pub is None:
            return jsonify({'error': 'Server signing key not configured'}), 500
        ok, reason, _payload = _verify_serial_token(serial_number, offline_token)
        if not ok:
            return jsonify({'error': reason}), 403
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_serial_ed25519.py -v`
Expected: PASS (8 passed).

- [ ] **Step 7: Commit**

```bash
git add dental_clinic.py tests/test_serial_ed25519.py
git commit -m "feat(license): Ed25519 verifier replaces HMAC; mandatory by default; grace hard-fail"
```

---

### Task 3: Update existing cloud-mode signed-serial tests to Ed25519

**Files:**
- Modify: `tests/test_cloud_mode.py:134-147` (`_sign_serial`) and the tests that use it (~150 onward)

- [ ] **Step 1: See which tests break**

Run: `python -m pytest tests/test_cloud_mode.py -v`
Expected: the signed-serial tests (e.g. `test_register_accepts_valid_signed_token`) now FAIL, because `register_clinic` verifies Ed25519 but `_sign_serial` still emits HMAC and the tests set `CLINIC_SERIAL_SIGNING_KEY`.

- [ ] **Step 2: Replace the `_sign_serial` helper**

Replace `tests/test_cloud_mode.py:134-147` with:

```python
def _make_keypair_and_patch(monkeypatch):
    """Generate a test Ed25519 keypair and point the verifier at the public key.
    Returns the private seed (b64) for signing test tokens."""
    import serial_generator
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    return priv_b64


def _sign_serial(serial, priv_b64, *, clinic_name='Signed Clinic', expiry_days=365):
    """Build a v2 Ed25519 serial token (same shape serial_generator emits)."""
    import serial_generator
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {
        'v': 2, 'serial': serial, 'clinic_name': clinic_name, 'max_devices': 3,
        'issued_at': now.isoformat() + 'Z',
        'expires_at': (now + timedelta(days=expiry_days)).isoformat() + 'Z',
        'grace_until': (now + timedelta(days=expiry_days + 30)).isoformat() + 'Z',
    }
    return serial_generator.sign_serial_token(payload, priv_b64)
```

- [ ] **Step 3: Fix the call sites**

For each test below `_sign_serial` that previously did
`key = b'...'; monkeypatch.setattr(dental_clinic, '_SERIAL_SIGNING_KEY_B64', base64.b64encode(key)...)`,
replace the key setup with `priv = _make_keypair_and_patch(monkeypatch)` and pass `priv` to `_sign_serial(...)`. Remove any `monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', ...)` that assumed the old default-off — the default is now on. A test that expects an **unsigned** register to succeed must explicitly set `monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', False)`.

(Read each failing test and apply the substitution; the bodies otherwise stay the same.)

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_cloud_mode.py -v`
Expected: PASS (all). Note `test_register_validates_input` and the plain unsigned `_register(...)` calls in earlier tests: since `_REQUIRE_SIGNED_SERIAL` now defaults on, add `monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', '')` is NOT enough (that returns 500). Instead set `monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', False)` in the `cloud` fixture so the *non-signature* tests (tenant isolation, etc.) keep registering with bare serials. Add that one line to the existing `cloud` fixture (`tests/test_cloud_mode.py:16-33`).

- [ ] **Step 5: Commit**

```bash
git add tests/test_cloud_mode.py
git commit -m "test(license): port cloud-mode signed-serial tests to Ed25519"
```

---

### Task 4: Cloud tables — `license_serials` + `license_device_slots`

**Files:**
- Modify: `dental_clinic.py:896` (after the `clinics` CREATE TABLE block)
- Test: `tests/test_license_authority.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_license_authority.py`:

```python
import sqlite3
import pytest
import serial_generator
import dental_clinic


@pytest.fixture()
def cloud(tmp_path, monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    data_dir = tmp_path / 'clouddata'
    data_dir.mkdir()
    master = str(data_dir / 'cloud_master.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', master)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', dental_clinic._DbPathProxy(master))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', data_dir / 'uploads')
    (data_dir / 'uploads').mkdir(exist_ok=True)
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    monkeypatch.setattr(dental_clinic, '_register_attempts', {})
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        c.priv_b64 = priv_b64
        yield c
    dental_clinic._set_request_db_path(None)


def _columns(master_path, table):
    conn = sqlite3.connect(master_path)
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]
    conn.close()
    return cols


def test_license_tables_exist(cloud):
    cols = _columns(dental_clinic.MASTER_DB_PATH, 'license_serials')
    assert {'serial', 'status', 'max_devices', 'expires_at', 'grace_until'} <= set(cols)
    slot_cols = _columns(dental_clinic.MASTER_DB_PATH, 'license_device_slots')
    assert {'serial', 'device_fingerprint', 'is_active'} <= set(slot_cols)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_license_authority.py::test_license_tables_exist -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: license_serials` (PRAGMA returns empty → assertion fails).

- [ ] **Step 3: Add the tables**

In `dental_clinic.py`, immediately after the `clinics` CREATE TABLE block (after line 896), insert:

```python
    # Cloud license authority (A1). Source of truth for subscription + revocation
    # and per-serial device caps. Only populated on the cloud master DB.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_serials (
            serial      TEXT PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'active',
            plan_name   TEXT,
            max_devices INTEGER NOT NULL DEFAULT 3,
            issued_at   TEXT,
            expires_at  TEXT,
            grace_until TEXT,
            clinic_id   INTEGER,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_device_slots (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            serial             TEXT NOT NULL,
            device_fingerprint TEXT NOT NULL,
            device_name        TEXT,
            claimed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active          INTEGER NOT NULL DEFAULT 1,
            UNIQUE(serial, device_fingerprint)
        )
    ''')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_license_authority.py::test_license_tables_exist -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_license_authority.py
git commit -m "feat(license): cloud license_serials + license_device_slots tables"
```

---

### Task 5: `POST /api/license/validate` — signature + register-on-first-use

**Files:**
- Modify: `dental_clinic.py:192` (`_CLOUD_OPEN_EXACT`), and add the route near `register_clinic` (~4229)
- Test: `tests/test_license_authority.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_license_authority.py`:

```python
def _sign(client, serial, **kw):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {
        'v': 2, 'serial': serial, 'clinic_name': 'C', 'max_devices': kw.get('max_devices', 3),
        'issued_at': now.isoformat() + 'Z',
        'expires_at': (now + timedelta(days=kw.get('expiry_days', 365))).isoformat() + 'Z',
        'grace_until': (now + timedelta(days=kw.get('expiry_days', 365) + 14)).isoformat() + 'Z',
    }
    return serial_generator.sign_serial_token(payload, client.priv_b64)


def _validate(client, token, fp='device-1'):
    return client.post('/api/license/validate',
                       json={'serial_token': token, 'device_fingerprint': fp})


def test_validate_accepts_signed_serial(cloud):
    r = _validate(cloud, _sign(cloud, 'DENTAL-VAL-0001'))
    assert r.status_code == 200
    body = r.get_json()
    assert body['valid'] is True
    assert body['status'] == 'active'


def test_validate_rejects_random(cloud):
    r = _validate(cloud, 'not-a-real-token')
    assert r.status_code == 200
    assert r.get_json()['valid'] is False
    assert r.get_json()['reason'] in ('bad_signature', 'malformed')


def test_validate_registers_on_first_use(cloud):
    _validate(cloud, _sign(cloud, 'DENTAL-VAL-0002'))
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    row = conn.execute("SELECT status FROM license_serials WHERE serial='DENTAL-VAL-0002'").fetchone()
    conn.close()
    assert row is not None and row[0] == 'active'


def test_validate_is_404_when_not_cloud(monkeypatch, tmp_path):
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'x.db'))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        assert c.post('/api/license/validate', json={'serial_token': 't', 'device_fingerprint': 'd'}).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_license_authority.py -k validate -v`
Expected: FAIL — 404 for all (route doesn't exist yet).

- [ ] **Step 3: Register the open path**

In `dental_clinic.py:192`, add `/api/license/validate` to `_CLOUD_OPEN_EXACT`:

```python
_CLOUD_OPEN_EXACT = {'/api/clinics/register', '/api/system/readiness', '/api/license/offline-verify', '/api/license/validate', '/healthz', '/logo', '/favicon.ico'}
```

- [ ] **Step 4: Add the route (signature + register-on-first-use only for now)**

In `dental_clinic.py`, after `register_clinic` (after line 4228), add:

```python
@app.route('/api/license/validate', methods=['POST'])
def validate_license():
    """Cloud node only: the license authority. Verify a vendor-signed serial,
    register it on first use, enforce status/subscription/device-cap, and claim a
    device slot. Returns {valid, reason, status, expires_at, grace_until,
    remaining_slots, plan_name}. Business failures are HTTP 200 with valid=false."""
    if not CLOUD_MODE:
        return jsonify({'error': 'Not available on a local server'}), 404
    limited = _check_register_rate_limit()
    if limited is not None:
        return limited

    data = request.json or {}
    token = str(data.get('serial_token') or '').strip()
    fingerprint = str(data.get('device_fingerprint') or '').strip()
    device_name = str(data.get('device_name') or '').strip()
    if not token or not fingerprint:
        return jsonify({'error': 'serial_token and device_fingerprint are required'}), 400

    # Verify signature. The serial id is inside the signed payload, so derive it
    # from the payload rather than trusting a separate field.
    pub = _serial_public_key()
    if pub is None:
        app.logger.error('validate_license: CLINIC_SERIAL_PUBLIC_KEY not configured')
        return jsonify({'error': 'Server signing key not configured'}), 500
    try:
        from cryptography.exceptions import InvalidSignature
        payload_part, sig_part = token.split('.', 1)
        payload_bytes = base64.urlsafe_b64decode(payload_part + '=' * (-len(payload_part) % 4))
        sig = base64.urlsafe_b64decode(sig_part + '=' * (-len(sig_part) % 4))
        pub.verify(sig, payload_bytes)
        payload = json.loads(payload_bytes.decode('utf-8'))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return jsonify({'valid': False, 'reason': 'malformed'})
    except InvalidSignature:
        return jsonify({'valid': False, 'reason': 'bad_signature'})

    serial = str(payload.get('serial') or '').strip().upper()
    if len(serial) < 8:
        return jsonify({'valid': False, 'reason': 'bad_serial'})

    conn = sqlite3.connect(MASTER_DB_PATH)
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            'SELECT status, max_devices, expires_at, grace_until, plan_name '
            'FROM license_serials WHERE serial = ?', (serial,)).fetchone()
        if row is None:
            conn.execute(
                'INSERT INTO license_serials (serial, status, plan_name, max_devices, '
                'issued_at, expires_at, grace_until) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (serial, 'active', payload.get('plan_name'),
                 int(payload.get('max_devices') or 3),
                 payload.get('issued_at'), payload.get('expires_at'),
                 payload.get('grace_until')))
            status = 'active'
            max_devices = int(payload.get('max_devices') or 3)
            expires_at = payload.get('expires_at')
            grace_until = payload.get('grace_until')
            plan_name = payload.get('plan_name')
        else:
            status, max_devices, expires_at, grace_until, plan_name = row
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        'valid': True, 'status': status, 'plan_name': plan_name,
        'expires_at': expires_at, 'grace_until': grace_until,
        'remaining_slots': max_devices,
    })
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_license_authority.py -k validate -v`
Expected: PASS (4 passed). (Status/cap come in Tasks 6-7; `remaining_slots` is provisional here.)

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_license_authority.py
git commit -m "feat(license): /api/license/validate — signature + register-on-first-use"
```

---

### Task 6: `validate` — status, subscription, and renewal gates

**Files:**
- Modify: `dental_clinic.py` (the `validate_license` body, between the register-on-first-use block and the final return)
- Test: `tests/test_license_authority.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_license_authority.py`:

```python
def _set_serial(serial, **cols):
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    sets = ', '.join(f'{k} = ?' for k in cols)
    conn.execute(f'UPDATE license_serials SET {sets} WHERE serial = ?',
                 (*cols.values(), serial))
    conn.commit(); conn.close()


def test_validate_blocks_revoked(cloud):
    _validate(cloud, _sign(cloud, 'DENTAL-REV-0001'))      # register
    _set_serial('DENTAL-REV-0001', status='revoked')
    body = _validate(cloud, _sign(cloud, 'DENTAL-REV-0001')).get_json()
    assert body['valid'] is False and body['reason'] == 'revoked'


def test_validate_expired_past_grace(cloud):
    tok = _sign(cloud, 'DENTAL-EXP-0001', expiry_days=-60)  # expired 60d ago, grace 14d
    body = _validate(cloud, tok).get_json()
    assert body['valid'] is False and body['reason'] == 'expired'


def test_validate_within_grace_ok(cloud):
    tok = _sign(cloud, 'DENTAL-GRC-0001', expiry_days=-5)   # expired 5d ago, still in 14d grace
    assert _validate(cloud, tok).get_json()['valid'] is True


def test_validate_renewal_extends_and_reactivates(cloud):
    _validate(cloud, _sign(cloud, 'DENTAL-RENEW-1', expiry_days=-60))  # expired
    assert _validate(cloud, _sign(cloud, 'DENTAL-RENEW-1', expiry_days=-60)).get_json()['reason'] == 'expired'
    body = _validate(cloud, _sign(cloud, 'DENTAL-RENEW-1', expiry_days=365)).get_json()  # renew
    assert body['valid'] is True and body['status'] == 'active'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_license_authority.py -k "revoked or expired or grace or renewal" -v`
Expected: FAIL — validate currently returns `valid:true` regardless of status/expiry.

- [ ] **Step 3: Implement the gates + renewal**

In `validate_license`, replace the `else: status, max_devices, ... = row` branch and the section up to `conn.commit()` with the full status/renewal logic:

```python
        token_exp = payload.get('expires_at')
        if row is None:
            status = 'active'
            max_devices = int(payload.get('max_devices') or 3)
            expires_at, grace_until, plan_name = token_exp, payload.get('grace_until'), payload.get('plan_name')
            conn.execute(
                'INSERT INTO license_serials (serial, status, plan_name, max_devices, '
                'issued_at, expires_at, grace_until) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (serial, status, plan_name, max_devices, payload.get('issued_at'),
                 expires_at, grace_until))
        else:
            status, max_devices, expires_at, grace_until, plan_name = row
            # Renewal: a later-signed token extends the window and reactivates.
            if token_exp and (not expires_at or token_exp > expires_at):
                expires_at = token_exp
                grace_until = payload.get('grace_until')
                max_devices = int(payload.get('max_devices') or max_devices)
                plan_name = payload.get('plan_name') or plan_name
                if status == 'expired':
                    status = 'active'
                conn.execute(
                    'UPDATE license_serials SET expires_at=?, grace_until=?, '
                    'max_devices=?, plan_name=?, status=?, updated_at=CURRENT_TIMESTAMP '
                    'WHERE serial=?',
                    (expires_at, grace_until, max_devices, plan_name, status, serial))

        # Status gate (revoked/suspended).
        if status in ('revoked', 'suspended'):
            conn.commit()
            return jsonify({'valid': False, 'reason': status, 'status': status})

        # Subscription gate: past grace_until → expired.
        if grace_until:
            try:
                if _naive_utc_now() > datetime.fromisoformat(str(grace_until).rstrip('Z')):
                    conn.execute("UPDATE license_serials SET status='expired', updated_at=CURRENT_TIMESTAMP WHERE serial=?", (serial,))
                    conn.commit()
                    return jsonify({'valid': False, 'reason': 'expired',
                                    'status': 'expired', 'expires_at': expires_at,
                                    'grace_until': grace_until})
            except ValueError:
                pass  # unparseable stored grace → treat as non-expiring
        conn.commit()
```

(The `return jsonify({'valid': True, ...})` at the end of the function stays.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_license_authority.py -k "revoked or expired or grace or renewal" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_license_authority.py
git commit -m "feat(license): validate enforces status, subscription expiry, and renewal"
```

---

### Task 7: `validate` — atomic device-slot cap

**Files:**
- Modify: `dental_clinic.py` (`validate_license`, after the status/subscription gates, before the final return)
- Test: `tests/test_license_authority.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_license_authority.py`:

```python
def test_device_cap_claims_and_blocks(cloud):
    s = 'DENTAL-CAP-0001'
    assert _validate(cloud, _sign(cloud, s, max_devices=2), fp='d1').get_json()['valid'] is True
    assert _validate(cloud, _sign(cloud, s, max_devices=2), fp='d2').get_json()['valid'] is True
    body = _validate(cloud, _sign(cloud, s, max_devices=2), fp='d3').get_json()
    assert body['valid'] is False and body['reason'] == 'device_cap_reached'


def test_device_reclaim_is_idempotent(cloud):
    s = 'DENTAL-CAP-0002'
    _validate(cloud, _sign(cloud, s, max_devices=1), fp='same')
    body = _validate(cloud, _sign(cloud, s, max_devices=1), fp='same').get_json()
    assert body['valid'] is True and body['remaining_slots'] == 0


def test_device_cap_atomic_under_concurrency(cloud):
    import threading
    s = 'DENTAL-CAP-0003'
    _validate(cloud, _sign(cloud, s, max_devices=2), fp='warm')  # create serial row (cap 2, 1 used)
    results = []
    def hit(i):
        with dental_clinic.app.test_client() as c:
            c.priv_b64 = cloud.priv_b64
            results.append(_validate(c, _sign(c, s, max_devices=2), fp=f'race-{i}').get_json()['valid'])
    threads = [threading.Thread(target=hit, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    active = conn.execute("SELECT COUNT(*) FROM license_device_slots WHERE serial=? AND is_active=1", (s,)).fetchone()[0]
    conn.close()
    assert active <= 2, f'cap exceeded: {active} active slots'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_license_authority.py -k "cap or reclaim" -v`
Expected: FAIL — no slot accounting yet (3rd device still validates; remaining_slots wrong).

- [ ] **Step 3: Implement the slot claim (inside the same transaction, before `conn.commit()` / final return)**

In `validate_license`, replace the final `conn.commit()` (added in Task 6) and the trailing return with slot logic. After the subscription gate, add:

```python
        # Device slot — idempotent re-claim, else enforce the cap. Still inside
        # the BEGIN IMMEDIATE transaction so count-then-insert can't race.
        slot = conn.execute(
            'SELECT id FROM license_device_slots WHERE serial=? AND device_fingerprint=?',
            (serial, fingerprint)).fetchone()
        if slot is not None:
            conn.execute('UPDATE license_device_slots SET last_seen_at=CURRENT_TIMESTAMP, '
                         'is_active=1, device_name=? WHERE id=?', (device_name, slot[0]))
        else:
            active = conn.execute(
                'SELECT COUNT(*) FROM license_device_slots WHERE serial=? AND is_active=1',
                (serial,)).fetchone()[0]
            if active >= int(max_devices):
                conn.commit()
                return jsonify({'valid': False, 'reason': 'device_cap_reached',
                                'status': status, 'max_devices': int(max_devices)})
            conn.execute('INSERT INTO license_device_slots (serial, device_fingerprint, device_name) '
                         'VALUES (?, ?, ?)', (serial, fingerprint, device_name))
        used = conn.execute(
            'SELECT COUNT(*) FROM license_device_slots WHERE serial=? AND is_active=1',
            (serial,)).fetchone()[0]
        conn.commit()
```

Then update the final return to use real remaining slots:

```python
    return jsonify({
        'valid': True, 'status': status, 'plan_name': plan_name,
        'expires_at': expires_at, 'grace_until': grace_until,
        'remaining_slots': max(0, int(max_devices) - used),
    })
```

(Move `used` into scope by computing it inside the `try` before `conn.close()`; the function-level `return` reads it — keep `used` assigned on every non-early-return path.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_license_authority.py -k "cap or reclaim" -v`
Expected: PASS (3 passed), including the concurrency test (≤2 active slots).

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_license_authority.py
git commit -m "feat(license): atomic device-slot cap in /api/license/validate"
```

---

### Task 8: Admin revoke / suspend / release endpoint

**Files:**
- Modify: `dental_clinic.py:192` (`_CLOUD_OPEN_EXACT` — NOT added; admin is token-gated, not open), add route after `validate_license`
- Test: `tests/test_license_authority.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_license_authority.py`:

```python
def test_admin_revoke_requires_token(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    _validate(cloud, _sign(cloud, 'DENTAL-ADM-0001'))
    no_tok = cloud.post('/api/license/admin/revoke', json={'serial': 'DENTAL-ADM-0001', 'status': 'revoked'})
    assert no_tok.status_code == 401
    ok = cloud.post('/api/license/admin/revoke',
                    headers={'X-Admin-Token': 'secret'},
                    json={'serial': 'DENTAL-ADM-0001', 'status': 'revoked'})
    assert ok.status_code == 200
    assert _validate(cloud, _sign(cloud, 'DENTAL-ADM-0001')).get_json()['reason'] == 'revoked'


def test_admin_release_frees_slot(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    s = 'DENTAL-ADM-0002'
    _validate(cloud, _sign(cloud, s, max_devices=1), fp='phone-A')
    assert _validate(cloud, _sign(cloud, s, max_devices=1), fp='phone-B').get_json()['reason'] == 'device_cap_reached'
    cloud.post('/api/license/admin/revoke', headers={'X-Admin-Token': 'secret'},
               json={'serial': s, 'device_fingerprint': 'phone-A', 'release': True})
    assert _validate(cloud, _sign(cloud, s, max_devices=1), fp='phone-B').get_json()['valid'] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_license_authority.py -k admin -v`
Expected: FAIL — route missing (404), `_ADMIN_API_TOKEN` missing.

- [ ] **Step 3: Add the admin-token global**

Near `_SERIAL_PUBLIC_KEY_B64` (after line 223), add:

```python
_ADMIN_API_TOKEN = os.environ.get('CLINIC_ADMIN_API_TOKEN', '').strip()
```

- [ ] **Step 4: Add the route (after `validate_license`)**

```python
@app.route('/api/license/admin/revoke', methods=['POST'])
def license_admin():
    """Cloud node only, admin-token gated. Set a serial's status (revoked/suspended/
    active), or release a device slot (release=true frees one fingerprint)."""
    if not CLOUD_MODE:
        return jsonify({'error': 'Not available on a local server'}), 404
    supplied = (request.headers.get('X-Admin-Token') or '').strip()
    if not _ADMIN_API_TOKEN or not hmac.compare_digest(supplied, _ADMIN_API_TOKEN):
        return jsonify({'error': 'admin token required'}), 401
    data = request.json or {}
    serial = str(data.get('serial') or '').strip().upper()
    if len(serial) < 8:
        return jsonify({'error': 'serial is required'}), 400
    conn = sqlite3.connect(MASTER_DB_PATH)
    try:
        if data.get('release') and data.get('device_fingerprint'):
            conn.execute('UPDATE license_device_slots SET is_active=0 '
                         'WHERE serial=? AND device_fingerprint=?',
                         (serial, str(data['device_fingerprint']).strip()))
        else:
            status = str(data.get('status') or 'revoked').strip()
            if status not in ('active', 'revoked', 'suspended'):
                return jsonify({'error': 'invalid status'}), 400
            conn.execute('UPDATE license_serials SET status=?, updated_at=CURRENT_TIMESTAMP '
                         'WHERE serial=?', (status, serial))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_license_authority.py -k admin -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_license_authority.py
git commit -m "feat(license): admin revoke/suspend/release-slot endpoint (token-gated)"
```

---

### Task 9: ProxyFix — trust the real client IP behind Caddy

**Files:**
- Modify: `dental_clinic.py:72` (right after `app = Flask(__name__)`)
- Test: `tests/test_license_authority.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_license_authority.py`:

```python
def test_proxyfix_uses_forwarded_for(cloud):
    # Behind one proxy hop, _client_ip must reflect X-Forwarded-For's client entry.
    with dental_clinic.app.test_request_context(
            '/api/license/validate',
            environ_overrides={'HTTP_X_FORWARDED_FOR': '203.0.113.9',
                               'REMOTE_ADDR': '10.0.0.1'}):
        assert dental_clinic._client_ip() == '203.0.113.9'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_license_authority.py::test_proxyfix_uses_forwarded_for -v`
Expected: it may already pass via the manual `X-Forwarded-For` parse in `_client_ip` — if so, still wire ProxyFix (Step 3) so `request.remote_addr` itself is corrected and the manual parse can be simplified. If it FAILS, proceed.

- [ ] **Step 3: Wire ProxyFix**

In `dental_clinic.py`, immediately after `app = Flask(__name__)` (line 72), add:

```python
from werkzeug.middleware.proxy_fix import ProxyFix
# One proxy hop (Caddy) in the cloud deployment. Makes request.remote_addr and
# the rate limiter trust only the last hop's X-Forwarded-For, not a spoofed header.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```

Then simplify `_client_ip` (line 282-286) to rely on the corrected `remote_addr`:

```python
def _client_ip():
    return request.remote_addr or 'unknown'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_license_authority.py::test_proxyfix_uses_forwarded_for -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -q` then check `$LASTEXITCODE` is 0.
Expected: all green (existing + new license suites).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_license_authority.py
git commit -m "feat(cloud): ProxyFix so rate limiting trusts the real client IP"
```

---

### Task 10: serial_generator CLI → Ed25519 (`--genkey`, sign, remove demo key)

**Files:**
- Modify: `serial_generator.py` (`generate_license_token`, `load_signing_key`, `main`)
- Test: `tests/test_serial_ed25519.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_serial_ed25519.py`:

```python
def test_load_private_seed(tmp_path):
    import json
    priv_b64, _ = serial_generator.generate_keypair()
    f = tmp_path / 'key.json'
    f.write_text(json.dumps({'alg': 'ed25519', 'private': priv_b64}))
    assert serial_generator.load_private_seed(str(f)) == priv_b64


def test_no_demo_key_fallback(tmp_path):
    # A missing key file must NOT silently sign with a baked-in demo key.
    with pytest.raises((SystemExit, FileNotFoundError, ValueError)):
        serial_generator.load_private_seed(str(tmp_path / 'nope.json'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_serial_ed25519.py -k "private_seed or demo" -v`
Expected: FAIL — `load_private_seed` doesn't exist; old `load_signing_key` had a demo fallback.

- [ ] **Step 3: Replace the key loader and signing path**

In `serial_generator.py`: delete `load_signing_key` (lines ~120-136) and the demo-key fallback in `generate_license_token` (the `if signing_key is None:` block, ~72-74). Add:

```python
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
```

Rewrite `generate_license_token` to build the v2 payload (serial, clinic_name, plan_name, max_devices, issued_at, expires_at, grace_until) and call `sign_serial_token(payload, private_seed_b64)`; it takes `private_seed_b64` instead of `signing_key`.

- [ ] **Step 4: Add the `--genkey` subcommand to `main()`**

At the top of `main()`, before the existing argparse, handle a genkey path:

```python
    if len(sys.argv) >= 2 and sys.argv[1] == '--genkey':
        priv_b64, pub_b64 = generate_keypair()
        out = sys.argv[2] if len(sys.argv) >= 3 else 'backend_ed25519_key.json'
        with open(out, 'w') as f:
            json.dump({'alg': 'ed25519', 'private': priv_b64}, f)
        print(f'Private seed written to {out} (KEEP SAFE, gitignored).')
        print(f'Public key (set CLINIC_SERIAL_PUBLIC_KEY on the cloud):\n{pub_b64}')
        return 0
```

Update the `--key-file` handling in `main()` to call `load_private_seed` and pass the seed to `generate_license_token`. Add `backend_ed25519_key.json` to `.gitignore`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_serial_ed25519.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add serial_generator.py tests/test_serial_ed25519.py .gitignore
git commit -m "feat(license): serial_generator Ed25519 CLI + --genkey; remove demo key"
```

---

### Task 11: Packaging + final verification

**Files:**
- Modify: `DentaCare.spec` (`hiddenimports`)
- Modify: `docs/SERIAL_GENERATOR_README.md` (Ed25519 workflow) — only if it documents the HMAC `--key-file` flow

- [ ] **Step 1: Add cryptography to the PyInstaller hidden imports**

In `DentaCare.spec`, add to the `COMMON_HIDDEN` list: `'cryptography'`, `'cryptography.hazmat.primitives.asymmetric.ed25519'`, `'cryptography.hazmat.backends.openssl'`.

- [ ] **Step 2: Update the serial-generator doc**

In `docs/SERIAL_GENERATOR_README.md`, replace the HMAC/`backend_key.json` instructions with the Ed25519 flow: `python serial_generator.py --genkey` once; set `CLINIC_SERIAL_PUBLIC_KEY` on the cloud; sign with `--key-file backend_ed25519_key.json`. Note the demo key is gone.

- [ ] **Step 3: Run the full suite + syntax check**

Run: `python -m pytest tests/ -q` (check `$LASTEXITCODE` == 0) and `python -m py_compile dental_clinic.py serial_generator.py` (no output = OK).
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add DentaCare.spec docs/SERIAL_GENERATOR_README.md
git commit -m "chore(license): bundle cryptography for PyInstaller; doc Ed25519 workflow"
```

---

## Self-review notes

- **Spec coverage:** Ed25519 (T1,T2,T10) · token v2 (T1,T10) · public-key verify + grace hard-fail (T2) · cloud tables (T4) · `/api/license/validate` signature+register-on-first-use (T5) · status/subscription/renewal (T6) · atomic device cap (T7) · admin revoke/release (T8) · ProxyFix (T9) · demo-key removal (T10) · packaging dep (T11). Register call-site migration (T2). Existing-test migration (T3).
- **Deferred (correctly out of A1):** local `/api/license/activate` hardening + device fingerprint derivation (A2); first-run UX, renewal UX, view-only revocation degrade, cloud-save decoupling (A3); admin GUI (D); baking the public key into apps + Dart verification (A2/B).
- **Type/name consistency:** `generate_keypair`, `sign_serial_token`, `verify_serial_token`, `load_private_seed` (serial_generator); `_serial_public_key`, `_verify_serial_token(serial, token) -> (ok, reason, payload)`, `_SERIAL_PUBLIC_KEY_B64`, `_ADMIN_API_TOKEN`, `validate_license`, `license_admin` (dental_clinic). Tables `license_serials(serial,…)`, `license_device_slots(serial, device_fingerprint, is_active)` used consistently in T4–T8.
