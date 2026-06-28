import io
import sqlite3 as _sqlite3
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


def test_readonly_posts_reachable_without_login(client):
    # The offline-first mobile app reads posts over the LAN with device/clinic
    # token headers, not the portal session cookie — same open posture as
    # /api/patients and /api/medical-images. The listing and image-serve GETs
    # must pass the portal gate without a session.
    listing = client.get('/api/posts')
    assert listing.status_code == 200
    assert listing.get_json() == []
    # A missing image returns 404 (handler ran), proving the gate let it through
    # rather than short-circuiting with a 401.
    assert client.get('/api/posts/999/image').status_code == 404


def test_post_writes_still_require_login(client):
    # Reads are open, but creates and deletes stay gated behind the portal session.
    assert client.post('/api/posts').status_code == 401
    assert client.delete('/api/posts/1').status_code == 401


def test_save_render_failure_rolls_back(client, monkeypatch):
    _login(client)

    def _boom(spec):
        raise RuntimeError('render exploded')

    monkeypatch.setattr(dental_clinic.post_studio, 'render_post', _boom)
    r = client.post(
        '/api/posts',
        data={'doctor_name': 'X', 'theme': 'clean_clinical', 'size': 'square',
              'photo': [(io.BytesIO(_png()), 'a.png')], 'labels': ['Before']},
        content_type='multipart/form-data')
    assert r.status_code == 500
    # rollback must discard the INSERTed row, so the gallery stays empty.
    assert client.get('/api/posts').get_json() == []


def test_branding_logo_endpoints_are_gone(client):
    _login(client)
    assert client.post('/api/branding/logo').status_code == 404
    assert client.get('/api/branding/logo').status_code == 404


def test_branding_get_has_no_logo_field(client):
    _login(client)
    body = client.get('/api/branding').get_json()
    assert body is not None
    assert 'has_logo' not in body


def test_wizard_done_endpoint_is_gone(client):
    _login(client)
    assert client.post('/api/branding/wizard-done').status_code == 404


def test_branding_get_has_no_wizard_field(client):
    _login(client)
    body = client.get('/api/branding').get_json()
    assert 'wizard_done' not in body


def test_marketing_posts_schema_has_template_json_not_photo_count(client):
    # client fixture has already run init_database() against a fresh temp DB.
    conn = _sqlite3.connect(dental_clinic.DB_NAME)
    cols = {row[1] for row in conn.execute('PRAGMA table_info(marketing_posts)')}
    conn.close()
    assert 'template_json' in cols
    assert 'photo_count' not in cols
    assert 'labels_json' not in cols


def test_photos_requires_login(client):
    assert client.post('/api/posts/photos').status_code == 401


def test_photos_upload_returns_staged_paths(client):
    _login(client)
    r = client.post('/api/posts/photos',
                    data={'photo': [(io.BytesIO(_png()), 'a.png'),
                                    (io.BytesIO(_png()), 'b.png')]},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    paths = r.get_json()['photos']
    assert len(paths) == 2
    assert all(p.startswith('posts/_staging/') for p in paths)
    assert all((dental_clinic.UPLOAD_FOLDER / p).exists() for p in paths)


def test_photos_rejects_zero_and_too_many(client):
    _login(client)
    assert client.post('/api/posts/photos', data={},
                       content_type='multipart/form-data').status_code == 400
    seven = [(io.BytesIO(_png()), f'p{i}.png') for i in range(7)]
    assert client.post('/api/posts/photos', data={'photo': seven},
                       content_type='multipart/form-data').status_code == 400


def test_photos_rejects_non_image(client):
    _login(client)
    r = client.post('/api/posts/photos',
                    data={'photo': [(io.BytesIO(b'not an image'), 'x.png')]},
                    content_type='multipart/form-data')
    assert r.status_code == 400
