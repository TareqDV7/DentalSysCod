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


def _seed_license(serial, status='active', days=365, grace_extra=14, token=None):
    today = datetime.now(timezone.utc).date()
    expires = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    grace = (today + timedelta(days=days + grace_extra)).strftime('%Y-%m-%d')
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute('''INSERT INTO licenses (serial_number, clinic_name, plan_name, status,
                    max_devices, expires_at, grace_until) VALUES (?,?,?,?,?,?,?)''',
                 (serial, 'C', 'standard', status, 3, expires, grace))
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('active_serial_number', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (serial,))
    if token is not None:
        conn.execute("INSERT INTO app_settings (key, value) VALUES ('active_serial_token', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (token,))
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


def test_gate_endpoint_reports_unlicensed(local):
    body = local.get('/api/license/gate').get_json()
    assert body['state'] == 'unlicensed' and body['licensed'] is False


def test_gate_endpoint_reports_active(local):
    _seed_license('DENTAL-A3-GATE', days=365)
    body = local.get('/api/license/gate').get_json()
    assert body['state'] == 'active'
    assert body['serial_number'] == 'DENTAL-A3-GATE'


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
    r = local.post('/api/patients', json={'first_name': 'Jane', 'last_name': 'Active', 'phone': '0590000000'})
    assert r.status_code in (200, 201)


def test_write_guard_fails_open_on_error(local, monkeypatch):
    _seed_license('DENTAL-A3-FO', days=-60)
    _login(local)
    def boom(_cur):
        raise RuntimeError('gate exploded')
    monkeypatch.setattr(dental_clinic, '_license_gate_state', boom)
    r = local.post('/api/patients', json={'first_name': 'FailOpen', 'last_name': 'Test', 'phone': '0590000001'})
    assert r.status_code in (200, 201)   # a licensing bug must never brick data entry


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


def _license_status_value(serial):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    row = conn.execute('SELECT status FROM licenses WHERE serial_number=?', (serial.upper(),)).fetchone()
    conn.close()
    return row[0] if row else None


def test_recheck_applies_cloud_revocation(local, monkeypatch):
    # token must be non-empty so the empty-token guard does not skip the cloud call
    _seed_license('DENTAL-A3-RC', status='active', days=365, token='test-token-sentinel')
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
