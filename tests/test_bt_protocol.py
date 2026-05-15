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
