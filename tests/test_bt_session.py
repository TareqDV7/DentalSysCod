"""Tests for the BT session driver — feeds frames in via one BytesIO and
collects responses from another."""

import io
import sqlite3
import pytest

from dental_clinic import (
    encode_bt_frame, decode_bt_frame,
    _bt_serve_session, init_database,
)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    db = tmp_path / 'sess.db'
    monkeypatch.setattr('dental_clinic.DB_NAME', str(db))
    init_database()
    conn = sqlite3.connect(str(db))
    conn.execute(
        'INSERT INTO paired_devices (device_id, device_name, device_token, paired_at, last_seen_at, is_active) '
        "VALUES ('test-dev', 'Test', 'good-token', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)"
    )
    conn.commit()
    conn.close()
    return str(db)


def _drive(db_path, requests):
    """Pipe requests into the session driver, return the list of responses."""
    inbuf = io.BytesIO(b''.join(encode_bt_frame(r) for r in requests))
    outbuf = io.BytesIO()
    _bt_serve_session(inbuf, outbuf, db_path)
    outbuf.seek(0)
    out = []
    while True:
        try:
            out.append(decode_bt_frame(outbuf))
        except EOFError:
            break
    return out


def test_full_round_trip(db_path):
    resps = _drive(db_path, [
        {'op': 'hello', 'device_token': 'good-token'},
        {'op': 'sync_export'},
        {'op': 'sync_import', 'tables': {}, 'tombstones': []},
    ])
    assert resps[0] == {'ok': True, 'server_version': '1.0.0'}
    assert resps[1]['ok'] is True
    assert 'tables' in resps[1]
    assert resps[2] == {'ok': True, 'applied': 0, 'skipped': 0}


def test_bad_token_closes_after_hello(db_path):
    resps = _drive(db_path, [
        {'op': 'hello', 'device_token': 'wrong'},
        {'op': 'sync_export'},   # should never be processed
    ])
    assert resps == [{'error': 'unauthorized'}]


def test_export_before_hello_is_unauthorized_and_closes(db_path):
    resps = _drive(db_path, [{'op': 'sync_export'}, {'op': 'sync_export'}])
    assert resps == [{'error': 'unauthorized'}]


def test_malformed_frame_closes_session(db_path):
    # Hand-craft: valid hello, then a length-prefix with garbage JSON.
    good = encode_bt_frame({'op': 'hello', 'device_token': 'good-token'})
    garbage_body = b'{not json'
    garbage = len(garbage_body).to_bytes(4, 'big') + garbage_body
    inbuf = io.BytesIO(good + garbage)
    outbuf = io.BytesIO()
    _bt_serve_session(inbuf, outbuf, db_path)
    outbuf.seek(0)
    resps = []
    while True:
        try:
            resps.append(decode_bt_frame(outbuf))
        except EOFError:
            break
    assert resps[0] == {'ok': True, 'server_version': '1.0.0'}
    assert resps[1] == {'error': 'malformed frame'}
