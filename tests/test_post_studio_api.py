import io
import json as _json
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


_TJSON = _json.dumps({'version': 1, 'size': 'square', 'theme': 'dark_premium',
                      'elements': [{'id': 'strip', 'type': 'photoStrip', 'blocks': []}]})


def _save_post(client):
    return client.post(
        '/api/posts',
        data={'image': (io.BytesIO(_png()), 'export.png'),
              'template_json': _TJSON, 'theme': 'dark_premium',
              'size': 'square', 'title': 'Root Canal'},
        content_type='multipart/form-data')


def test_save_requires_login(client):
    assert client.post('/api/posts').status_code == 401


def test_save_persists_png_and_spec_then_roundtrips(client):
    _login(client)
    pid = _save_post(client).get_json()['id']
    # list
    listing = client.get('/api/posts').get_json()
    row = next(p for p in listing if p['id'] == pid)
    assert row['title'] == 'Root Canal'
    assert 'photo_count' not in row
    # get-spec (re-edit) round-trips the template_json
    spec = client.get(f'/api/posts/{pid}').get_json()
    assert _json.loads(spec['template_json'])['theme'] == 'dark_premium'
    # serve the exported PNG
    img = client.get(f'/api/posts/{pid}/image')
    assert img.status_code == 200 and img.content_type.startswith('image/png')
    # delete
    assert client.delete(f'/api/posts/{pid}').status_code == 200
    assert client.get(f'/api/posts/{pid}').status_code == 404


def test_save_rejects_missing_png_or_bad_spec(client):
    _login(client)
    no_png = client.post('/api/posts',
                         data={'template_json': _TJSON, 'theme': 'dark_premium', 'size': 'square'},
                         content_type='multipart/form-data')
    assert no_png.status_code == 400
    bad_spec = client.post('/api/posts',
                           data={'image': (io.BytesIO(_png()), 'e.png'),
                                 'template_json': 'not json', 'theme': 'dark_premium', 'size': 'square'},
                           content_type='multipart/form-data')
    assert bad_spec.status_code == 400


def test_get_spec_open_to_mobile_read_posture(client):
    # like /api/posts and /api/posts/<id>/image, the spec GET is reachable
    # without the portal session (mobile uses device/clinic-token headers).
    assert client.get('/api/posts/999').status_code == 404  # handler ran, not 401


def test_pillow_engine_is_retired():
    import importlib.util
    assert importlib.util.find_spec('post_studio') is None
    assert importlib.util.find_spec('post_themes') is None


def test_preview_route_is_gone(client):
    _login(client)
    assert client.post('/api/posts/preview').status_code == 404
