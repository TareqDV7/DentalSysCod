"""Short-serial online activation (the ~22-char activation code).

Cloud node: `/api/license/claim` hands back a serial's cached signed token + claims
a device slot, and `/api/license/admin/register-serial` lets the vendor pre-load a
serial so a brand-new clinic can activate by short serial alone. Local server:
`/api/license/activate` with just `{serial_number}` fetches the token from the cloud
and then runs the normal signed-token activation, caching it for offline use.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import serial_generator
import dental_clinic


# ── Cloud-node fixture (claim + admin/register-serial live here) ──────────────

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
    monkeypatch.setattr(dental_clinic, '_validate_attempts', {})
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        c.priv_b64 = priv_b64
        yield c
    dental_clinic._set_request_db_path(None)


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


def _claim(client, serial, fp='dev-1', **extra):
    body = {'serial_number': serial, 'device_fingerprint': fp}
    body.update(extra)
    return client.post('/api/license/claim', json=body)


def _admin_register(client, token, admin='secret'):
    return client.post('/api/license/admin/register-serial',
                       headers={'X-Admin-Token': admin}, json={'serial_token': token})


def _set_serial(serial, **cols):
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    sets = ', '.join(f'{k} = ?' for k in cols)
    conn.execute(f'UPDATE license_serials SET {sets} WHERE serial = ?', (*cols.values(), serial))
    conn.commit()
    conn.close()


def _columns(master_path, table):
    conn = sqlite3.connect(master_path)
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]
    conn.close()
    return cols


# ── schema ───────────────────────────────────────────────────────────────────

def test_license_serials_has_token_column(cloud):
    assert 'serial_token' in _columns(dental_clinic.MASTER_DB_PATH, 'license_serials')


# ── claim: gating + basics ───────────────────────────────────────────────────

def test_claim_404_on_local(monkeypatch, tmp_path):
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'x.db'))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        r = c.post('/api/license/claim', json={'serial_number': 'DENTAL-X1', 'device_fingerprint': 'd'})
        assert r.status_code == 404


def test_claim_requires_serial_and_fp(cloud):
    assert cloud.post('/api/license/claim', json={'serial_number': 'DENTAL-NOFP'}).status_code == 400
    assert cloud.post('/api/license/claim', json={'device_fingerprint': 'd'}).status_code == 400


def test_claim_unknown_serial_is_not_found(cloud):
    body = _claim(cloud, 'DENTAL-UNKNOWN-001').get_json()
    assert body['valid'] is False and body['reason'] == 'not_found'


def test_claim_after_validate_returns_token(cloud):
    tok = _sign(cloud, 'DENTAL-CLM-0001')
    cloud.post('/api/license/validate', json={'serial_token': tok, 'device_fingerprint': 'val-dev'})
    body = _claim(cloud, 'DENTAL-CLM-0001').get_json()
    assert body['valid'] is True
    assert body['serial_token'] == tok
    assert body['status'] == 'active'
    assert body['plan_name'] == 'standard'


def test_claim_no_token_when_serial_known_but_tokenless(cloud):
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    conn.execute("INSERT INTO license_serials (serial, status, max_devices) VALUES ('DENTAL-LEGACY-01','active',3)")
    conn.commit()
    conn.close()
    body = _claim(cloud, 'DENTAL-LEGACY-01').get_json()
    assert body['valid'] is False and body['reason'] == 'no_token'


# ── admin register-serial: vendor pre-load ───────────────────────────────────

def test_admin_register_requires_token(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    tok = _sign(cloud, 'DENTAL-ADM-PRE1')
    assert cloud.post('/api/license/admin/register-serial', json={'serial_token': tok}).status_code == 401


def test_admin_register_then_claimable(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    tok = _sign(cloud, 'DENTAL-ADM-PRE2')
    r = _admin_register(cloud, tok)
    assert r.status_code == 200 and r.get_json()['already_existed'] is False
    body = _claim(cloud, 'DENTAL-ADM-PRE2').get_json()
    assert body['valid'] is True and body['serial_token'] == tok


def test_admin_register_idempotent(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    tok = _sign(cloud, 'DENTAL-ADM-PRE3')
    _admin_register(cloud, tok)
    assert _admin_register(cloud, tok).get_json()['already_existed'] is True


def test_admin_register_rejects_garbage(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    r = cloud.post('/api/license/admin/register-serial',
                   headers={'X-Admin-Token': 'secret'}, json={'serial_token': 'junk'})
    assert r.status_code == 400


def test_admin_register_404_on_local(monkeypatch, tmp_path):
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'x.db'))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        assert c.post('/api/license/admin/register-serial', json={'serial_token': 't'}).status_code == 404


# ── claim: status + device-cap gates ─────────────────────────────────────────

def test_claim_blocks_revoked(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    _admin_register(cloud, _sign(cloud, 'DENTAL-CLM-REV'))
    _set_serial('DENTAL-CLM-REV', status='revoked')
    body = _claim(cloud, 'DENTAL-CLM-REV').get_json()
    assert body['valid'] is False and body['reason'] == 'revoked'


def test_claim_enforces_device_cap(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    _admin_register(cloud, _sign(cloud, 'DENTAL-CLM-CAP', max_devices=2))
    assert _claim(cloud, 'DENTAL-CLM-CAP', fp='d1').get_json()['valid'] is True
    assert _claim(cloud, 'DENTAL-CLM-CAP', fp='d2').get_json()['valid'] is True
    body = _claim(cloud, 'DENTAL-CLM-CAP', fp='d3').get_json()
    assert body['valid'] is False and body['reason'] == 'device_cap_reached'
    # an already-claimed device re-claims its own slot idempotently
    assert _claim(cloud, 'DENTAL-CLM-CAP', fp='d1').get_json()['valid'] is True


def test_claim_expired_past_grace(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    _admin_register(cloud, _sign(cloud, 'DENTAL-CLM-EXP', expiry_days=-60))
    body = _claim(cloud, 'DENTAL-CLM-EXP').get_json()
    assert body['valid'] is False and body['reason'] == 'expired'


# ── register pre-loads token (an existing paired clinic becomes claimable) ────

def test_register_preloads_token_for_claim(cloud):
    tok = _sign(cloud, 'DENTAL-REG-PRE1', clinic_name='Reg Clinic')
    r = cloud.post('/api/clinics/register', json={
        'serial_number': 'DENTAL-REG-PRE1', 'clinic_name': 'Reg Clinic', 'offline_token': tok})
    assert r.status_code == 200
    body = _claim(cloud, 'DENTAL-REG-PRE1').get_json()
    assert body['valid'] is True and body['serial_token'] == tok


# ── Local server: activate by short serial (online) ──────────────────────────

@pytest.fixture()
def local(tmp_path, monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    # Cloud validate is 'offline' by default so _activate_primary uses the local
    # offline-window check; tests that need the claim leg override _claim_with_cloud.
    monkeypatch.setattr(dental_clinic, '_validate_with_cloud', lambda *a, **k: None)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        c.priv_b64 = priv_b64
        yield c


def _active_settings():
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    rows = dict(conn.execute(
        "SELECT key, value FROM app_settings WHERE key IN "
        "('active_serial_number','active_serial_token')").fetchall())
    conn.close()
    return rows


def test_activate_by_serial_uses_cloud_token(local, monkeypatch):
    tok = _sign(local, 'DENTAL-ACT-SER1')
    monkeypatch.setattr(
        dental_clinic, '_claim_with_cloud',
        lambda serial, fp, dn='': {'valid': True, 'serial_token': tok, 'status': 'active',
                                   'plan_name': 'standard', 'max_devices': 3})
    r = local.post('/api/license/activate', json={'serial_number': 'DENTAL-ACT-SER1'})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    s = _active_settings()
    assert s['active_serial_number'] == 'DENTAL-ACT-SER1'
    assert s['active_serial_token'] == tok


def test_activate_by_serial_cloud_unreachable_falls_back(local, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_claim_with_cloud', lambda *a, **k: None)
    r = local.post('/api/license/activate', json={'serial_number': 'DENTAL-ACT-SER2'})
    assert r.status_code == 503
    assert r.get_json()['reason'] == 'cloud_unreachable'


def test_activate_by_serial_rejected_reason_passthrough(local, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_claim_with_cloud',
                        lambda *a, **k: {'valid': False, 'reason': 'device_cap_reached'})
    r = local.post('/api/license/activate', json={'serial_number': 'DENTAL-ACT-SER3'})
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'device_cap_reached'


def test_activate_full_token_still_works(local):
    # Air-gapped fallback unchanged: pasting the full signed token still activates.
    r = local.post('/api/license/activate', json={'serial_token': _sign(local, 'DENTAL-ACT-FULL')})
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_activate_lan_attach_still_routes(local):
    # serial_number + device_id → LAN-attach path, not online-claim. Not activated
    # on the server yet → 403 not_activated (unchanged behaviour).
    r = local.post('/api/license/activate', json={'serial_number': 'DENTAL-LAN-1', 'device_id': 'dev-x'})
    assert r.status_code == 403
    assert r.get_json().get('reason') == 'not_activated'


def test_activate_short_serial_too_short(local):
    assert local.post('/api/license/activate', json={'serial_number': 'SHORT'}).status_code == 400
