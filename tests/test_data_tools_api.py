# tests/test_data_tools_api.py
"""Route tests for the Settings -> Data Tools surface."""
import io
import os
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


def test_export_bundle_file_requires_login(client):
    assert client.post('/api/data/export-bundle-file').status_code == 401


def test_export_bundle_file_writes_zip_to_disk(client):
    # The desktop shell can't trigger a browser download, so the bundle is written
    # to an exports/ folder beside the DB and its path is returned.
    _login(client)
    resp = client.post('/api/data/export-bundle-file')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    path = body['path']
    assert os.path.isfile(path)
    assert os.path.basename(os.path.dirname(path)) == 'exports'
    with zipfile.ZipFile(path) as z:
        assert 'dental_clinic.db' in z.namelist()


def test_export_bundle_file_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert client.post('/api/data/export-bundle-file').status_code == 404


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


def test_merge_surfaces_real_error(client, tmp_path, monkeypatch):
    # A merge failure must report the actual exception — the desktop app has no
    # visible server log, so "see server log" was a dead end for the user.
    _login(client)
    src = tmp_path / 'other_clinic.db'
    _make_source_db(src)

    def boom(*a, **k):
        raise ValueError('kaboom-detail')

    monkeypatch.setattr(dental_clinic.db_merge, 'merge_database', boom)
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'other_clinic.db')}
        resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 500
    assert 'kaboom-detail' in resp.get_json().get('error', '')


def test_merge_isolates_a_failing_dependent_table(client, tmp_path, monkeypatch):
    # One dependent table failing wholesale must not abort the whole additive
    # merge: patients still import and the skip is recorded as a warning.
    _login(client)
    import db_merge
    real_copy = db_merge._copy_table

    def flaky(dst_cur, src_cur, table, fk_cols, remaps, report):
        if table == 'billing':
            raise RuntimeError('boom-billing')
        return real_copy(dst_cur, src_cur, table, fk_cols, remaps, report)

    monkeypatch.setattr(db_merge, '_copy_table', flaky)
    src = tmp_path / 'other_clinic.db'
    _make_source_db(src)
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'other_clinic.db')}
        resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['report']['total_added'] >= 1                       # patient still imported
    assert any('billing' in w for w in body['report']['warnings'])  # skip recorded


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


def test_replace_preserves_device_activation(client, tmp_path):
    """Replacing the clinic's *data* must not de-activate this *workstation*.

    The device identity (serial + token + fingerprint) and cloud pairing live in
    app_settings. The swap overwrites the whole DB, so without preservation the
    incoming DB's blank activation rows would land here and the license gate would
    re-show the activation popup. Regression for that report.
    """
    _login(client)
    # This install is activated + paired to the cloud.
    preserved = {
        'active_serial_number': 'DENTAL-MINE-0001',
        'active_serial_token': 'signed.mine.token',
        'device_fingerprint': 'fp-mine-123',
        'cloud_url': 'https://cloud.example.test',
        'cloud_clinic_token': 'clinic-tok-mine',
        'cloud_clinic_id': '7',
    }
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    for k, v in preserved.items():
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    conn.commit()
    conn.close()

    src = tmp_path / 'replacement.db'
    _make_source_db(src)   # a different clinic's DB; its activation rows are blank
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'replacement.db')}
        resp = client.post('/api/data/replace', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200

    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    names = {r[0] for r in conn.execute('SELECT first_name FROM patients').fetchall()}

    def _get(key):
        row = conn.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    survived = {k: _get(k) for k in preserved}
    conn.close()

    assert names == {'Imported'}        # the data really was replaced...
    assert survived == preserved        # ...but this install's activation + pairing stayed


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


def test_clear_catalogs_is_idempotent_and_reemits_tombstones(client):
    """A second clear (rows already inactive) must NOT be a silent no-op.

    It re-counts the rows and re-stamps their tombstones so a lingering cloud /
    phone copy still gets wiped. Guards the "clicked Clear, nothing happened,
    the cloud copy stayed" trap from legacy demo catalogs.
    """
    _login(client)
    client.post('/api/treatment-procedures', json={'name': 'Cleaning', 'default_price': 200})
    client.post('/api/tooth-conditions', json={'name': 'Decay', 'color': '#ef4444'})

    first = client.post('/api/data/clear-catalogs').get_json()
    assert first['procedures_cleared'] >= 1
    assert first['conditions_cleared'] >= 1

    # Everything is inactive now — the second clear must still act on it.
    second = client.post('/api/data/clear-catalogs').get_json()
    assert second['procedures_cleared'] >= 1
    assert second['conditions_cleared'] >= 1

    assert client.get('/api/treatment-procedures').get_json() == []
    assert client.get('/api/tooth-conditions').get_json() == []


def test_clear_catalogs_blocked_on_cloud_node(client, monkeypatch):
    _login(client)
    import dental_clinic
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert client.post('/api/data/clear-catalogs').status_code == 404


def test_clear_billing_endpoint_removed(client):
    # The bulk "clear billing" action was removed as too dangerous (it wiped
    # every invoice in one click). The route must no longer exist — 404 even
    # for a logged-in staff session.
    _login(client)
    assert client.post('/api/data/clear-billing').status_code == 404
