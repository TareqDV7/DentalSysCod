# tests/test_onboarding_b.py
import sqlite3
import pytest
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
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    val = conn.execute("SELECT value FROM app_settings WHERE key='cloud_url'").fetchone()[0]
    conn.close()
    assert val == dental_clinic._BAKED_CLOUD_BASE_URL.rstrip('/')
