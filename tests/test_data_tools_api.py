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
