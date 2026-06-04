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
