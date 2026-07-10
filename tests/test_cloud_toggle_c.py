# tests/test_cloud_toggle_c.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.delenv('CLINIC_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_LICENSE_CLOUD_URL', raising=False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _stub_cloud_ok(monkeypatch, sink):
    def fake_http(method, url, headers=None, body=None, timeout=15):
        sink['url'] = url
        sink['body'] = body
        return 200, {'clinic_token': 'tok-xyz', 'clinic_id': 11}
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True, 'pulled': 0, 'pushed': 0})


def test_helper_exists():
    assert hasattr(dental_clinic, '_link_clinic_to_cloud')


def test_cloud_pair_still_works(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    r = local.post('/api/cloud/pair',
                   json={'cloud_url': 'https://c.example.test', 'serial_number': 'DENTAL-C-PAIR1'})
    assert r.status_code == 200
    conn = dental_clinic.get_db_connection()
    assert conn.execute("SELECT value FROM app_settings WHERE key='cloud_clinic_token'").fetchone()[0] == 'tok-xyz'
    conn.close()


def _set_setting(key, value):
    conn = dental_clinic.get_db_connection()
    conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def test_enable_without_license_409(local):
    r = local.post('/api/cloud/enable')
    assert r.status_code == 409
    assert r.get_json()['reason'] == 'not_activated'


def test_enable_uses_active_serial_and_baked_url(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    _set_setting('active_serial_number', 'DENTAL-C-EN1')
    _set_setting('active_serial_token', 'signed.token.here')
    r = local.post('/api/cloud/enable')
    assert r.status_code == 200
    # registered against the baked base, with the active serial + retained token forwarded
    assert sink['url'].startswith(dental_clinic._BAKED_CLOUD_BASE_URL)
    assert sink['body']['serial_number'] == 'DENTAL-C-EN1'
    assert sink['body']['offline_token'] == 'signed.token.here'
    conn = dental_clinic.get_db_connection()
    assert conn.execute("SELECT value FROM app_settings WHERE key='cloud_clinic_token'").fetchone()[0] == 'tok-xyz'
    conn.close()


def test_pair_falls_back_to_active_serial_token(local, monkeypatch):
    """Regression for the post-activation 'Enable secure cloud backup' popup.

    That popup calls /api/cloud/pair with only {serial_number} — no offline_token.
    After an ONLINE activation only `active_serial_token` is stored (never
    `cloud_offline_token`), so the pair must fall back to it. Otherwise the request
    reaches the cloud's signed-serial gate unsigned and is rejected with HTTP 403
    (surfaced to the user as 'Cloud registration failed (HTTP 403)')."""
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    monkeypatch.delenv('CLINIC_OFFLINE_TOKEN', raising=False)
    _set_setting('active_serial_number', 'DENTAL-C-PAIR2')
    _set_setting('active_serial_token', 'signed.activation.token')
    r = local.post('/api/cloud/pair',
                   json={'cloud_url': 'https://c.example.test',
                         'serial_number': 'DENTAL-C-PAIR2'})
    assert r.status_code == 200
    assert sink['body']['offline_token'] == 'signed.activation.token'


def test_resolve_offline_token_precedence(local, monkeypatch):
    """body > cloud_offline_token > active_serial_token > env."""
    monkeypatch.delenv('CLINIC_OFFLINE_TOKEN', raising=False)
    # Nothing configured anywhere → empty.
    assert dental_clinic._resolve_offline_token({}) == ''
    # active_serial_token is the lowest DB tier.
    _set_setting('active_serial_token', 'from-activation')
    assert dental_clinic._resolve_offline_token({}) == 'from-activation'
    # A prior pair's cloud_offline_token wins over the activation token.
    _set_setting('cloud_offline_token', 'from-prior-pair')
    assert dental_clinic._resolve_offline_token({}) == 'from-prior-pair'
    # An explicit body token wins over everything.
    assert dental_clinic._resolve_offline_token({'offline_token': 'from-body'}) == 'from-body'


def _license_count():
    conn = dental_clinic.get_db_connection()
    n = conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
    conn.close()
    return n


def dental_clinic_active_serial():
    conn = dental_clinic.get_db_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key='active_serial_number'").fetchone()
    conn.close()
    return row[0] if row else None


def test_enable_does_not_touch_license(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    _set_setting('active_serial_number', 'DENTAL-C-DEC')
    before = _license_count()
    local.post('/api/cloud/enable')
    assert _license_count() == before                  # enable never writes licenses
    assert dental_clinic_active_serial() == 'DENTAL-C-DEC'


def test_unpair_does_not_touch_license(local):
    _set_setting('active_serial_number', 'DENTAL-C-DEC2')
    local.post('/api/cloud/unpair')
    assert dental_clinic_active_serial() == 'DENTAL-C-DEC2'   # unpair leaves the license alone
