"""Multi-tenant cloud-mode tests (Phase 1 of the cloud sync work).

In cloud mode one process serves many clinics: a master registry DB plus one
SQLite file per clinic. Every /api/* request must carry a clinic token; a
before_request hook resolves it and points DB_NAME at that clinic's file, so the
existing handlers run unchanged but see only that tenant's data.
"""

import os

import pytest

import dental_clinic


@pytest.fixture()
def cloud(tmp_path, monkeypatch):
    data_dir = tmp_path / 'clouddata'
    data_dir.mkdir()
    master = str(data_dir / 'cloud_master.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', master)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', dental_clinic._DbPathProxy(master))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', data_dir / 'uploads')
    (data_dir / 'uploads').mkdir(exist_ok=True)
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', False)
    dental_clinic._set_request_db_path(None)
    dental_clinic._register_attempts.clear()  # rate-limit state must not leak between tests
    dental_clinic.init_database()  # builds the master DB
    with dental_clinic.app.test_client() as c:
        yield c
    dental_clinic._set_request_db_path(None)
    dental_clinic._register_attempts.clear()


@pytest.fixture()
def plain(tmp_path, monkeypatch):
    """A normal (non-cloud) server, to confirm cloud-only endpoints stay off."""
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'clinic.db'))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _register(client, serial, name='Test Clinic'):
    r = client.post('/api/clinics/register', json={'serial_number': serial, 'clinic_name': name})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _h(token):
    return {'X-Clinic-Token': token}


def test_cloud_master_has_no_admin_user(cloud, monkeypatch):
    # On a cloud node the staff portal is never reachable, so init_database()
    # must not seed an admin login row — otherwise the master ends up holding a
    # stale credential (the docker-compose used to set "change-me-please" here).
    import sqlite3
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    conn.close()
    assert row[0] == 0, 'cloud master DB should have no seeded admin'


def test_register_creates_clinic_and_db(cloud):
    body = _register(cloud, 'SERIAL-AAAA-0001', 'Bright Smiles')
    assert body['already_registered'] is False
    assert body['clinic_name'] == 'Bright Smiles'
    assert body['clinic_token']
    assert isinstance(body['clinic_id'], int)
    assert os.path.exists(dental_clinic._clinic_db_path(body['clinic_id']))


def test_register_is_idempotent_per_serial(cloud):
    first = _register(cloud, 'SERIAL-AAAA-0002')
    again = cloud.post('/api/clinics/register', json={'serial_number': 'SERIAL-AAAA-0002', 'clinic_name': 'Whatever'})
    assert again.status_code == 200
    body = again.get_json()
    assert body['already_registered'] is True
    assert body['clinic_token'] == first['clinic_token']
    assert body['clinic_id'] == first['clinic_id']


def test_register_validates_input(cloud):
    assert cloud.post('/api/clinics/register', json={'serial_number': 'short', 'clinic_name': 'X'}).status_code == 400
    assert cloud.post('/api/clinics/register', json={'serial_number': 'LONGENOUGH123', 'clinic_name': ''}).status_code == 400


def test_api_requires_clinic_token(cloud):
    assert cloud.get('/api/patients').status_code == 401            # no token
    assert cloud.get('/api/patients', headers=_h('bogus')).status_code == 401  # bad token
    token = _register(cloud, 'SERIAL-AAAA-0003')['clinic_token']
    ok = cloud.get('/api/patients', headers=_h(token))
    assert ok.status_code == 200
    assert ok.get_json() == []


def test_tenant_isolation(cloud):
    a = _register(cloud, 'SERIAL-AAAA-000A', 'Clinic A')['clinic_token']
    b = _register(cloud, 'SERIAL-AAAA-000B', 'Clinic B')['clinic_token']

    created = cloud.post('/api/patients', headers=_h(a), json={'first_name': 'Alice', 'last_name': 'A', 'phone': '111'})
    assert created.status_code == 200

    seen_by_a = cloud.get('/api/patients', headers=_h(a)).get_json()
    seen_by_b = cloud.get('/api/patients', headers=_h(b)).get_json()
    assert any(p.get('first_name') == 'Alice' for p in seen_by_a)
    assert seen_by_b == []  # B must not see A's patient


