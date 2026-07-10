# tests/test_onboarding_b.py
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone
import dental_clinic


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.delenv('CLINIC_LICENSE_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_CLOUD_URL', raising=False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def test_license_cloud_url_falls_back_to_baked(local):
    assert dental_clinic._license_cloud_url() == dental_clinic._BAKED_CLOUD_BASE_URL.rstrip('/')


def test_env_overrides_baked(local, monkeypatch):
    monkeypatch.setenv('CLINIC_LICENSE_CLOUD_URL', 'https://staging.example.test/')
    assert dental_clinic._license_cloud_url() == 'https://staging.example.test'


def test_pair_uses_baked_url_when_omitted(local, monkeypatch):
    calls = {}
    def fake_http(method, url, headers=None, body=None, timeout=15):
        calls['url'] = url
        return 200, {'clinic_token': 'tok-123', 'clinic_id': 7}
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True})
    r = local.post('/api/cloud/pair', json={'serial_number': 'DENTAL-B-LINK1'})
    assert r.status_code == 200
    assert calls['url'].startswith(dental_clinic._BAKED_CLOUD_BASE_URL)
    # And it persisted the baked URL as the clinic's cloud_url.
    conn = dental_clinic.get_db_connection()
    val = conn.execute("SELECT value FROM app_settings WHERE key='cloud_url'").fetchone()[0]
    conn.close()
    assert val == dental_clinic._BAKED_CLOUD_BASE_URL.rstrip('/')


def _seed_active_license(serial='DENTAL-B-ONB'):
    today = datetime.now(timezone.utc).date()
    conn = dental_clinic.get_db_connection()
    conn.execute('''INSERT INTO licenses (serial_number, clinic_name, plan_name, status,
                    max_devices, expires_at, grace_until) VALUES (?,?,?,?,?,?,?)''',
                 (serial, 'C', 'standard', 'active', 3,
                  (today + timedelta(days=365)).strftime('%Y-%m-%d'),
                  (today + timedelta(days=379)).strftime('%Y-%m-%d')))
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('active_serial_number', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (serial,))
    conn.commit(); conn.close()


def _set_setting(key, value):
    conn = dental_clinic.get_db_connection()
    conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def test_onboarding_fresh_install(local):
    b = local.get('/api/onboarding/state').get_json()
    assert b['licensed_state'] == 'unlicensed'
    assert b['cloud_linked'] is False
    assert b['needs_onboarding'] is True


def test_onboarding_licensed_unlinked_needs_onboarding(local):
    _seed_active_license()
    b = local.get('/api/onboarding/state').get_json()
    assert b['licensed_state'] == 'active'
    assert b['cloud_linked'] is False
    assert b['needs_onboarding'] is True


def test_onboarding_linked(local):
    _seed_active_license()
    _set_setting('cloud_url', 'https://cloud.example.test')
    _set_setting('cloud_clinic_token', 'tok')
    b = local.get('/api/onboarding/state').get_json()
    assert b['cloud_linked'] is True
    assert b['needs_onboarding'] is False


def test_onboarding_dismissed(local):
    _seed_active_license()
    _set_setting('cloud_link_dismissed', '1')
    b = local.get('/api/onboarding/state').get_json()
    assert b['needs_onboarding'] is False   # licensed + dismissed → done
