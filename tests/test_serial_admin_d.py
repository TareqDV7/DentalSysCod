import json
import pytest
import serial_generator
import serial_admin


@pytest.fixture()
def vendor(tmp_path, monkeypatch):
    """serial_admin app with a temp vendor keypair on disk."""
    priv, pub = serial_generator.generate_keypair()
    key_file = tmp_path / 'backend_ed25519_key.json'
    key_file.write_text(json.dumps({'alg': 'ed25519', 'private': priv}), encoding='utf-8')
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(key_file))
    with serial_admin.app.test_client() as c:
        c.pub_b64 = pub
        c.priv_b64 = priv
        yield c


def test_key_status_returns_public_only(vendor):
    r = vendor.get('/api/key/status')
    assert r.status_code == 200
    body = r.get_json()
    assert body['has_key'] is True
    assert body['public_key'] == vendor.pub_b64
    # The private seed must NEVER appear in any response.
    assert 'private' not in r.get_data(as_text=True)
    assert vendor.priv_b64 not in r.get_data(as_text=True)


def test_key_status_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(tmp_path / 'missing.json'))
    with serial_admin.app.test_client() as c:
        assert c.get('/api/key/status').get_json()['has_key'] is False


def test_loopback_guard_blocks_remote(vendor):
    r = vendor.get('/api/key/status', environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403


def test_generate_refuses_to_clobber(vendor):
    r = vendor.post('/api/key/generate', json={})
    assert r.status_code == 409
    assert r.get_json()['reason'] == 'exists'
    assert vendor.priv_b64 not in r.get_data(as_text=True)


def test_generate_with_confirm_rotates_key(vendor):
    r = vendor.post('/api/key/generate', json={'confirm_overwrite': True})
    assert r.status_code == 200
    body = r.get_json()
    assert body['public_key'] and body['public_key'] != vendor.pub_b64  # new key
    assert 'private' not in r.get_data(as_text=True)


def test_generate_when_absent(tmp_path, monkeypatch):
    path = tmp_path / 'new_key.json'
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(path))
    with serial_admin.app.test_client() as c:
        r = c.post('/api/key/generate', json={})
        assert r.status_code == 200
        assert r.get_json()['public_key']
        assert path.exists()
