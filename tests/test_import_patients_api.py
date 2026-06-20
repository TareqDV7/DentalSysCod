import io

import openpyxl
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
