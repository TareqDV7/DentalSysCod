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
