# tests/test_cloud_always_on_d.py
"""Always-on cloud sync (no toggle): the local server auto-links to the cloud
using the activation key (active_serial_number + active_serial_token), and the
routine license-validate endpoint no longer shares the tight anti-spam register
rate limit (the cause of spurious HTTP 429 on cloud sync)."""
import sqlite3
import pytest
import dental_clinic


@pytest.fixture(autouse=True)
def _reset_rate_buckets():
    dental_clinic._register_attempts.clear()
    dental_clinic._validate_attempts.clear()
    yield
    dental_clinic._register_attempts.clear()
    dental_clinic._validate_attempts.clear()


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.delenv('CLINIC_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_LICENSE_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_CLOUD_SYNC_DISABLED', raising=False)
    dental_clinic.init_database()
    return db


def _set_setting(key, value):
    conn = dental_clinic.get_db_connection()
    conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def _get_setting(key):
    conn = dental_clinic.get_db_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


def _stub_cloud_ok(monkeypatch, sink):
    def fake_http(method, url, headers=None, body=None, timeout=15):
        sink['url'] = url
        sink['body'] = body
        return 200, {'clinic_token': 'auto-tok', 'clinic_id': 42}
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once',
                        lambda *a, **k: {'ok': True, 'pulled': 0, 'pushed': 0})


# --- auto-link from the activation key (no toggle) --------------------------

def test_auto_pair_links_using_activation_key(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    _set_setting('active_serial_number', 'DENTAL-AUTO-0001')
    _set_setting('active_serial_token', 'signed.activation.token')

    assert dental_clinic._try_auto_cloud_pair() is True
    # Linked against the baked cloud URL using the stored serial + token — no inputs.
    assert sink['url'].startswith(dental_clinic._BAKED_CLOUD_BASE_URL)
    assert sink['body']['serial_number'] == 'DENTAL-AUTO-0001'
    assert sink['body']['offline_token'] == 'signed.activation.token'
    assert _get_setting('cloud_clinic_token') == 'auto-tok'


def test_auto_pair_noop_when_not_activated(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)  # would succeed if called
    assert dental_clinic._try_auto_cloud_pair() is False
    assert _get_setting('cloud_clinic_token') is None
    assert 'url' not in sink  # the register call was never made


def test_auto_pair_respects_disable_env(local, monkeypatch):
    sink = {}
    _stub_cloud_ok(monkeypatch, sink)
    _set_setting('active_serial_number', 'DENTAL-AUTO-0002')
    monkeypatch.setenv('CLINIC_CLOUD_SYNC_DISABLED', '1')
    assert dental_clinic._try_auto_cloud_pair() is False
    assert _get_setting('cloud_clinic_token') is None


def test_auto_sync_disabled_on_cloud_node(monkeypatch):
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert dental_clinic._auto_cloud_sync_enabled() is False


def test_status_reports_auto_sync_and_activation(local, monkeypatch):
    with dental_clinic.app.test_client() as c:
        st = c.get('/api/cloud/status').get_json()
        assert st['auto_sync'] is True
        assert st['activated'] is False      # nothing activated yet
        _set_setting('active_serial_number', 'DENTAL-AUTO-0003')
        st2 = c.get('/api/cloud/status').get_json()
        assert st2['activated'] is True


# --- rate-limit separation: validate must not share register's tight budget ---

def test_validate_limit_independent_of_register(monkeypatch):
    monkeypatch.setattr(dental_clinic, '_REGISTER_RATE_LIMIT', 2)
    monkeypatch.setattr(dental_clinic, '_VALIDATE_RATE_LIMIT', 5)
    with dental_clinic.app.test_request_context(
            '/', environ_overrides={'REMOTE_ADDR': '203.0.113.7'}):
        # Exhaust the register bucket.
        assert dental_clinic._check_register_rate_limit() is None
        assert dental_clinic._check_register_rate_limit() is None
        blocked = dental_clinic._check_register_rate_limit()
        assert blocked is not None and blocked[1] == 429
        # validate has its OWN, separate budget — still wide open.
        for _ in range(5):
            assert dental_clinic._check_validate_rate_limit() is None
        # ...and only trips at its own (higher) limit.
        v_blocked = dental_clinic._check_validate_rate_limit()
        assert v_blocked is not None and v_blocked[1] == 429
