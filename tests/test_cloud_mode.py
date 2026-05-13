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
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()  # builds the master DB
    with dental_clinic.app.test_client() as c:
        yield c
    dental_clinic._set_request_db_path(None)


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
