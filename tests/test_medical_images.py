"""Medical-image upload + byte download — ``/api/medical-images`` and
``/api/medical-images/<id>/file``.

The mobile app syncs X-rays/photos through the local server: it POSTs the
file (multipart), needs the new row id back to reconcile, and downloads the
raw bytes of images other devices uploaded. This suite locks the id return
and the byte-download endpoint.
"""

import io
import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    # Keep uploaded files inside the test's tmp dir so nothing leaks.
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', tmp_path / 'uploads')
    (tmp_path / 'uploads').mkdir(parents=True, exist_ok=True)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(first='Img', last='Pat', phone='0500'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (first, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _upload(client, pid, content=b'\x89PNG\r\n\x1a\nFAKE', name='xray.png', notes='molar'):
    return client.post(
        '/api/medical-images',
        data={
            'patient_id': str(pid),
            'notes': notes,
            'image': (io.BytesIO(content), name),
        },
        content_type='multipart/form-data',
    )


def test_upload_returns_new_id(client):
    pid = _patient()
    r = _upload(client, pid)
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert isinstance(body['id'], int) and body['id'] > 0


def test_upload_appears_in_listing(client):
    pid = _patient()
    new_id = _upload(client, pid).get_json()['id']
    listing = client.get(f'/api/medical-images?patient_id={pid}').get_json()
    assert any(row['id'] == new_id for row in listing)
    row = next(r for r in listing if r['id'] == new_id)
    assert row['file_name'] == 'xray.png'
    assert row['notes'] == 'molar'


def test_download_returns_the_bytes(client):
    pid = _patient()
    payload = b'\x89PNG\r\n\x1a\nHELLO-XRAY'
    new_id = _upload(client, pid, content=payload).get_json()['id']
    r = client.get(f'/api/medical-images/{new_id}/file')
    assert r.status_code == 200
    assert r.data == payload


def test_download_unknown_id_is_404(client):
    assert client.get('/api/medical-images/99999/file').status_code == 404
