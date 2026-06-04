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


# ── Task 1: signature gate ──────────────────────────────────────────────────

def test_activate_rejects_unsigned_token(local):
    r = _activate(local, 'not-a-real-token')
    assert r.status_code == 403
    assert r.get_json()['reason'] in ('malformed', 'bad_signature')


def test_activate_accepts_signed_token(local):
    r = _activate(local, _sign(local, 'DENTAL-A2-0001'))
    assert r.status_code == 200
    assert r.get_json()['success'] is True


# ── Task 2: baked public key ────────────────────────────────────────────────

def test_baked_public_key_is_present():
    assert dental_clinic._SERIAL_PUBLIC_KEY_B64, 'no serial public key baked or configured'


@pytest.mark.xfail(reason='real vendor public key not yet baked', strict=False)
def test_baked_public_key_is_real():
    assert dental_clinic._BAKED_SERIAL_PUBLIC_KEY != 'REPLACE_WITH_REAL_VENDOR_PUBLIC_KEY_BASE64'


# ── Task 3: token-sourced fields ────────────────────────────────────────────

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


# ── Task 4: grace-date bypass fix ───────────────────────────────────────────

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


# ── Task 5: cloud authoritative + offline fallback ──────────────────────────

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


# ── Task 6: LAN-attach path ─────────────────────────────────────────────────

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


# ── Task 7: device-membership gate on /api/license/login ───────────────────

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


# ── Task 8: device-membership gate on /api/license/status ──────────────────

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
