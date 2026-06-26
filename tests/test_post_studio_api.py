import io
import pytest
from PIL import Image
import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    uploads = data_dir / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(data_dir / 'dental_clinic.db'))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', uploads)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1


def _png(color=(120, 80, 200)):
    b = io.BytesIO()
    Image.new('RGB', (200, 200), color).save(b, 'PNG')
    return b.getvalue()


def _form(n=2):
    data = {'doctor_name': 'Dr. Wasfy', 'theme': 'clean_clinical', 'size': 'square'}
    files = [('photo', (io.BytesIO(_png()), f'p{i}.png')) for i in range(n)]
    labels = [('labels', lbl) for lbl in ['Before', 'After'][:n]]
    return data, files, labels


def test_preview_requires_login(client):
    assert client.post('/api/posts/preview').status_code == 401


def test_preview_returns_png(client):
    _login(client)
    data, files, labels = _form()
    r = client.post(
        '/api/posts/preview',
        data={**data, 'photo': [f[1] for f in files],
              'labels': [lb[1] for lb in labels]},
        content_type='multipart/form-data',
    )
    assert r.status_code == 200
    assert r.content_type.startswith('image/png')
    assert Image.open(io.BytesIO(r.data)).size == (1080, 1080)


def test_preview_rejects_zero_photos(client):
    _login(client)
    r = client.post(
        '/api/posts/preview',
        data={'doctor_name': 'X', 'theme': 'clean_clinical', 'size': 'square'},
        content_type='multipart/form-data',
    )
    assert r.status_code == 400


def test_preview_rejects_more_than_four_photos(client):
    _login(client)
    photos = [(io.BytesIO(_png()), f'p{i}.png') for i in range(5)]
    r = client.post(
        '/api/posts/preview',
        data={'doctor_name': 'X', 'theme': 'clean_clinical', 'size': 'square',
              'photo': photos},
        content_type='multipart/form-data',
    )
    assert r.status_code == 400


def test_preview_rejects_bad_theme_and_size(client):
    _login(client)
    # A fresh BytesIO per request: werkzeug closes the stream after sending,
    # so the two POSTs cannot share one photo object.
    bad_theme = client.post(
        '/api/posts/preview',
        data={'doctor_name': 'X', 'theme': 'neon_chaos', 'size': 'square',
              'photo': [(io.BytesIO(_png()), 'p.png')]},
        content_type='multipart/form-data')
    assert bad_theme.status_code == 400
    bad_size = client.post(
        '/api/posts/preview',
        data={'doctor_name': 'X', 'theme': 'clean_clinical', 'size': 'billboard',
              'photo': [(io.BytesIO(_png()), 'p.png')]},
        content_type='multipart/form-data')
    assert bad_size.status_code == 400


def _save_one(client):
    return client.post('/api/posts',
                       data={'doctor_name': 'Dr. Wasfy', 'theme': 'soft_mint',
                             'size': 'portrait', 'photo': [(io.BytesIO(_png()), 'a.png')],
                             'labels': ['Before']},
                       content_type='multipart/form-data')


def test_save_then_list_serve_delete(client):
    _login(client)
    pid = _save_one(client).get_json()['id']
    listing = client.get('/api/posts').get_json()
    assert any(p['id'] == pid for p in listing)
    img = client.get(f'/api/posts/{pid}/image')
    assert img.status_code == 200 and img.content_type.startswith('image/png')
    assert Image.open(io.BytesIO(img.data)).size == (1080, 1350)
    assert client.delete(f'/api/posts/{pid}').status_code == 200
    assert client.get(f'/api/posts/{pid}/image').status_code == 404


def test_list_requires_login(client):
    assert client.get('/api/posts').status_code == 401