def test_clinic_token_via_query_param(cloud):
    token = _register(cloud, 'SERIAL-AAAA-0004')['clinic_token']
    assert cloud.get(f'/api/patients?clinic_token={token}').status_code == 200


def test_portal_paths_show_info_on_cloud(cloud):
    r = cloud.get('/')
    assert r.status_code == 200
    assert b'cloud sync node' in r.data.lower()


def test_medical_images_blocked_on_cloud(cloud):
    token = _register(cloud, 'SERIAL-AAAA-0005')['clinic_token']
    r = cloud.get('/api/medical-images', headers=_h(token))
    assert r.status_code == 501


def test_register_disabled_when_not_cloud_mode(plain):
    r = plain.post('/api/clinics/register', json={'serial_number': 'SERIAL-AAAA-0006', 'clinic_name': 'X'})
    assert r.status_code == 404


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


def test_register_accepts_valid_signed_token(cloud, monkeypatch):
    priv = _make_keypair_and_patch(monkeypatch)
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', True)

    serial = 'SIGNED-AAAA-0001'
    token = _sign_serial(serial, priv)
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': serial, 'clinic_name': 'OK', 'offline_token': token})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_register_rejects_unsigned_when_required(cloud, monkeypatch):
    _make_keypair_and_patch(monkeypatch)
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', True)

    r = cloud.post('/api/clinics/register',
                   json={'serial_number': 'NO-TOKEN-AAA', 'clinic_name': 'X'})
    assert r.status_code == 403, r.get_data(as_text=True)
    assert 'required' in r.get_json()['error']


def test_register_rejects_tampered_token(cloud, monkeypatch):
    import serial_generator
    _make_keypair_and_patch(monkeypatch)
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', True)

    serial = 'TAMPER-AAAA-001'
    # Token signed with a DIFFERENT keypair (not the one patched into the verifier)
    priv2, _pub2 = serial_generator.generate_keypair()
    bad_token = _sign_serial(serial, priv2)
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': serial, 'clinic_name': 'X', 'offline_token': bad_token})
    assert r.status_code == 403
    assert 'signature' in r.get_json()['error']


def test_register_rejects_serial_mismatch(cloud, monkeypatch):
    priv = _make_keypair_and_patch(monkeypatch)
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', True)

    # Token signed for serial A — but registration uses serial B
    token = _sign_serial('REAL-SERIAL-001', priv)
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': 'OTHER-SERIAL-001', 'clinic_name': 'X',
                         'offline_token': token})
    assert r.status_code == 403
    assert 'match' in r.get_json()['error']


def test_register_unsigned_still_works_when_not_required(cloud, monkeypatch):
    # Default behaviour: signing isn't required, no key configured → legacy demo
    # serials still register. (This guards the rollout path.)
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', '')
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', False)
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': 'LEGACY-DEMO-001', 'clinic_name': 'X'})
    assert r.status_code == 200


# --- _verify_serial_token unit tests -----------------------------------------
# These exercise the gate's primitive directly (no HTTP), covering the cases the
# register handler depends on: valid, bad signature, wrong serial, expired grace,
# and malformed input. They also confirm a token straight out of
# serial_generator.py validates against the cloud's verifier.

def test_verify_serial_token_valid(monkeypatch):
    priv = _make_keypair_and_patch(monkeypatch)
    serial = 'VERIFY-OK-0001'
    token = _sign_serial(serial, priv)
    ok, reason, _payload = dental_clinic._verify_serial_token(serial, token)
    assert ok is True, reason
    assert reason == ''


