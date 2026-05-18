"""Tests for the BT protocol dispatcher — pure function from (request, cursor)
to response, reusing _collect_sync_export / _apply_sync_import."""

import sqlite3
import pytest

from dental_clinic import (
    BT_PROTOCOL_VERSION,
    _bt_handle_request,
    init_database,
    DB_NAME,
)


@pytest.fixture
def cursor(tmp_path, monkeypatch):
    db = tmp_path / 'test.db'
    monkeypatch.setattr('dental_clinic.DB_NAME', str(db))
    init_database()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Seed a paired device so hello succeeds.
    cur.execute(
        'INSERT INTO paired_devices (device_id, device_name, device_token, paired_at, last_seen_at, is_active) '
        "VALUES ('test-dev', 'Test', 'good-token', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)"
    )
    conn.commit()
    yield cur
    conn.close()


def test_hello_accepts_valid_token(cursor):
    resp, authed = _bt_handle_request(cursor, {
        'op': 'hello', 'device_token': 'good-token', 'client_version': '1.0.0',
    }, authed=False)
    assert resp == {'ok': True, 'server_version': BT_PROTOCOL_VERSION}
    assert authed is True


def test_hello_rejects_bad_token(cursor):
    resp, authed = _bt_handle_request(cursor, {
        'op': 'hello', 'device_token': 'wrong-token', 'client_version': '1.0.0',
    }, authed=False)
    assert resp == {'error': 'unauthorized'}
    assert authed is False


def test_hello_rejects_missing_token(cursor):
    resp, authed = _bt_handle_request(cursor, {'op': 'hello'}, authed=False)
    assert resp == {'error': 'unauthorized'}
    assert authed is False


def test_sync_export_requires_authed(cursor):
    resp, _ = _bt_handle_request(cursor, {'op': 'sync_export'}, authed=False)
    assert resp == {'error': 'unauthorized'}


def test_sync_import_requires_authed(cursor):
    resp, _ = _bt_handle_request(cursor, {
        'op': 'sync_import', 'tables': {}, 'tombstones': [],
    }, authed=False)
    assert resp == {'error': 'unauthorized'}


def test_unknown_op_returns_error(cursor):
    resp, _ = _bt_handle_request(cursor, {'op': 'eat_lunch'}, authed=True)
    assert resp == {'error': 'unknown op'}


def test_missing_op_returns_error(cursor):
    resp, _ = _bt_handle_request(cursor, {}, authed=True)
    assert resp == {'error': 'unknown op'}


def test_sync_export_returns_tables_and_tombstones(cursor):
    resp, _ = _bt_handle_request(cursor, {'op': 'sync_export'}, authed=True)
    assert resp['ok'] is True
    assert 'tables' in resp
    assert 'tombstones' in resp
    assert 'generated_at' in resp


def test_sync_import_applies_rows(cursor):
    # Insert a patient via import
    payload = {
        'op': 'sync_import',
        'tables': {
            'patients': [{
                'id': 1, 'first_name': 'Imported', 'last_name': 'Patient',
                'phone': '555', 'updated_at': '2030-01-01T00:00:00',
                'created_at': '2030-01-01T00:00:00',
            }],
        },
        'tombstones': [],
    }
    resp, _ = _bt_handle_request(cursor, payload, authed=True)
    assert resp['ok'] is True
    assert resp['applied'] >= 1
    cursor.execute("SELECT first_name FROM patients WHERE id = 1")
    assert cursor.fetchone()['first_name'] == 'Imported'


def test_bt_pair_creates_new_paired_device(cursor):
    """op:bt_pair is unauthenticated: server issues a fresh device_token,
    inserts a paired_devices row, and the response includes the token.

    Trust model: the BT-SPP COM port the server listens on is OS-Bluetooth-
    bonded already, so anyone who can speak this protocol has the doctor's
    physical/intent approval. Per-device tokens still let the server tell
    devices apart for audit + revoke later."""
    resp, authed = _bt_handle_request(cursor, {
        'op': 'bt_pair',
        'device_id': 'mobile-abc',
        'device_name': 'Doctor phone',
        'client_version': '1.0.0',
    }, authed=False)
    assert resp['ok'] is True
    assert resp['device_token']
    assert isinstance(resp['device_token'], str)
    assert len(resp['device_token']) >= 16
    # Authed flag flips on so the same BT session can immediately do
    # sync_export / sync_import without a second hello round-trip.
    assert authed is True

    cursor.execute(
        'SELECT device_id, device_name, is_active FROM paired_devices '
        'WHERE device_token = ?', (resp['device_token'],))
    row = cursor.fetchone()
    assert row is not None
    assert row['device_id'] == 'mobile-abc'
    assert row['device_name'] == 'Doctor phone'
    assert int(row['is_active']) == 1


def test_bt_pair_reissues_token_for_same_device_id(cursor):
    """If the same device_id pairs again (e.g. mobile lost its stored token
    after a reinstall), don't proliferate paired_devices rows — rotate the
    existing row's token and return the new one."""
    first, _ = _bt_handle_request(cursor, {
        'op': 'bt_pair', 'device_id': 'mobile-abc', 'device_name': 'phone',
    }, authed=False)
    second, _ = _bt_handle_request(cursor, {
        'op': 'bt_pair', 'device_id': 'mobile-abc', 'device_name': 'phone',
    }, authed=False)
    assert first['device_token'] != second['device_token']

    cursor.execute(
        "SELECT COUNT(*) AS n FROM paired_devices WHERE device_id = 'mobile-abc'")
    assert cursor.fetchone()['n'] == 1
    # The previous token must no longer authenticate.
    resp, _ = _bt_handle_request(cursor, {
        'op': 'hello', 'device_token': first['device_token'],
    }, authed=False)
    assert resp == {'error': 'unauthorized'}


def test_bt_pair_token_is_immediately_usable(cursor):
    """A pair → hello on the same session uses the fresh token."""
    pair_resp, _ = _bt_handle_request(cursor, {
        'op': 'bt_pair', 'device_id': 'mobile-abc', 'device_name': 'phone',
    }, authed=False)
    hello_resp, authed = _bt_handle_request(cursor, {
        'op': 'hello', 'device_token': pair_resp['device_token'],
    }, authed=False)
    assert hello_resp['ok'] is True
    assert authed is True


def test_bt_pair_rejects_missing_device_id(cursor):
    resp, authed = _bt_handle_request(cursor, {
        'op': 'bt_pair', 'device_name': 'phone',
    }, authed=False)
    assert resp == {'error': 'device_id required'}
    assert authed is False


def test_sync_import_isolates_bad_rows(cursor):
    # One good row + one row with no id — the good row must still apply.
    payload = {
        'op': 'sync_import',
        'tables': {
            'patients': [
                {'id': 2, 'first_name': 'OK', 'last_name': 'X',
                 'updated_at': '2030-01-01T00:00:00'},
                {'first_name': 'Bad'},  # missing id → skipped
            ],
        },
        'tombstones': [],
    }
    resp, _ = _bt_handle_request(cursor, payload, authed=True)
    assert resp['ok'] is True
    assert resp['applied'] >= 1
    assert resp['skipped'] >= 1
