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


def _set_serial(serial, **cols):
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    sets = ', '.join(f'{k} = ?' for k in cols)
    conn.execute(f'UPDATE license_serials SET {sets} WHERE serial = ?',
                 (*cols.values(), serial))
    conn.commit(); conn.close()


def test_validate_blocks_revoked(cloud):
    _validate(cloud, _sign(cloud, 'DENTAL-REV-0001'))      # register
    _set_serial('DENTAL-REV-0001', status='revoked')
    body = _validate(cloud, _sign(cloud, 'DENTAL-REV-0001')).get_json()
    assert body['valid'] is False and body['reason'] == 'revoked'


def test_validate_expired_past_grace(cloud):
    tok = _sign(cloud, 'DENTAL-EXP-0001', expiry_days=-60)  # expired 60d ago, grace 14d
    body = _validate(cloud, tok).get_json()
    assert body['valid'] is False and body['reason'] == 'expired'


def test_validate_within_grace_ok(cloud):
    tok = _sign(cloud, 'DENTAL-GRC-0001', expiry_days=-5)   # expired 5d ago, still in 14d grace
    assert _validate(cloud, tok).get_json()['valid'] is True


def test_validate_renewal_extends_and_reactivates(cloud):
    _validate(cloud, _sign(cloud, 'DENTAL-RENEW-1', expiry_days=-60))  # expired
    assert _validate(cloud, _sign(cloud, 'DENTAL-RENEW-1', expiry_days=-60)).get_json()['reason'] == 'expired'
    body = _validate(cloud, _sign(cloud, 'DENTAL-RENEW-1', expiry_days=365)).get_json()  # renew
    assert body['valid'] is True and body['status'] == 'active'


def test_device_cap_claims_and_blocks(cloud):
    s = 'DENTAL-CAP-0001'
    assert _validate(cloud, _sign(cloud, s, max_devices=2), fp='d1').get_json()['valid'] is True
    assert _validate(cloud, _sign(cloud, s, max_devices=2), fp='d2').get_json()['valid'] is True
    body = _validate(cloud, _sign(cloud, s, max_devices=2), fp='d3').get_json()
    assert body['valid'] is False and body['reason'] == 'device_cap_reached'


def test_device_reclaim_is_idempotent(cloud):
    s = 'DENTAL-CAP-0002'
    _validate(cloud, _sign(cloud, s, max_devices=1), fp='same')
    body = _validate(cloud, _sign(cloud, s, max_devices=1), fp='same').get_json()
    assert body['valid'] is True and body['remaining_slots'] == 0


def test_device_cap_atomic_under_concurrency(cloud):
    import threading
    s = 'DENTAL-CAP-0003'
    _validate(cloud, _sign(cloud, s, max_devices=2), fp='warm')  # create serial row (cap 2, 1 used)
    results = []
    def hit(i):
        with dental_clinic.app.test_client() as c:
            c.priv_b64 = cloud.priv_b64
            results.append(_validate(c, _sign(c, s, max_devices=2), fp=f'race-{i}').get_json()['valid'])
    threads = [threading.Thread(target=hit, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    conn = sqlite3.connect(dental_clinic.MASTER_DB_PATH)
    active = conn.execute("SELECT COUNT(*) FROM license_device_slots WHERE serial=? AND is_active=1", (s,)).fetchone()[0]
    conn.close()
    assert active <= 2, f'cap exceeded: {active} active slots'


def test_admin_revoke_requires_token(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    _validate(cloud, _sign(cloud, 'DENTAL-ADM-0001'))
    no_tok = cloud.post('/api/license/admin/revoke', json={'serial': 'DENTAL-ADM-0001', 'status': 'revoked'})
    assert no_tok.status_code == 401
    ok = cloud.post('/api/license/admin/revoke',
                    headers={'X-Admin-Token': 'secret'},
                    json={'serial': 'DENTAL-ADM-0001', 'status': 'revoked'})
    assert ok.status_code == 200
    assert _validate(cloud, _sign(cloud, 'DENTAL-ADM-0001')).get_json()['reason'] == 'revoked'


def test_admin_release_frees_slot(cloud, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_ADMIN_API_TOKEN', 'secret')
    s = 'DENTAL-ADM-0002'
    _validate(cloud, _sign(cloud, s, max_devices=1), fp='phone-A')
    assert _validate(cloud, _sign(cloud, s, max_devices=1), fp='phone-B').get_json()['reason'] == 'device_cap_reached'
    cloud.post('/api/license/admin/revoke', headers={'X-Admin-Token': 'secret'},
               json={'serial': s, 'device_fingerprint': 'phone-A', 'release': True})
    assert _validate(cloud, _sign(cloud, s, max_devices=1), fp='phone-B').get_json()['valid'] is True
