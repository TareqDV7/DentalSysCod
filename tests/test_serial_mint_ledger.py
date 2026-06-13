"""Vendor mint ledger + publish-existing-token + cloud-registry proxy.

The minting console now keeps a local SQLite ledger of every serial it issues (so
the vendor never loses track), can publish a previously-minted Activation Code to
the cloud registry (the fix for "online activation fails because the serial was
never published"), and can view the live cloud registry.
"""
import json

import pytest

import serial_generator
import serial_admin


@pytest.fixture()
def vendor(tmp_path, monkeypatch):
    """serial_admin app with a temp keypair + a temp ledger (derived from KEY_FILE
    dir, so each test gets an isolated minted_serials.db)."""
    priv, pub = serial_generator.generate_keypair()
    key_file = tmp_path / 'backend_ed25519_key.json'
    key_file.write_text(json.dumps({'alg': 'ed25519', 'private': priv}), encoding='utf-8')
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(key_file))
    monkeypatch.delenv(serial_admin.LEDGER_FILE_ENV, raising=False)
    with serial_admin.app.test_client() as c:
        c.pub_b64 = pub
        c.priv_b64 = priv
        yield c


def _mint(client, **body):
    base = {'clinic_name': 'Wasfy', 'clinic_code': 'KHK', 'plan_name': 'Standard',
            'expiry_days': 365, 'max_devices': 3}
    base.update(body)
    return client.post('/api/mint', json=base)


# ── ledger writes on mint ─────────────────────────────────────────────────────

def test_mint_writes_to_ledger(vendor):
    rec = _mint(vendor, devices=['LAPTOP-01']).get_json()['records'][0]
    hist = vendor.get('/api/history').get_json()['records']
    assert len(hist) == 1
    row = hist[0]
    assert row['serial'] == rec['serial']
    assert row['clinic_name'] == 'Wasfy'
    assert row['clinic_code'] == 'KHK'
    assert row['plan_name'] == 'Standard'
    assert row['offline_token'] == rec['offline_token']
    assert row['published'] == 0  # minted but not yet pushed to the cloud


def test_history_accumulates_across_mints(vendor):
    _mint(vendor, devices=['A', 'B'])
    _mint(vendor, devices=['C'])
    hist = vendor.get('/api/history').get_json()['records']
    assert len(hist) == 3
    assert len({r['serial'] for r in hist}) == 3


def test_history_empty_before_any_mint(vendor):
    assert vendor.get('/api/history').get_json()['records'] == []


