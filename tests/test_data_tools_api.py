# tests/test_data_tools_api.py
"""Route tests for the Settings -> Data Tools surface."""
import io
import sqlite3
import zipfile

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
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def test_export_bundle_requires_login(client):
    assert client.get('/api/data/export-bundle').status_code == 401


def test_export_bundle_returns_zip_with_db(client):
    _login(client)
    resp = client.get('/api/data/export-bundle')
    assert resp.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'dental_clinic.db' in z.namelist()


def _make_source_db(path):
    """A second clinic's DB with one patient, colliding id 1."""
    prev = dental_clinic.DB_NAME
    dental_clinic.DB_NAME = str(path)
    try:
        dental_clinic.init_database()
    finally:
        dental_clinic.DB_NAME = prev
    conn = sqlite3.connect(str(path))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Imported', 'Patient')")
    conn.commit()
    conn.close()


def test_merge_requires_login(client):
    assert client.post('/api/data/merge').status_code == 401


def test_merge_rejects_non_sqlite(client):
    _login(client)
    data = {'file': (io.BytesIO(b'not a database'), 'evil.db')}
    resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 400


def test_merge_adds_imported_patient_and_keeps_existing(client, tmp_path):
    _login(client)
    # Destination already has a patient at id 1.
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Local', 'Owner')")
    conn.commit(); conn.close()

    src = tmp_path / 'other_clinic.db'
    _make_source_db(src)
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'other_clinic.db')}
        resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['report']['total_added'] >= 1
    assert body['backup_path']                      # safety backup was taken

    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    names = {r[0] for r in conn.execute("SELECT first_name FROM patients").fetchall()}
    conn.close()
    assert {'Local', 'Imported'} <= names


def test_merge_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    resp = client.post('/api/data/merge', data={}, content_type='multipart/form-data')
    assert resp.status_code == 404


def test_replace_requires_login(client):
    assert client.post('/api/data/replace').status_code == 401


def test_replace_swaps_database(client, tmp_path):
    _login(client)
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Local', 'Owner')")
    conn.commit(); conn.close()

    src = tmp_path / 'replacement.db'
    _make_source_db(src)   # has 'Imported Patient', no 'Local Owner'
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'replacement.db')}
        resp = client.post('/api/data/replace', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.get_json()['backup_path']

    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    names = {r[0] for r in conn.execute("SELECT first_name FROM patients").fetchall()}
    conn.close()
    assert names == {'Imported'}              # local data replaced, not merged


def test_replace_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    resp = client.post('/api/data/replace', data={}, content_type='multipart/form-data')
    assert resp.status_code == 404


def test_maintenance_guard_blocks_api(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, '_MAINTENANCE', True)
    resp = client.get('/api/patients')
    assert resp.status_code == 503
    assert resp.get_json().get('maintenance') is True


def test_upload_too_large_returns_413(client, monkeypatch):
    """Fix A: MAX_CONTENT_LENGTH is enforced and the handler returns JSON 413."""
    _login(client)
    monkeypatch.setitem(dental_clinic.app.config, 'MAX_CONTENT_LENGTH', 10)
    data = {'file': (io.BytesIO(b'X' * 11), 'big.db')}
    resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 413
    assert 'error' in resp.get_json()


def test_replace_aborts_when_backup_fails(client, monkeypatch, tmp_path):
    """Fix C: replace is aborted with 500 when the safety backup cannot be created."""
    _login(client)
    # Seed the live DB with a known patient.
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Local', 'Owner')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(dental_clinic, 'run_database_backup', lambda: [])

    src = tmp_path / 'replacement.db'
    _make_source_db(src)
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'replacement.db')}
        resp = client.post('/api/data/replace', data=data, content_type='multipart/form-data')

    assert resp.status_code == 500
    body = resp.get_json()
    assert 'backup' in body.get('error', '').lower()

    # The live DB must not have been changed — 'Local Owner' still present, 'Imported' absent.
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    names = {r[0] for r in conn.execute('SELECT first_name FROM patients').fetchall()}
    conn.close()
    assert 'Local' in names
    assert 'Imported' not in names


def test_concurrent_replace_returns_503(client, monkeypatch):
    """Fix D: a second replace while _MAINTENANCE is True returns 503."""
    _login(client)
    monkeypatch.setattr(dental_clinic, '_MAINTENANCE', True)
    data = {'file': (io.BytesIO(b'irrelevant'), 'x.db')}
    resp = client.post('/api/data/replace', data=data, content_type='multipart/form-data')
    assert resp.status_code == 503
    body = resp.get_json()
    assert 'error' in body


def test_clear_catalogs_empties_active_lists_and_tombstones(client):
    _login(client)
    client.post('/api/treatment-procedures', json={'name': 'Cleaning', 'default_price': 200})
    client.post('/api/tooth-conditions', json={'name': 'Decay', 'color': '#ef4444'})

    r = client.post('/api/data/clear-catalogs')
    assert r.status_code == 200
    body = r.get_json()
    assert body['procedures_cleared'] >= 1
    assert body['conditions_cleared'] >= 1

    assert client.get('/api/treatment-procedures').get_json() == []
    assert client.get('/api/tooth-conditions').get_json() == []

    import sqlite3, dental_clinic
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    tp = conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='treatment_procedures'").fetchone()[0]
    tc = conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='tooth_conditions'").fetchone()[0]
    conn.close()
    assert tp >= 1 and tc >= 1


def test_clear_catalogs_blocked_on_cloud_node(client, monkeypatch):
    _login(client)
    import dental_clinic
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert client.post('/api/data/clear-catalogs').status_code == 404
