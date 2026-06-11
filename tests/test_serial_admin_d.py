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


def _mint(client, **body):
    base = {'clinic_name': 'Smile Dental', 'clinic_code': 'SMD', 'plan_name': 'Standard',
            'expiry_days': 365, 'max_devices': 3}
    base.update(body)
    return client.post('/api/mint', json=base)


def test_mint_single_verifies(vendor):
    r = _mint(vendor, devices=['LAPTOP-01'])
    assert r.status_code == 200
    recs = r.get_json()['records']
    assert len(recs) == 1
    ok, payload = serial_generator.verify_serial_token(recs[0]['offline_token'], vendor.pub_b64)
    assert ok is True
    assert payload['max_devices'] == 3
    assert payload['plan_name'] == 'Standard'
    assert payload['serial'] == recs[0]['serial']


def test_mint_batch_distinct_and_valid(vendor):
    recs = _mint(vendor, devices=['A', 'B', 'C']).get_json()['records']
    assert len(recs) == 3
    serials = {x['serial'] for x in recs}
    assert len(serials) == 3
    for x in recs:
        ok, _ = serial_generator.verify_serial_token(x['offline_token'], vendor.pub_b64)
        assert ok is True


def test_mint_clinic_level_when_no_devices(vendor):
    recs = _mint(vendor, devices=[]).get_json()['records']
    assert len(recs) == 1
    ok, _ = serial_generator.verify_serial_token(recs[0]['offline_token'], vendor.pub_b64)
    assert ok is True


def test_mint_clinic_level_serials_are_unique_across_calls(vendor):
    """Re-minting a clinic-level key must NOT reuse one serial. The cloud
    registers idempotently by serial, so a repeated serial would bind every
    "new" key to the same clinic — which is the bug this guards against."""
    s1 = _mint(vendor, devices=[]).get_json()['records'][0]['serial']
    s2 = _mint(vendor, devices=[]).get_json()['records'][0]['serial']
    assert s1 != s2
    # Same request, same device input — uniqueness comes from the serial itself.
    same_device = lambda: _mint(vendor, devices=['LAPTOP-01']).get_json()['records'][0]['serial']
    assert same_device() != same_device()


def test_generate_device_serial_number_is_unique_and_well_formed():
    a = serial_generator.generate_device_serial_number('SMD', 'CLINIC-SMD', 1)
    b = serial_generator.generate_device_serial_number('SMD', 'CLINIC-SMD', 1)
    assert a != b
    assert a.startswith('DENTAL-SMD-')
    assert len(a) >= 8  # cloud register floor


def test_mint_without_key_400(tmp_path, monkeypatch):
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(tmp_path / 'missing.json'))
    with serial_admin.app.test_client() as c:
        r = c.post('/api/mint', json={'clinic_name': 'X', 'clinic_code': 'X', 'devices': ['D']})
        assert r.status_code == 400
        assert r.get_json()['reason'] == 'no_key'


def test_mint_csv_format(vendor):
    r = vendor.post(
        '/api/mint?format=csv',
        json={'clinic_name': 'Smile', 'clinic_code': 'SMD', 'devices': ['A', 'B'],
              'plan_name': 'Standard', 'expiry_days': 365, 'max_devices': 1})
    assert r.status_code == 200
    assert 'text/csv' in r.headers['Content-Type']
    text = r.get_data(as_text=True)
    assert 'Serial' in text and text.count('\n') >= 2  # header + 2 rows


@pytest.mark.parametrize('body', [
    {}, {'clinic_name': '', 'clinic_code': 'SMD'},
    {'clinic_name': 'X', 'clinic_code': 'TOOLONG'},
    {'clinic_name': 'X', 'clinic_code': 'SMD', 'devices': 'x' * 5000},
])
def test_mint_never_500s(vendor, body):
    r = vendor.post('/api/mint', json=body)
    assert r.status_code in (200, 400)


# ── Publish to cloud (short-serial activation pre-load) ───────────────────────

def test_upload_cloud_requires_records(vendor):
    r = vendor.post('/api/upload-cloud', json={'cloud_url': 'https://x', 'admin_token': 't'})
    assert r.status_code == 400


def test_upload_cloud_requires_url_and_token(vendor):
    recs = _mint(vendor, devices=['L1']).get_json()['records']
    assert vendor.post('/api/upload-cloud', json={'records': recs, 'admin_token': 't'}).status_code == 400
    assert vendor.post('/api/upload-cloud', json={'records': recs, 'cloud_url': 'https://x'}).status_code == 400


def test_upload_cloud_reports_per_serial(vendor, monkeypatch):
    recs = _mint(vendor, devices=['L1', 'L2']).get_json()['records']
    captured = {}

    def fake_upload(records, cloud_url, admin_token):
        captured['url'] = cloud_url
        captured['token'] = admin_token
        return [{'serial': r['serial'], 'ok': True, 'already_existed': False} for r in records]

    monkeypatch.setattr(serial_admin, '_upload_records_to_cloud', fake_upload)
    r = vendor.post('/api/upload-cloud',
                    json={'records': recs, 'cloud_url': 'https://cloud.test', 'admin_token': 'sek'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok_count'] == 2 and body['total'] == 2
    assert captured['url'] == 'https://cloud.test' and captured['token'] == 'sek'


def test_upload_records_posts_to_admin_register_endpoint(vendor, monkeypatch):
    recs = _mint(vendor, devices=['L1']).get_json()['records']
    seen = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"success": true, "already_existed": false}'

    def fake_urlopen(req, timeout=15):
        seen['url'] = req.full_url
        seen['admin'] = req.headers.get('X-admin-token')
        seen['body'] = json.loads(req.data.decode('utf-8'))
        return _Resp()

    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', fake_urlopen)
    out = serial_admin._upload_records_to_cloud(recs, 'https://cloud.test/', 'sek')
    assert out[0]['ok'] is True
    assert seen['url'] == 'https://cloud.test/api/license/admin/register-serial'
    assert seen['admin'] == 'sek'
    assert seen['body']['serial_token'] == recs[0]['offline_token']


def test_upload_cloud_loopback_guarded(vendor):
    r = vendor.post('/api/upload-cloud', json={'records': [{}], 'cloud_url': 'x', 'admin_token': 't'},
                    environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403