def test_history_loopback_guarded(vendor):
    r = vendor.get('/api/history', environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403


# ── upload-cloud marks the ledger published ───────────────────────────────────

def test_upload_cloud_marks_published(vendor, monkeypatch):
    recs = _mint(vendor, devices=['L1', 'L2']).get_json()['records']
    monkeypatch.setattr(
        serial_admin, '_upload_records_to_cloud',
        lambda records, url, tok: [{'serial': r['serial'], 'ok': True} for r in records])
    vendor.post('/api/upload-cloud',
                json={'records': recs, 'cloud_url': 'https://cloud.test', 'admin_token': 'sek'})
    hist = vendor.get('/api/history').get_json()['records']
    assert all(r['published'] == 1 for r in hist)
    assert all(r['cloud_url'] == 'https://cloud.test' for r in hist)


def test_upload_failure_leaves_unpublished(vendor, monkeypatch):
    recs = _mint(vendor, devices=['L1']).get_json()['records']
    monkeypatch.setattr(
        serial_admin, '_upload_records_to_cloud',
        lambda records, url, tok: [{'serial': r['serial'], 'ok': False, 'error': 'boom'} for r in records])
    vendor.post('/api/upload-cloud',
                json={'records': recs, 'cloud_url': 'https://cloud.test', 'admin_token': 'sek'})
    hist = vendor.get('/api/history').get_json()['records']
    assert all(r['published'] == 0 for r in hist)


# ── publish an existing Activation Code (the KHK unblock) ─────────────────────

def _sign_record(vendor, serial='DENTAL-KHK-CLINI-00001'):
    """Build a real signed token the way the minter does, to feed publish-token."""
    rec = _mint(vendor, devices=['CLINIC-KHK']).get_json()['records'][0]
    return rec


def test_publish_token_decodes_serial_and_records(vendor, monkeypatch):
    rec = _sign_record(vendor)
    captured = {}

    def fake_upload(records, url, tok):
        captured['token'] = records[0]['offline_token']
        captured['url'] = url
        captured['admin'] = tok
        return [{'serial': records[0]['serial'], 'ok': True}]

    monkeypatch.setattr(serial_admin, '_upload_records_to_cloud', fake_upload)
    r = vendor.post('/api/publish-token', json={
        'offline_token': rec['offline_token'], 'cloud_url': 'https://cloud.test',
        'admin_token': 'sek'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['result']['ok'] is True
    assert body['serial'] == rec['serial']
    assert captured['token'] == rec['offline_token']
    assert captured['url'] == 'https://cloud.test' and captured['admin'] == 'sek'
    # ledger now has the serial flagged published
    hist = {h['serial']: h for h in vendor.get('/api/history').get_json()['records']}
    assert hist[rec['serial']]['published'] == 1


def test_publish_token_requires_token_url_admin(vendor):
    assert vendor.post('/api/publish-token', json={'cloud_url': 'x', 'admin_token': 't'}).status_code == 400
    assert vendor.post('/api/publish-token', json={'offline_token': 'eyJ.x', 'admin_token': 't'}).status_code == 400
    assert vendor.post('/api/publish-token', json={'offline_token': 'eyJ.x', 'cloud_url': 'x'}).status_code == 400


def test_publish_token_not_recorded_on_failure(vendor, monkeypatch):
    rec = _sign_record(vendor)
    # wipe the ledger row first so we can assert publish-of-failure doesn't flip it
    monkeypatch.setattr(serial_admin, '_upload_records_to_cloud',
                        lambda records, url, tok: [{'serial': records[0]['serial'], 'ok': False, 'error': 'bad sig'}])
    vendor.post('/api/publish-token', json={
        'offline_token': rec['offline_token'], 'cloud_url': 'https://cloud.test', 'admin_token': 'sek'})
    hist = {h['serial']: h for h in vendor.get('/api/history').get_json()['records']}
    assert hist[rec['serial']]['published'] == 0


def test_publish_token_loopback_guarded(vendor):
    r = vendor.post('/api/publish-token',
                    json={'offline_token': 'eyJ.x', 'cloud_url': 'x', 'admin_token': 't'},
                    environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403


# ── decode helper ─────────────────────────────────────────────────────────────

def test_decode_token_payload_reads_serial(vendor):
    rec = _mint(vendor, devices=['D1']).get_json()['records'][0]
    payload = serial_admin._decode_token_payload(rec['offline_token'])
    assert payload['serial'] == rec['serial']
    assert payload['clinic_name'] == 'Wasfy'


def test_decode_token_payload_garbage_is_none():
    assert serial_admin._decode_token_payload('not-a-token') is None
    assert serial_admin._decode_token_payload('') is None


# ── cloud-registry proxy ──────────────────────────────────────────────────────

def test_cloud_serials_requires_url_and_token(vendor):
    assert vendor.post('/api/cloud/serials', json={'admin_token': 't'}).status_code == 400
    assert vendor.post('/api/cloud/serials', json={'cloud_url': 'https://x'}).status_code == 400


def test_cloud_serials_proxies_list(vendor, monkeypatch):
    seen = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"serials": [{"serial": "DENTAL-KHK-CLINI-00001", "status": "active"}], "count": 1}'

    def fake_urlopen(req, timeout=15):
        seen['url'] = req.full_url
        seen['admin'] = req.headers.get('X-admin-token')
        return _Resp()

    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', fake_urlopen)
    r = vendor.post('/api/cloud/serials', json={'cloud_url': 'https://cloud.test/', 'admin_token': 'sek'})
    assert r.status_code == 200
    assert r.get_json()['count'] == 1
    assert seen['url'] == 'https://cloud.test/api/license/admin/serials'
    assert seen['admin'] == 'sek'


def test_cloud_serials_loopback_guarded(vendor):
    r = vendor.post('/api/cloud/serials', json={'cloud_url': 'x', 'admin_token': 't'},
                    environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403
