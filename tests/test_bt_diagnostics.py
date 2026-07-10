"""Tests for the BT diagnostic extras on /api/bt/status:
  - paired_devices list (sourced from the paired_devices table)
  - recent_attempts ring buffer (in-memory, capped at maxlen=20)
  - server_listening flag (set by the daemon thread)

These are diagnostic breadcrumbs exposed so the Settings UI can show the
user *why* a BT sync isn't happening, without forcing them to read logs.
"""

import sqlite3
import pytest

import dental_clinic


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / 'bt_diag.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    # Each test starts with an empty ring buffer + listener flag off so
    # assertions are deterministic.
    dental_clinic._bt_recent_attempts.clear()
    dental_clinic._bt_server_listening = False
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as c:
        c.post('/login', data={'username': 'admin', 'password': 'admin'})
        yield c


def _seed_paired_device(db_path, device_id, device_name, token='tok-xyz', active=1):
    conn = dental_clinic.get_db_connection(db_path=db_path)
    conn.execute(
        'INSERT INTO paired_devices (device_id, device_name, device_token, '
        'paired_at, last_seen_at, is_active) '
        'VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)',
        (device_id, device_name, token, active),
    )
    conn.commit()
    conn.close()


def test_status_returns_empty_diagnostics_by_default(client):
    """Fresh DB → no paired devices, no attempts, listener off."""
    data = client.get('/api/bt/status').get_json()
    assert data['paired_devices'] == []
    assert data['recent_attempts'] == []
    assert data['server_listening'] is False


def test_paired_devices_surfaces_in_status(client):
    """Inserting a paired_devices row → /api/bt/status surfaces it."""
    _seed_paired_device(dental_clinic.DB_NAME, 'dev-A', 'Reception Phone')
    data = client.get('/api/bt/status').get_json()
    assert len(data['paired_devices']) == 1
    d = data['paired_devices'][0]
    assert d['device_id'] == 'dev-A'
    assert d['device_name'] == 'Reception Phone'
    assert d['is_active'] is True
    assert d['paired_at']      # populated by CURRENT_TIMESTAMP
    assert d['last_seen_at']
    # Token must NEVER be exposed in the diagnostic payload — it's the
    # auth secret. (Schema has device_token; response should not.)
    assert 'device_token' not in d


def test_recent_attempts_records_pair_and_hello(client):
    """A successful bt_pair + hello should each leave a breadcrumb with the
    right op/outcome, newest-first."""
    # Drive the dispatcher directly — no socket needed.
    conn = dental_clinic.get_db_connection(with_row_factory=True)
    cur = conn.cursor()
    resp, authed = dental_clinic._bt_handle_request(
        cur, {'op': 'bt_pair', 'device_id': 'dev-Z', 'device_name': 'Phone Z'},
        authed=False,
    )
    assert resp['ok'] is True
    token = resp['device_token']
    conn.commit()
    # Now a hello with the fresh token.
    resp2, authed2 = dental_clinic._bt_handle_request(
        cur, {'op': 'hello', 'device_token': token}, authed=False,
    )
    assert resp2['ok'] is True
    conn.commit()
    conn.close()

    data = client.get('/api/bt/status').get_json()
    attempts = data['recent_attempts']
    # Newest first → hello, then bt_pair.
    assert len(attempts) == 2
    assert attempts[0]['op'] == 'hello'
    assert attempts[0]['outcome'] == 'ok'
    assert attempts[0]['device_id'] == 'dev-Z'
    assert attempts[1]['op'] == 'bt_pair'
    assert attempts[1]['outcome'] == 'ok'


def test_recent_attempts_records_unauthorized_hello(client):
    """A bad-token hello must leave an 'unauthorized' breadcrumb so the
    user can see the connection attempt in the UI."""
    conn = dental_clinic.get_db_connection(with_row_factory=True)
    cur = conn.cursor()
    resp, _ = dental_clinic._bt_handle_request(
        cur, {'op': 'hello', 'device_token': 'not-a-real-token'}, authed=False,
    )
    assert resp == {'error': 'unauthorized'}
    conn.close()

    data = client.get('/api/bt/status').get_json()
    assert len(data['recent_attempts']) == 1
    a = data['recent_attempts'][0]
    assert a['op'] == 'hello'
    assert a['outcome'] == 'unauthorized'
    assert a['detail']  # non-empty failure detail


def test_recent_attempts_is_bounded_to_maxlen_20(client):
    """The ring buffer caps at 20 entries; /api/bt/status returns the last
    10 so the UI stays compact even under heavy churn."""
    # Hammer the dispatcher with 30 unauthorized hellos.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    for _i in range(30):
        dental_clinic._bt_handle_request(
            cur, {'op': 'hello', 'device_token': 'bad'}, authed=False,
        )
    conn.close()

    # Underlying deque capped at 20 — that's the invariant we care about
    # most (memory bound). The endpoint returns the most recent 10.
    assert len(dental_clinic._bt_recent_attempts) == 20

    data = client.get('/api/bt/status').get_json()
    assert len(data['recent_attempts']) == 10
    # Every entry should be the 'hello' / 'unauthorized' case we drove.
    assert all(a['op'] == 'hello' for a in data['recent_attempts'])
    assert all(a['outcome'] == 'unauthorized' for a in data['recent_attempts'])


def test_server_listening_flag_round_trip(client):
    """The status response mirrors the module-level _bt_server_listening
    flag so the UI's listener indicator reflects daemon state."""
    dental_clinic._bt_server_listening = True
    try:
        assert client.get('/api/bt/status').get_json()['server_listening'] is True
    finally:
        dental_clinic._bt_server_listening = False
    assert client.get('/api/bt/status').get_json()['server_listening'] is False
