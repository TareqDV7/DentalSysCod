# tests/test_branding_api.py
import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db = data_dir / 'dental_clinic.db'
    uploads = data_dir / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', uploads)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def test_branding_requires_login(client):
    assert client.get('/api/branding').status_code == 401


def test_branding_round_trips(client):
    _login(client)
    r = client.put('/api/branding', json={
        'doctor_name': 'Dr. Wasfy Barzaq',
        'doctor_name_ar': 'د. وصفي برزق',
        'default_theme': 'dark_premium',
    })
    assert r.status_code == 200
    body = client.get('/api/branding').get_json()
    assert body['doctor_name'] == 'Dr. Wasfy Barzaq'
    assert body['doctor_name_ar'] == 'د. وصفي برزق'
    assert body['default_theme'] == 'dark_premium'


def test_branding_rejects_unknown_theme(client):
    _login(client)
    r = client.put('/api/branding', json={'default_theme': 'neon_chaos'})
    assert r.status_code == 400


def test_logo_serve_404_when_absent(client):
    _login(client)
    assert client.get('/api/branding/logo').status_code == 404


def test_wizard_done_false_on_fresh_db(client):
    _login(client)
    body = client.get('/api/branding').get_json()
    assert body['wizard_done'] is False


def test_wizard_done_flips_to_true(client):
    _login(client)
    r = client.post('/api/branding/wizard-done')
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    body = client.get('/api/branding').get_json()
    assert body['wizard_done'] is True
