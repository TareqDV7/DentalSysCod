"""Cloud read-only serial registry: GET /api/license/admin/serials.

Admin-token gated list of every serial the cloud knows, with live device usage —
so the vendor can see what has actually been issued/registered. Never returns the
signed token (a secret); exposes a `has_token` flag instead.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import serial_generator
import dental_clinic


@pytest.fixture()
def cloud(tmp_path, monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    data_dir = tmp_path / 'clouddata'
    data_dir.mkdir()
    master = str(data_dir / 'cloud_master.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', master)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', dental_clinic._DbPathProxy(master))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', data_dir / 'uploads')
    (data_dir / 'uploads').mkdir(exist_ok=True)
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    monkeypatch.setattr(dental_clinic, '_register_attempts', {})
    monkeypatch.setattr(dental_clinic, '_validate_attempts', {})
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        c.priv_b64 = priv_b64
        yield c
    dental_clinic._set_request_db_path(None)


def _sign(client, serial, **kw):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {
        'v': 2, 'serial': serial, 'clinic_name': kw.get('clinic_name', 'C'),
        'plan_name': kw.get('plan_name', 'standard'),
        'max_devices': kw.get('max_devices', 3),
        'issued_at': now.isoformat() + 'Z',
        'expires_at': (now + timedelta(days=kw.get('expiry_days', 365))).isoformat() + 'Z',
        'grace_until': (now + timedelta(days=kw.get('expiry_days', 365) + 14)).isoformat() + 'Z',
    }
    return serial_generator.sign_serial_token(payload, client.priv_b64)


def _register(client, token):
    return client.post('/api/license/admin/register-serial',
                       headers={'X-Admin-Token': 'secret'}, json={'serial_token': token})


def _list(client, token='secret'):
    headers = {'X-Admin-Token': token} if token is not None else {}
    return client.get('/api/license/admin/serials', headers=headers)


# ── gating ────────────────────────────────────────────────────────────────────

def test_list_404_on_local(monkeypatch, tmp_path):
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'x.db'))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        assert c.get('/api/license/admin/serials').status_code == 404


def test_list_requires_admin_token(cloud):
    assert _list(cloud, token=None).status_code == 401
    assert _list(cloud, token='wrong').status_code == 401


def test_list_empty_registry(cloud):
    body = _list(cloud).get_json()
    assert body['count'] == 0 and body['serials'] == []


# ── content ───────────────────────────────────────────────────────────────────

def test_list_returns_registered_serial(cloud):
    _register(cloud, _sign(cloud, 'DENTAL-KHK-CLINI-00001', clinic_name='Wasfy', plan_name='Standard'))
    body = _list(cloud).get_json()
    assert body['count'] == 1
    row = body['serials'][0]
    assert row['serial'] == 'DENTAL-KHK-CLINI-00001'
    assert row['clinic_name'] == 'Wasfy'
    assert row['plan_name'] == 'Standard'
    assert row['status'] == 'active'
    assert row['has_token'] is True
    assert row['used_devices'] == 0
    assert row['max_devices'] == 3


def test_list_never_returns_serial_token(cloud):
    tok = _sign(cloud, 'DENTAL-SEC-0001')
    _register(cloud, tok)
    raw = _list(cloud).get_data(as_text=True)
    assert tok not in raw
    assert 'serial_token' not in raw


def test_list_counts_active_devices(cloud):
    _register(cloud, _sign(cloud, 'DENTAL-DEV-0001', max_devices=3))
    cloud.post('/api/license/claim',
               json={'serial_number': 'DENTAL-DEV-0001', 'device_fingerprint': 'fp-a'})
    cloud.post('/api/license/claim',
               json={'serial_number': 'DENTAL-DEV-0001', 'device_fingerprint': 'fp-b'})
    row = _list(cloud).get_json()['serials'][0]
    assert row['used_devices'] == 2
    assert row['max_devices'] == 3


def test_list_has_token_false_for_tokenless_row(cloud):
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    conn.execute("INSERT INTO license_serials (serial, status, max_devices) "
                 "VALUES ('DENTAL-LEGACY-01', 'active', 3)")
    conn.commit()
    conn.close()
    row = _list(cloud).get_json()['serials'][0]
    assert row['serial'] == 'DENTAL-LEGACY-01'
    assert row['has_token'] is False