def test_verify_serial_token_from_serial_generator(monkeypatch):
    # A token produced by serial_generator.sign_serial_token must validate
    # against the cloud gate (Ed25519, base64url wire format).
    import serial_generator
    from datetime import datetime, timedelta, timezone
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    serial = 'DENTAL-SMD-ABCDE-00001'
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {
        'v': 2, 'serial': serial, 'clinic_name': 'Smile', 'max_devices': 1,
        'issued_at': now.isoformat() + 'Z',
        'expires_at': (now + timedelta(days=365)).isoformat() + 'Z',
        'grace_until': (now + timedelta(days=395)).isoformat() + 'Z',
    }
    token = serial_generator.sign_serial_token(payload, priv_b64)
    ok, reason, _payload = dental_clinic._verify_serial_token(serial, token)
    assert ok is True, reason


def test_verify_serial_token_bad_signature(monkeypatch):
    import serial_generator
    _make_keypair_and_patch(monkeypatch)  # patch the good public key; we then sign with a different key
    # Sign with a different (unpatched) private key
    priv_other, _pub_other = serial_generator.generate_keypair()
    serial = 'VERIFY-BAD-SIG'
    token = _sign_serial(serial, priv_other)  # signed with a different key
    ok, reason, _payload = dental_clinic._verify_serial_token(serial, token)
    assert ok is False
    assert 'signature' in reason


def test_verify_serial_token_wrong_serial(monkeypatch):
    priv = _make_keypair_and_patch(monkeypatch)
    token = _sign_serial('TOKEN-SERIAL-A', priv)
    ok, reason, _payload = dental_clinic._verify_serial_token('OTHER-SERIAL-B', token)
    assert ok is False
    assert 'match' in reason


def test_verify_serial_token_expired_grace(monkeypatch):
    priv = _make_keypair_and_patch(monkeypatch)
    serial = 'VERIFY-EXPIRED'
    # expiry_days = -60 → grace_until (expiry + 30 days) is 30 days in the past.
    token = _sign_serial(serial, priv, expiry_days=-60)
    ok, reason, _payload = dental_clinic._verify_serial_token(serial, token)
    assert ok is False
    assert 'expired' in reason


def test_verify_serial_token_malformed(monkeypatch):
    _make_keypair_and_patch(monkeypatch)
    # empty
    assert dental_clinic._verify_serial_token('S', '')[0] is False
    # no dot separator
    ok, reason, _p = dental_clinic._verify_serial_token('S', 'notatoken')
    assert ok is False and 'malformed' in reason
    # non-base64 garbage on both sides of the dot
    ok, reason, _p = dental_clinic._verify_serial_token('S', '!!!.@@@')
    assert ok is False
    # valid base64url but payload isn't JSON
    import base64
    junk = base64.urlsafe_b64encode(b'not json').decode().rstrip('=')
    sig = base64.urlsafe_b64encode(b'whatever').decode().rstrip('=')
    ok, reason, _p = dental_clinic._verify_serial_token('S', f'{junk}.{sig}')
    assert ok is False  # signature fails before JSON parse, but either way not ok


def test_register_500_when_required_but_no_key(cloud, monkeypatch):
    # Misconfiguration guard: enforcement requested but no signing key set must
    # fail closed with 500, never silently allow an unsigned registration.
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', '')
    monkeypatch.setattr(dental_clinic, '_REQUIRE_SIGNED_SERIAL', True)
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': 'NOKEY-SERIAL-1', 'clinic_name': 'X'})
    assert r.status_code == 500, r.get_data(as_text=True)
    assert 'signing key' in r.get_json()['error'].lower()


