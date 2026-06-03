import sqlite3
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
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        c.priv_b64 = priv_b64
        yield c
    dental_clinic._set_request_db_path(None)


def _columns(master_path, table):
    conn = sqlite3.connect(master_path)
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]
    conn.close()
    return cols


def test_license_tables_exist(cloud):
    cols = _columns(dental_clinic.MASTER_DB_PATH, 'license_serials')
    assert {'serial', 'status', 'max_devices', 'expires_at', 'grace_until'} <= set(cols)
    slot_cols = _columns(dental_clinic.MASTER_DB_PATH, 'license_device_slots')
    assert {'serial', 'device_fingerprint', 'is_active'} <= set(slot_cols)


def _sign(client, serial, **kw):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = {
        'v': 2, 'serial': serial, 'clinic_name': 'C', 'max_devices': kw.get('max_devices', 3),
        'issued_at': now.isoformat() + 'Z',
        'expires_at': (now + timedelta(days=kw.get('expiry_days', 365))).isoformat() + 'Z',
        'grace_until': (now + timedelta(days=kw.get('expiry_days', 365) + 14)).isoformat() + 'Z',
    }
    return serial_generator.sign_serial_token(payload, client.priv_b64)


def _validate(client, token, fp='device-1'):
    return client.post('/api/license/validate',
                       json={'serial_token': token, 'device_fingerprint': fp})


def test_validate_accepts_signed_serial(cloud):
    r = _validate(cloud, _sign(cloud, 'DENTAL-VAL-0001'))
    assert r.status_code == 200
    body = r.get_json()
    assert body['valid'] is True
    assert body['status'] == 'active'


def test_validate_rejects_random(cloud):
    r = _validate(cloud, 'not-a-real-token')
    assert r.status_code == 200
    assert r.get_json()['valid'] is False
    assert r.get_json()['reason'] in ('bad_signature', 'malformed')


def test_validate_registers_on_first_use(cloud):
    _validate(cloud, _sign(cloud, 'DENTAL-VAL-0002'))
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    row = conn.execute("SELECT status FROM license_serials WHERE serial='DENTAL-VAL-0002'").fetchone()
    conn.close()
    assert row is not None and row[0] == 'active'


def test_validate_is_404_when_not_cloud(monkeypatch, tmp_path):
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(tmp_path / 'x.db'))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        assert c.post('/api/license/validate', json={'serial_token': 't', 'device_fingerprint': 'd'}).status_code == 404
