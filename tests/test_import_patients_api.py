import io

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db = data_dir / 'dental_clinic.db'
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def _csv_upload(text, name='patients.csv'):
    return {'file': (io.BytesIO(text.encode('utf-8')), name)}


def test_preview_requires_login(client):
    assert client.post('/api/data/import-patients/preview').status_code == 401


def test_preview_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    r = client.post('/api/data/import-patients/preview',
                    data=_csv_upload('First Name,Last Name\nAli,Hassan\n'),
                    content_type='multipart/form-data')
    assert r.status_code == 404


def test_preview_returns_mapping_and_counts(client):
    _login(client)
    csv_text = ('First Name,Last Name,Mobile,DOB\n'
                'Ali,Hassan,0501,04/03/2020\n'
                ',Saleh,0502,\n')                      # missing first name -> problem
    r = client.post('/api/data/import-patients/preview',
                    data=_csv_upload(csv_text), content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_json()
    assert body['suggested_mapping']['first_name'] == 'First Name'
    assert body['suggested_mapping']['phone'] == 'Mobile'
    assert body['counts']['valid'] == 1
    assert body['counts']['problems'] == 1
    assert body['rows_total'] == 2


def _commit(client, csv_text, **form):
    data = {'file': (io.BytesIO(csv_text.encode('utf-8')), 'patients.csv'),
            'date_format': form.get('date_format', 'DD/MM/YYYY')}
    if 'mapping' in form:
        data['mapping'] = form['mapping']
    if 'import_duplicates' in form:
        data['import_duplicates'] = form['import_duplicates']
    return client.post('/api/data/import-patients/commit', data=data,
                       content_type='multipart/form-data')


def test_commit_requires_login(client):
    assert client.post('/api/data/import-patients/commit').status_code == 401


def test_commit_imports_valid_skips_problems(client):
    _login(client)
    csv_text = ('First Name,Last Name,Mobile,DOB\n'
                'Ali,Hassan,0501,04/03/2020\n'
                ',Saleh,0502,\n')
    r = _commit(client, csv_text)
    assert r.status_code == 200
    body = r.get_json()
    assert body['imported'] == 1
    assert body['skipped'] == 1
    # The imported patient is now visible.
    listing = client.get('/api/patients').get_json()
    assert any(p['last_name'] == 'Hassan' for p in listing)
    assert all(p['last_name'] != 'Saleh' for p in listing)


def test_commit_skips_duplicates_by_default_then_imports_when_opted_in(client):
    _login(client)
    csv_text = 'First Name,Last Name,Mobile\nAli,Hassan,0501\nAli,Hassan,0501\n'
    body = _commit(client, csv_text).get_json()
    assert body['imported'] == 1 and body['skipped'] == 1
    # Opt in: the in-file duplicate now imports too (and both collide with the
    # one already stored, so 2 more come in).
    body2 = _commit(client, csv_text, import_duplicates='true').get_json()
    assert body2['imported'] == 2


def test_commit_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert _commit(client, 'First Name,Last Name\nAli,Hassan\n').status_code == 404


def test_commit_writes_audit_log(client):
    _login(client)
    _commit(client, 'First Name,Last Name\nAli,Hassan\n')
    import sqlite3
    conn = dental_clinic.get_db_connection()
    n = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action_type='import'").fetchone()[0]
    conn.close()
    assert n == 1


def test_preview_rejects_oversized_file(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, '_IMPORT_MAX_BYTES', 5)
    r = client.post('/api/data/import-patients/preview',
                    data=_csv_upload('First Name,Last Name\nAli,Hassan\n'),
                    content_type='multipart/form-data')
    assert r.status_code == 400


def test_commit_rejects_bad_mapping_json(client):
    _login(client)
    data = {'file': (io.BytesIO(b'First Name,Last Name\nAli,Hassan\n'), 'p.csv'),
            'date_format': 'DD/MM/YYYY', 'mapping': '{not valid json'}
    r = client.post('/api/data/import-patients/commit', data=data,
                    content_type='multipart/form-data')
    assert r.status_code == 400