def test_cloud_pair_forwards_offline_token_from_body(tmp_path, monkeypatch):
    # Local-server side: /api/cloud/pair must forward an offline_token supplied in
    # the request body to the cloud's register call, so the HMAC gate accepts it.
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'clinic.db'))
    monkeypatch.setitem(dental_clinic.CLINIC_CONFIG, 'CLINIC_NAME', 'Paired Clinic')
    dental_clinic.init_database()

    captured = {}

    def fake_http(method, url, headers=None, body=None, timeout=15):
        captured['url'] = url
        captured['body'] = body
        return 200, {'clinic_token': 'tok-123', 'clinic_id': 7, 'already_registered': False}

    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True})

    with dental_clinic.app.test_client() as c:
        r = c.post('/api/cloud/pair', json={
            'cloud_url': 'https://cloud.example',
            'serial_number': 'PAIR-SERIAL-001',
            'offline_token': 'PAYLOAD.SIG',
        })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert captured['body']['offline_token'] == 'PAYLOAD.SIG'
    assert captured['body']['serial_number'] == 'PAIR-SERIAL-001'

    # And it persisted the token for future re-pairs.
    import sqlite3
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    assert dental_clinic.read_app_setting(cur, 'cloud_offline_token', '') == 'PAYLOAD.SIG'
    conn.close()


def test_cloud_pair_omits_offline_token_when_none(tmp_path, monkeypatch):
    # Default path (no token anywhere): the register body must NOT carry an
    # offline_token key, so the cloud's unsigned-allowed path is exercised.
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'clinic2.db'))
    monkeypatch.setitem(dental_clinic.CLINIC_CONFIG, 'CLINIC_NAME', 'Plain Clinic')
    monkeypatch.delenv('CLINIC_OFFLINE_TOKEN', raising=False)
    dental_clinic.init_database()

    captured = {}

    def fake_http(method, url, headers=None, body=None, timeout=15):
        captured['body'] = body
        return 200, {'clinic_token': 'tok-456', 'clinic_id': 8, 'already_registered': False}

    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True})

    with dental_clinic.app.test_client() as c:
        r = c.post('/api/cloud/pair', json={
            'cloud_url': 'https://cloud.example',
            'serial_number': 'PAIR-SERIAL-002',
        })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert 'offline_token' not in captured['body']


def test_cloud_pair_uses_env_offline_token(tmp_path, monkeypatch):
    # Fallback source: env CLINIC_OFFLINE_TOKEN when nothing in body/app_settings.
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'clinic3.db'))
    monkeypatch.setitem(dental_clinic.CLINIC_CONFIG, 'CLINIC_NAME', 'Env Clinic')
    monkeypatch.setenv('CLINIC_OFFLINE_TOKEN', 'ENVPAYLOAD.ENVSIG')
    dental_clinic.init_database()

    captured = {}

    def fake_http(method, url, headers=None, body=None, timeout=15):
        captured['body'] = body
        return 200, {'clinic_token': 'tok-789', 'clinic_id': 9, 'already_registered': False}

    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True})

    with dental_clinic.app.test_client() as c:
        r = c.post('/api/cloud/pair', json={
            'cloud_url': 'https://cloud.example',
            'serial_number': 'PAIR-SERIAL-003',
        })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert captured['body']['offline_token'] == 'ENVPAYLOAD.ENVSIG'


def test_register_rate_limit(cloud, monkeypatch):
    # Tight limit so the test runs quickly. Up to N from the same IP succeed,
    # then the next ones are 429 until the window expires.
    monkeypatch.setattr(dental_clinic, '_REGISTER_RATE_LIMIT', 3)
    monkeypatch.setattr(dental_clinic, '_REGISTER_RATE_WINDOW', 60)
    dental_clinic._register_attempts.clear()

    # 3 distinct serials succeed:
    for i in range(3):
        r = cloud.post('/api/clinics/register',
                       json={'serial_number': f'RL-SERIAL-{i:04d}', 'clinic_name': 'X'})
        assert r.status_code == 200, (i, r.get_data(as_text=True))

    # 4th attempt from the same client is rate-limited regardless of serial:
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': 'RL-SERIAL-9999', 'clinic_name': 'X'})
    assert r.status_code == 429
    body = r.get_json()
    assert 'Too many' in body['error']

    # Idempotent hits on an existing serial also count toward the limit
    # (only the response not being 429 matters here — we already past the cap).
    r = cloud.post('/api/clinics/register',
                   json={'serial_number': 'RL-SERIAL-0001', 'clinic_name': 'X'})
    assert r.status_code == 429

    dental_clinic._register_attempts.clear()
