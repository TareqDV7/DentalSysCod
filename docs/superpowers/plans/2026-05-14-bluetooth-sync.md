# Phase 4 — Bluetooth sync implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** add classic BT-SPP as an automatic fallback transport between the Flutter mobile app and the Windows desktop `dental_clinic.py` server, replacing the existing BLE stub.

**Architecture:** desktop runs a daemon thread that listens on a Windows-assigned BT-SPP COM port via `pyserial` and dispatches framed JSON requests (`hello`/`sync_export`/`sync_import`) to the existing `_collect_sync_export` / `_apply_sync_import` helpers. The phone runs an Android foreground service that auto-reconnects every 30 s when LAN+cloud are unreachable. Wire protocol is length-prefixed JSON (4-byte big-endian length + UTF-8 payload, 4 MB cap). Full design: `docs/superpowers/specs/2026-05-14-bluetooth-sync-design.md`.

**Tech stack:**
- Backend: Python 3.10+, Flask, SQLite (WAL), `pyserial>=3.5`, `threading`.
- Frontend: Flutter 3.x, `flutter_bluetooth_serial`, `flutter_background_service`, `flutter_secure_storage`, `sqflite`.
- Tests: `pytest` (116 baseline, target +18) and `flutter test`.

**Branch:** all work lands on a feature branch `feat/bluetooth-sync` cut from `backup/ui-backup-20260506-135130` (current branch, 4 ahead of origin). The branch is created in Task 0 and merged back via fast-forward at the end.

**File map:**
- Backend (all in `dental_clinic.py` unless noted):
  - new helpers: `encode_bt_frame`, `decode_bt_frame`, `_bt_handle_request`, `_bt_serve_session`, `bt_sync_server`
  - new endpoints: `GET /api/bt/status`, `POST /api/bt/configure`
  - new web-portal HTML/JS card under Settings
  - `requirements.txt`: add `pyserial>=3.5`
  - `DentalClinicApp.spec`: add `pyserial` + `serial.tools.list_ports` to `hiddenimports`
  - `README.md`: new "Bluetooth sync" subsection
- Frontend (`clinic_mobile_app/`):
  - new file: `lib/services/bluetooth_frame_codec.dart` (pure codec)
  - new file: `lib/services/bt_session_client.dart` (protocol-over-stream)
  - **rewrite**: `lib/services/bluetooth_sync_service.dart`
  - **modify**: `lib/services/connectivity_sync_service.dart` (fallback gating)
  - **modify**: `lib/services/local_storage_service.dart` (BT fields)
  - **modify**: `lib/state/app_state.dart` (wire BT service)
  - **modify**: `lib/screens/settings_screen.dart` (new BT card)
  - **modify**: `lib/widgets/sync_status_bar.dart` (Bluetooth link label)
  - `pubspec.yaml`: swap deps
  - `android/app/src/main/AndroidManifest.xml`: foreground-service declaration, `POST_NOTIFICATIONS`, `FOREGROUND_SERVICE`
- Tests:
  - `tests/test_bt_codec.py`
  - `tests/test_bt_protocol.py`
  - `tests/test_bt_session.py`
  - `tests/test_bt_endpoints.py`
  - `tests/test_bt_worker.py`
  - `clinic_mobile_app/test/bluetooth_frame_codec_test.dart`
  - `clinic_mobile_app/test/bt_session_client_test.dart`
  - `clinic_mobile_app/test/bluetooth_sync_service_test.dart`

---

## Task 0: Create feature branch

**Files:** none (git only).

- [ ] **Step 1: Cut the branch from current HEAD**

Run:
```bash
git checkout -b feat/bluetooth-sync
git status
```

Expected: `On branch feat/bluetooth-sync`, working tree clean.

- [ ] **Step 2: Confirm baseline tests pass**

Run: `python -m pytest tests/ -q`
Expected: `116 passed`. No new failures before any code is written.

---

## Task 1: Backend frame codec

**Files:**
- Modify: `dental_clinic.py` (append new functions near `_cloud_http_request` ~ line 10712)
- Create: `tests/test_bt_codec.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_bt_codec.py`:

```python
"""Frame codec for the Bluetooth-SPP wire protocol.

Each frame is a 4-byte big-endian unsigned length, then a UTF-8 JSON payload.
Frames larger than 4 MB are rejected. Truncated streams raise EOFError.
"""

import io
import json
import pytest

from dental_clinic import encode_bt_frame, decode_bt_frame, BT_MAX_FRAME_BYTES


def test_encode_decode_round_trip():
    payload = {'op': 'hello', 'device_token': 'abc', 'client_version': '1.0.0'}
    framed = encode_bt_frame(payload)
    stream = io.BytesIO(framed)
    assert decode_bt_frame(stream) == payload


def test_encode_uses_4_byte_big_endian_length_prefix():
    payload = {'op': 'ping'}
    framed = encode_bt_frame(payload)
    body = json.dumps(payload).encode('utf-8')
    assert len(framed) == 4 + len(body)
    assert int.from_bytes(framed[:4], 'big') == len(body)
    assert framed[4:] == body


def test_decode_rejects_oversized_frame():
    huge_len = (BT_MAX_FRAME_BYTES + 1).to_bytes(4, 'big')
    stream = io.BytesIO(huge_len + b'{}')
    with pytest.raises(ValueError, match='frame too large'):
        decode_bt_frame(stream)


def test_decode_raises_eof_on_empty_stream():
    with pytest.raises(EOFError):
        decode_bt_frame(io.BytesIO(b''))


def test_decode_raises_eof_on_truncated_body():
    # Length header says 10 bytes, body has only 3.
    stream = io.BytesIO((10).to_bytes(4, 'big') + b'abc')
    with pytest.raises(EOFError):
        decode_bt_frame(stream)


def test_decode_rejects_malformed_json():
    body = b'{not json'
    stream = io.BytesIO(len(body).to_bytes(4, 'big') + body)
    with pytest.raises(ValueError, match='malformed JSON'):
        decode_bt_frame(stream)


def test_encode_handles_unicode_payload():
    payload = {'clinic_name': 'عيادة الأسنان', 'note': '中文'}
    framed = encode_bt_frame(payload)
    assert decode_bt_frame(io.BytesIO(framed)) == payload
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `python -m pytest tests/test_bt_codec.py -v`
Expected: ImportError on `encode_bt_frame` / `decode_bt_frame` / `BT_MAX_FRAME_BYTES`.

- [ ] **Step 3: Implement the codec**

Edit `dental_clinic.py`. Find the line `def _cloud_http_request(method, url, headers=None, body=None, timeout=15):` (~line 10712) and insert the following **above** it:

```python
# ── Bluetooth-SPP wire protocol ─────────────────────────────────────────────
# Frames are 4-byte big-endian unsigned length + UTF-8 JSON payload. The cap
# guards against a peer claiming a 4 GB frame; real deltas are a few KB.
BT_MAX_FRAME_BYTES = 4 * 1024 * 1024  # 4 MB


def encode_bt_frame(payload):
    """Encode a JSON-serialisable dict into a length-prefixed BT frame."""
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    if len(body) > BT_MAX_FRAME_BYTES:
        raise ValueError(f'frame too large: {len(body)} > {BT_MAX_FRAME_BYTES}')
    return len(body).to_bytes(4, 'big') + body


def _read_exactly(stream, n):
    """Read exactly n bytes from a stream, or raise EOFError."""
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError(f'stream closed after {n - remaining} of {n} bytes')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def decode_bt_frame(stream):
    """Read one length-prefixed BT frame from a binary stream and return the
    decoded JSON dict. Raises EOFError on truncation, ValueError on malformed
    JSON or an oversized frame."""
    header = _read_exactly(stream, 4)
    length = int.from_bytes(header, 'big')
    if length > BT_MAX_FRAME_BYTES:
        raise ValueError(f'frame too large: {length} > {BT_MAX_FRAME_BYTES}')
    body = _read_exactly(stream, length)
    try:
        return json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f'malformed JSON: {exc}') from exc
```

- [ ] **Step 4: Run the tests, confirm pass**

Run: `python -m pytest tests/test_bt_codec.py -v`
Expected: 7 passed.

- [ ] **Step 5: Run the full suite to verify no regression**

Run: `python -m pytest tests/ -q`
Expected: `123 passed` (116 baseline + 7 new).

- [ ] **Step 6: Commit**

```bash
git add tests/test_bt_codec.py dental_clinic.py
git commit -m "feat(bt): length-prefixed JSON frame codec for BT-SPP wire protocol"
```

---

## Task 2: Backend protocol dispatcher

**Files:**
- Modify: `dental_clinic.py` (append after the codec from Task 1)
- Create: `tests/test_bt_protocol.py`

The dispatcher is a **pure function**: takes a parsed request dict + a cursor + an "authenticated" flag, returns a response dict. No I/O, no threading — easy to test.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bt_protocol.py`:

```python
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
```

- [ ] **Step 2: Confirm the tests fail**

Run: `python -m pytest tests/test_bt_protocol.py -v`
Expected: ImportError on `_bt_handle_request` / `BT_PROTOCOL_VERSION`.

- [ ] **Step 3: Implement the dispatcher**

In `dental_clinic.py`, **after** the codec functions added in Task 1, append:

```python
BT_PROTOCOL_VERSION = '1.0.0'


def _bt_lookup_device_by_token(cursor, token):
    """Return the device row for a token, or None. Mirrors the auth lookup
    in get_authenticated_device but without using request context."""
    if not token:
        return None
    cursor.execute(
        'SELECT device_id, device_name, is_active FROM paired_devices WHERE device_token = ?',
        (token,),
    )
    row = cursor.fetchone()
    if not row or int(row['is_active']) != 1:
        return None
    cursor.execute(
        'UPDATE paired_devices SET last_seen_at = CURRENT_TIMESTAMP WHERE device_id = ?',
        (row['device_id'],),
    )
    return {'device_id': row['device_id'], 'device_name': row['device_name']}


def _bt_handle_request(cursor, req, authed):
    """Dispatch one BT request. Returns (response_dict, new_authed_flag).
    Pure function — no I/O, no threading."""
    op = req.get('op')
    if op == 'hello':
        device = _bt_lookup_device_by_token(cursor, req.get('device_token'))
        if device is None:
            return {'error': 'unauthorized'}, False
        return {'ok': True, 'server_version': BT_PROTOCOL_VERSION}, True

    if not authed:
        return {'error': 'unauthorized'}, authed

    if op == 'sync_export':
        since_raw = req.get('since')
        since_dt = parse_timestamp_for_sync(since_raw) if since_raw else None
        tables, tombstones, _total = _collect_sync_export(cursor, since_dt)
        return {
            'ok': True,
            'tables': tables,
            'tombstones': tombstones,
            'generated_at': _naive_utc_now().isoformat(),
        }, authed

    if op == 'sync_import':
        applied, skipped, _tombs_applied, _by_table = _apply_sync_import(cursor, req)
        return {'ok': True, 'applied': applied, 'skipped': skipped}, authed

    return {'error': 'unknown op'}, authed
```

- [ ] **Step 4: Run the tests, confirm pass**

Run: `python -m pytest tests/test_bt_protocol.py -v`
Expected: 10 passed.

- [ ] **Step 5: Full suite**

Run: `python -m pytest tests/ -q`
Expected: `133 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_bt_protocol.py dental_clinic.py
git commit -m "feat(bt): protocol dispatcher (hello/sync_export/sync_import)"
```

---

## Task 3: Backend session driver

The driver reads frames from one binary stream, dispatches via the Task-2 function, writes responses to another stream. Persistent `authed` flag across the session.

**Files:**
- Modify: `dental_clinic.py` (append after Task 2 functions)
- Create: `tests/test_bt_session.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bt_session.py`:

```python
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
```

- [ ] **Step 2: Confirm fail**

Run: `python -m pytest tests/test_bt_session.py -v`
Expected: ImportError on `_bt_serve_session`.

- [ ] **Step 3: Implement the session driver**

In `dental_clinic.py`, **after** the dispatcher from Task 2, append:

```python
def _bt_serve_session(stream_in, stream_out, db_path=None):
    """Drive one BT session: read frames, dispatch, write responses, exit
    when the peer disconnects or sends a malformed frame. Closes on the
    first unauthorized response (auth failure) or fatal protocol error.

    Opens its own short-lived SQLite connection so the caller (the BT
    server thread) doesn't have to manage one. `db_path` defaults to
    DB_NAME — exposed for tests."""
    conn = sqlite3.connect(db_path or DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    authed = False
    try:
        while True:
            try:
                req = decode_bt_frame(stream_in)
            except EOFError:
                return
            except ValueError:
                try:
                    stream_out.write(encode_bt_frame({'error': 'malformed frame'}))
                    stream_out.flush()
                except Exception:
                    pass
                return
            resp, authed = _bt_handle_request(cursor, req, authed)
            try:
                stream_out.write(encode_bt_frame(resp))
                stream_out.flush()
            except Exception:
                return
            conn.commit()
            if 'error' in resp and resp['error'] == 'unauthorized':
                return
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_bt_session.py -v`
Expected: 4 passed.

- [ ] **Step 5: Full suite**

Run: `python -m pytest tests/ -q`
Expected: `137 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_bt_session.py dental_clinic.py
git commit -m "feat(bt): session driver — frames in, dispatch, responses out"
```

---

## Task 4: Backend `/api/bt/status` + `/api/bt/configure` endpoints

**Files:**
- Modify: `dental_clinic.py` (`requirements.txt` too)
- Create: `tests/test_bt_endpoints.py`

- [ ] **Step 1: Add pyserial to requirements**

Edit `requirements.txt` — add the line `pyserial>=3.5` (alphabetical position fine, otherwise append):

```
Flask>=3.0.0
Flask-CORS>=4.0.0
pyserial>=3.5
waitress>=2.1.2
```

- [ ] **Step 2: Install locally**

Run: `python -m pip install -r requirements.txt`
Expected: `pyserial-3.5+` installed. Verify with `python -c "import serial; print(serial.__version__)"`.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_bt_endpoints.py`:

```python
"""Tests for the BT settings endpoints (/api/bt/status, /api/bt/configure)."""

import json
import pytest

import dental_clinic


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / 'bt_ep.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as c:
        # Log in as the seeded admin so the endpoints are reachable.
        c.post('/login', data={'username': 'admin', 'password': 'admin'})
        yield c


def test_status_returns_defaults_when_unconfigured(client):
    r = client.get('/api/bt/status')
    assert r.status_code == 200
    data = r.get_json()
    assert data['enabled'] is False
    assert data['com_port'] == ''
    assert 'available_ports' in data
    assert isinstance(data['available_ports'], list)


def test_configure_persists_settings(client):
    r = client.post('/api/bt/configure', json={'enabled': True, 'com_port': 'COM7'})
    assert r.status_code == 200
    assert r.get_json()['ok'] is True
    status = client.get('/api/bt/status').get_json()
    assert status['enabled'] is True
    assert status['com_port'] == 'COM7'


def test_configure_rejects_invalid_payload(client):
    r = client.post('/api/bt/configure', json={'enabled': 'yes', 'com_port': 9})
    assert r.status_code == 400


def test_endpoints_require_login(tmp_path, monkeypatch):
    db = tmp_path / 'bt_ep2.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        r = c.get('/api/bt/status')
        assert r.status_code in (302, 401)


def test_endpoints_disabled_on_cloud_node(tmp_path, monkeypatch):
    db = tmp_path / 'bt_ep3.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        r = c.get('/api/bt/status')
        assert r.status_code == 400  # disabled on cloud
```

- [ ] **Step 4: Confirm fail**

Run: `python -m pytest tests/test_bt_endpoints.py -v`
Expected: 404s from missing endpoints.

- [ ] **Step 5: Implement the endpoints**

In `dental_clinic.py`, find the `/api/cloud/unpair` route (search for `def cloud_unpair`). Add **after** it (or beside other cloud routes — they sit near each other):

```python
def _bt_list_serial_ports():
    """Return COM port entries that look like Bluetooth SPP ports."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = []
    for p in list_ports.comports():
        desc = (p.description or '').lower()
        if 'bluetooth' in desc or 'standard serial over bluetooth' in desc:
            ports.append({'device': p.device, 'description': p.description})
    return ports


@app.route('/api/bt/status', methods=['GET'])
@login_required
def bt_status():
    if CLOUD_MODE:
        return jsonify({'error': 'Bluetooth sync is local-server only'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    enabled = read_app_setting(cur, 'bt_sync_enabled', '0') == '1'
    com_port = read_app_setting(cur, 'bt_sync_com_port', '') or ''
    last_sync_at = read_app_setting(cur, 'bt_last_sync_at', '') or ''
    last_error = read_app_setting(cur, 'bt_last_error', '') or ''
    conn.close()
    return jsonify({
        'enabled': enabled,
        'com_port': com_port,
        'last_sync_at': last_sync_at,
        'last_error': last_error,
        'available_ports': _bt_list_serial_ports(),
    })


@app.route('/api/bt/configure', methods=['POST'])
@login_required
def bt_configure():
    if CLOUD_MODE:
        return jsonify({'error': 'Bluetooth sync is local-server only'}), 400
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    com_port = data.get('com_port')
    if not isinstance(enabled, bool) or not isinstance(com_port, str):
        return jsonify({'error': 'enabled (bool) and com_port (str) required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    write_app_setting(cur, 'bt_sync_enabled', '1' if enabled else '0')
    write_app_setting(cur, 'bt_sync_com_port', com_port.strip())
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_bt_endpoints.py -v`
Expected: 5 passed.

- [ ] **Step 7: Full suite**

Run: `python -m pytest tests/ -q`
Expected: `142 passed`.

- [ ] **Step 8: Commit**

```bash
git add tests/test_bt_endpoints.py dental_clinic.py requirements.txt
git commit -m "feat(bt): /api/bt/status + /api/bt/configure endpoints"
```

---

## Task 5: Backend BT server thread

**Files:**
- Modify: `dental_clinic.py`
- Create: `tests/test_bt_worker.py`

The thread is hard to test fully without a real BT radio. We make the **port-opener swappable** (injected callable that returns a stream pair) and unit-test the loop's settings-re-read + back-off behavior.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bt_worker.py`:

```python
"""Tests for the BT server thread's loop logic — settings re-read, back-off.
The real pyserial open is swapped for a fake that returns BytesIO pairs."""

import io
import threading
import time
import pytest

import dental_clinic


class _FakePort:
    """Pretends to be a serial.Serial: exposes .read/.write/.flush/.close and
    supports the context-manager protocol. Drained from a pre-filled buffer."""

    def __init__(self, inbytes):
        self._in = io.BytesIO(inbytes)
        self.out = io.BytesIO()
        self.closed = False

    def read(self, n=1):
        return self._in.read(n)

    def write(self, b):
        return self.out.write(b)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_loop_calls_session_when_enabled(tmp_path, monkeypatch):
    db = tmp_path / 'w.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    dental_clinic.write_app_setting(cur, 'bt_sync_enabled', '1')
    dental_clinic.write_app_setting(cur, 'bt_sync_com_port', 'COMTEST')
    conn.commit()
    conn.close()

    fake = _FakePort(dental_clinic.encode_bt_frame({'op': 'hello', 'device_token': 'x'}))

    opens = []
    def fake_open(port, **kwargs):
        opens.append(port)
        return fake

    stop = threading.Event()
    monkeypatch.setattr(dental_clinic, '_bt_open_port', fake_open)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_SLEEP', 0.01)  # speed up for tests

    t = threading.Thread(target=dental_clinic.bt_sync_server,
                         kwargs={'stop_event': stop}, daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2.0)

    assert opens == ['COMTEST']
    # Fake port should have received an "unauthorized" framed response.
    assert fake.out.getvalue().endswith(
        dental_clinic.encode_bt_frame({'error': 'unauthorized'})[-len(b'unauthorized') - 10:][-30:]
    ) or b'unauthorized' in fake.out.getvalue()


def test_loop_idles_when_disabled(tmp_path, monkeypatch):
    db = tmp_path / 'w2.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()

    opens = []
    monkeypatch.setattr(dental_clinic, '_bt_open_port',
                        lambda port, **kw: opens.append(port) or _FakePort(b''))
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_SLEEP', 0.01)

    stop = threading.Event()
    t = threading.Thread(target=dental_clinic.bt_sync_server,
                         kwargs={'stop_event': stop}, daemon=True)
    t.start()
    time.sleep(0.15)
    stop.set()
    t.join(timeout=2.0)

    # Setting is disabled → port never opened.
    assert opens == []


def test_loop_recovers_after_open_failure(tmp_path, monkeypatch):
    db = tmp_path / 'w3.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    dental_clinic.write_app_setting(cur, 'bt_sync_enabled', '1')
    dental_clinic.write_app_setting(cur, 'bt_sync_com_port', 'COMTEST')
    conn.commit()
    conn.close()

    import serial as pyserial
    calls = {'n': 0}

    def flaky_open(port, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise pyserial.SerialException('port busy')
        return _FakePort(b'')   # second call succeeds, immediate EOF

    monkeypatch.setattr(dental_clinic, '_bt_open_port', flaky_open)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_SLEEP', 0.01)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_ERROR_SLEEP', 0.01)

    stop = threading.Event()
    t = threading.Thread(target=dental_clinic.bt_sync_server,
                         kwargs={'stop_event': stop}, daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2.0)

    assert calls['n'] >= 2  # tried again after the SerialException
```

- [ ] **Step 2: Confirm fail**

Run: `python -m pytest tests/test_bt_worker.py -v`
Expected: AttributeError on `bt_sync_server` / `_bt_open_port`.

- [ ] **Step 3: Implement the worker**

In `dental_clinic.py`, **after** `_bt_serve_session` from Task 3, append:

```python
# How long the BT worker idles when disabled or after an error.
_BT_LOOP_SLEEP = 30.0
_BT_LOOP_ERROR_SLEEP = 15.0


def _bt_open_port(port, baudrate=115200, timeout=1.0):
    """Open a pyserial port. Indirection so tests can swap this."""
    import serial as _pyserial
    return _pyserial.Serial(port, baudrate=baudrate, timeout=timeout)


def bt_sync_server(stop_event=None):
    """Daemon loop: re-read settings every cycle, accept one peer at a time
    on the configured COM port. Skipped on the cloud node and in debug mode
    (the parent process gates startup)."""
    import serial as _pyserial
    while stop_event is None or not stop_event.is_set():
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            enabled = read_app_setting(cur, 'bt_sync_enabled', '0') == '1'
            port = (read_app_setting(cur, 'bt_sync_com_port', '') or '').strip()
            conn.close()
        except sqlite3.Error:
            enabled, port = False, ''
        if not enabled or not port:
            _bt_sleep(_BT_LOOP_SLEEP, stop_event)
            continue
        try:
            ser = _bt_open_port(port)
            with ser:
                _bt_serve_session(ser, ser)
            _bt_record_success()
        except _pyserial.SerialException as exc:
            _bt_record_error(f'serial: {exc}')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)
        except Exception as exc:  # noqa: BLE001
            _bt_record_error(f'{type(exc).__name__}: {exc}')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)


def _bt_sleep(seconds, stop_event):
    """Sleep up to `seconds`, waking early if stop_event fires."""
    if stop_event is None:
        time.sleep(seconds)
        return
    stop_event.wait(timeout=seconds)


def _bt_record_success():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        write_app_setting(cur, 'bt_last_sync_at', _naive_utc_now().isoformat())
        write_app_setting(cur, 'bt_last_error', '')
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def _bt_record_error(message):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        write_app_setting(cur, 'bt_last_error', message[:300])
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass
```

Then wire startup. Find the block near the end of `dental_clinic.py` that starts `cloud_sync_worker` (~line 10858 — `threading.Thread(target=cloud_sync_worker, daemon=True).start()`). **Add immediately after** that line:

```python
    # Background Bluetooth-SPP server (local clinic server only — production runs).
    bt_sync_on = (not CLOUD_MODE) and (not debug_mode)
    if bt_sync_on:
        threading.Thread(target=bt_sync_server, daemon=True).start()
```

And in the print block lower down (search for `if cloud_sync_on:` print line), **add after** the cloud-sync prints:

```python
    if bt_sync_on:
        print('📡 Bluetooth sync ready (configure in Settings → Bluetooth Sync)')
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_bt_worker.py -v`
Expected: 3 passed.

- [ ] **Step 5: Full suite + compile check**

Run:
```bash
python -m py_compile dental_clinic.py
python -m pytest tests/ -q
```
Expected: clean compile; `145 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_bt_worker.py dental_clinic.py
git commit -m "feat(bt): server thread — listens on Windows-assigned BT COM port"
```

---

## Task 6: Backend PyInstaller hidden imports

**Files:**
- Modify: `DentalClinicApp.spec`

- [ ] **Step 1: Find the existing `hiddenimports` block**

Run: `grep -n hiddenimports DentalClinicApp.spec`
Expected: one match showing the existing list.

- [ ] **Step 2: Add pyserial entries**

Open `DentalClinicApp.spec`. Find the `hiddenimports` list (it currently includes `waitress`, `markupsafe`, `werkzeug.security`, etc.). Add `'serial'` and `'serial.tools.list_ports'` to the list.

Example diff:
```python
hiddenimports=[
    'waitress',
    'markupsafe',
    'werkzeug.security',
    'serial',
    'serial.tools.list_ports',
],
```

- [ ] **Step 3: Verify the spec still parses (no full build needed)**

Run: `python -c "import ast; ast.parse(open('DentalClinicApp.spec').read()); print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add DentalClinicApp.spec
git commit -m "build: include pyserial in DentaCare.exe hiddenimports"
```

---

## Task 7: Backend Settings → Bluetooth Sync UI card

**Files:**
- Modify: `dental_clinic.py` (the giant HTML/JS template inside it)

This is a UI-only change; manual smoke verifies it. Match the existing pattern used by the "Cloud Sync" card.

- [ ] **Step 1: Locate the existing Cloud Sync card markup**

Run: `grep -n "Cloud Sync\|cloud-sync-section\|loadCloudSyncSettings" dental_clinic.py | head -10`
Note the line numbers — the new card goes immediately after the Cloud Sync card's closing `</div>` so it appears next in Settings.

- [ ] **Step 2: Add the card HTML**

Insert this block **after** the Cloud Sync card closing `</div>` in the Settings template:

```html
<div class="settings-card" id="bt-sync-card">
  <h3 data-en="Bluetooth Sync" data-ar="مزامنة عبر بلوتوث">Bluetooth Sync</h3>
  <p class="hint"
     data-en="Pair the clinic PC with a phone in Windows Bluetooth Settings, then pick the assigned COM port below. The phone will sync automatically over Bluetooth when Wi-Fi and cloud are unreachable."
     data-ar="قم بإقران الجهاز اللوحي مع كمبيوتر العيادة من إعدادات بلوتوث ويندوز، ثم اختر منفذ COM المخصّص.">
  </p>
  <label>
    <input type="checkbox" id="bt-enabled"/>
    <span data-en="Enable Bluetooth Sync" data-ar="تفعيل مزامنة بلوتوث">Enable Bluetooth Sync</span>
  </label>
  <label>
    <span data-en="COM port" data-ar="منفذ COM">COM port:</span>
    <select id="bt-com-port"></select>
  </label>
  <div class="bt-actions">
    <button id="bt-save-btn" data-en="Save" data-ar="حفظ">Save</button>
    <button id="bt-open-windows-btn" type="button"
            data-en="Pair a phone (Windows BT settings)"
            data-ar="إقران الجهاز (إعدادات بلوتوث ويندوز)">
      Pair a phone (Windows BT settings)
    </button>
  </div>
  <div id="bt-status-line" class="bt-status"></div>
</div>
```

- [ ] **Step 3: Add the card JS**

Find the JS block where `loadCloudSyncSettings` is defined. Add a sibling function next to it:

```javascript
async function loadBluetoothSyncSettings() {
  try {
    const r = await fetch('/api/bt/status', {credentials: 'same-origin'});
    if (!r.ok) { document.getElementById('bt-sync-card').style.display = 'none'; return; }
    const s = await r.json();
    document.getElementById('bt-enabled').checked = !!s.enabled;
    const sel = document.getElementById('bt-com-port');
    sel.innerHTML = '';
    const opt0 = document.createElement('option');
    opt0.value = ''; opt0.textContent = '— pick a port —';
    sel.appendChild(opt0);
    for (const p of (s.available_ports || [])) {
      const o = document.createElement('option');
      o.value = p.device; o.textContent = `${p.device} (${p.description})`;
      if (p.device === s.com_port) o.selected = true;
      sel.appendChild(o);
    }
    if (s.com_port && !Array.from(sel.options).some(o => o.value === s.com_port)) {
      const o = document.createElement('option');
      o.value = s.com_port; o.textContent = `${s.com_port} (not currently present)`;
      o.selected = true;
      sel.appendChild(o);
    }
    let line = '';
    if (!s.enabled) line = (currentLang === 'ar' ? 'متوقّفة' : 'Disabled');
    else if (!s.com_port) line = (currentLang === 'ar' ? 'لم يُختر منفذ' : 'No port selected');
    else if (s.last_error) line = `⚠️ ${s.last_error}`;
    else if (s.last_sync_at) line = (currentLang === 'ar' ? 'آخر مزامنة: ' : 'Last sync: ') + s.last_sync_at;
    else line = (currentLang === 'ar' ? 'في الانتظار…' : 'Waiting for a phone…');
    document.getElementById('bt-status-line').textContent = line;
  } catch (_) {
    document.getElementById('bt-sync-card').style.display = 'none';
  }
}

async function saveBluetoothSyncSettings() {
  const enabled = document.getElementById('bt-enabled').checked;
  const com_port = document.getElementById('bt-com-port').value || '';
  const r = await fetch('/api/bt/configure', {
    method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled, com_port}),
  });
  if (!r.ok) { alert(currentLang === 'ar' ? 'فشل الحفظ' : 'Save failed'); return; }
  await loadBluetoothSyncSettings();
}

function bindBluetoothSyncControls() {
  const saveBtn = document.getElementById('bt-save-btn');
  if (saveBtn) saveBtn.onclick = saveBluetoothSyncSettings;
  const winBtn = document.getElementById('bt-open-windows-btn');
  if (winBtn) winBtn.onclick = () => { window.location.href = 'ms-settings:bluetooth'; };
}
```

- [ ] **Step 4: Hook into Settings load**

Find the `loadSupportSection` function (search `function loadSupportSection`). Inside its body, find the call to `loadCloudSyncSettings();` and add **on the line below**:

```javascript
  loadBluetoothSyncSettings();
  bindBluetoothSyncControls();
```

- [ ] **Step 5: Smoke-run the dev server and visually check the Settings page**

Run: `python dental_clinic.py` (in a separate terminal).
Open http://localhost:5000 → log in → Settings. The Bluetooth Sync card should render below Cloud Sync, with the COM port dropdown populated (possibly empty if no BT serial ports on this machine — that's expected).

Save with no port selected → status line shows "No port selected". Stop the dev server.

- [ ] **Step 6: Compile check**

Run: `python -m py_compile dental_clinic.py`
Expected: clean.

- [ ] **Step 7: Full pytest suite (regression check)**

Run: `python -m pytest tests/ -q`
Expected: `145 passed` (no new tests, no regressions).

- [ ] **Step 8: Commit**

```bash
git add dental_clinic.py
git commit -m "feat(bt): Settings → Bluetooth Sync card on the web portal"
```

---

## Task 8: Flutter frame codec

**Files:**
- Create: `clinic_mobile_app/lib/services/bluetooth_frame_codec.dart`
- Create: `clinic_mobile_app/test/bluetooth_frame_codec_test.dart`

- [ ] **Step 1: Write the failing tests**

Create `clinic_mobile_app/test/bluetooth_frame_codec_test.dart`:

```dart
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/bluetooth_frame_codec.dart';

void main() {
  group('BluetoothFrameCodec', () {
    test('round trip', () {
      final payload = {'op': 'hello', 'device_token': 'abc'};
      final framed = BluetoothFrameCodec.encode(payload);
      final reader = FrameReader();
      reader.addBytes(framed);
      expect(reader.next(), payload);
    });

    test('4-byte big-endian length prefix', () {
      final framed = BluetoothFrameCodec.encode({'op': 'ping'});
      final body = utf8.encode(jsonEncode({'op': 'ping'}));
      expect(framed.length, 4 + body.length);
      final lengthHeader =
          ByteData.sublistView(framed, 0, 4).getUint32(0, Endian.big);
      expect(lengthHeader, body.length);
    });

    test('handles unicode payload', () {
      final payload = {'clinic_name': 'عيادة الأسنان', 'note': '中文'};
      final framed = BluetoothFrameCodec.encode(payload);
      final reader = FrameReader();
      reader.addBytes(framed);
      expect(reader.next(), payload);
    });

    test('decodes back-to-back frames', () {
      final f1 = BluetoothFrameCodec.encode({'a': 1});
      final f2 = BluetoothFrameCodec.encode({'b': 2});
      final reader = FrameReader();
      reader.addBytes(Uint8List.fromList([...f1, ...f2]));
      expect(reader.next(), {'a': 1});
      expect(reader.next(), {'b': 2});
      expect(reader.next(), isNull);
    });

    test('reader returns null when frame is partial', () {
      final framed = BluetoothFrameCodec.encode({'a': 1});
      final reader = FrameReader();
      reader.addBytes(framed.sublist(0, 3));   // only 3 of 4 length bytes
      expect(reader.next(), isNull);
      reader.addBytes(framed.sublist(3));      // feed the rest
      expect(reader.next(), {'a': 1});
    });

    test('encode rejects oversized payload', () {
      final huge = {'data': 'x' * (4 * 1024 * 1024)};   // ~4 MB
      expect(() => BluetoothFrameCodec.encode(huge), throwsArgumentError);
    });
  });
}
```

- [ ] **Step 2: Confirm fail**

Run: `cd clinic_mobile_app && flutter test test/bluetooth_frame_codec_test.dart`
Expected: ImportError / file-not-found on `bluetooth_frame_codec.dart`.

- [ ] **Step 3: Implement the codec**

Create `clinic_mobile_app/lib/services/bluetooth_frame_codec.dart`:

```dart
import 'dart:convert';
import 'dart:typed_data';

/// 4-byte big-endian length prefix + UTF-8 JSON payload.
class BluetoothFrameCodec {
  static const int maxFrameBytes = 4 * 1024 * 1024;

  static Uint8List encode(Map<String, dynamic> payload) {
    final body = utf8.encode(jsonEncode(payload));
    if (body.length > maxFrameBytes) {
      throw ArgumentError('frame too large: ${body.length} > $maxFrameBytes');
    }
    final out = BytesBuilder();
    final header = ByteData(4)..setUint32(0, body.length, Endian.big);
    out.add(header.buffer.asUint8List());
    out.add(body);
    return out.toBytes();
  }
}

/// Incremental decoder: feed bytes as they arrive, call [next] to pull
/// completed frames out. Returns null when no full frame is buffered yet.
class FrameReader {
  final BytesBuilder _buf = BytesBuilder(copy: false);

  void addBytes(List<int> bytes) {
    _buf.add(bytes);
  }

  Map<String, dynamic>? next() {
    final all = _buf.toBytes();
    if (all.length < 4) return null;
    final length = ByteData.sublistView(all, 0, 4).getUint32(0, Endian.big);
    if (length > BluetoothFrameCodec.maxFrameBytes) {
      throw const FormatException('frame too large');
    }
    if (all.length < 4 + length) return null;
    final body = all.sublist(4, 4 + length);
    final rest = all.sublist(4 + length);
    _buf.clear();
    _buf.add(rest);
    final decoded = jsonDecode(utf8.decode(body));
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('frame body is not a JSON object');
    }
    return decoded;
  }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd clinic_mobile_app && flutter test test/bluetooth_frame_codec_test.dart`
Expected: All 6 tests pass.

- [ ] **Step 5: Run all Flutter tests + analyze**

Run:
```bash
cd clinic_mobile_app
flutter test
flutter analyze
```
Expected: no new failures, no new analyzer warnings.

- [ ] **Step 6: Commit**

```bash
git add clinic_mobile_app/lib/services/bluetooth_frame_codec.dart clinic_mobile_app/test/bluetooth_frame_codec_test.dart
git commit -m "feat(bt-mobile): length-prefixed JSON frame codec"
```

---

## Task 9: Flutter protocol-over-stream client

**Files:**
- Create: `clinic_mobile_app/lib/services/bt_session_client.dart`
- Create: `clinic_mobile_app/test/bt_session_client_test.dart`

Designed so the production code can plug `BluetoothConnection`'s `input`/`output` streams in, while tests use a `StreamController` + `Completer`-based mock.

- [ ] **Step 1: Write the failing tests**

Create `clinic_mobile_app/test/bt_session_client_test.dart`:

```dart
import 'dart:async';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/bluetooth_frame_codec.dart';
import 'package:clinic_mobile_app/services/bt_session_client.dart';

class _FakeBtStream implements BtStream {
  final _incoming = StreamController<Uint8List>();
  final List<List<int>> written = [];
  bool closed = false;
  @override
  Stream<Uint8List> get input => _incoming.stream;
  @override
  void writeBytes(List<int> bytes) => written.add(bytes);
  @override
  Future<void> close() async {
    closed = true;
    await _incoming.close();
  }
  void deliver(Map<String, dynamic> resp) {
    _incoming.add(BluetoothFrameCodec.encode(resp));
  }
}

void main() {
  test('successful hello -> export -> import round trip', () async {
    final stream = _FakeBtStream();
    final client = BtSessionClient(stream);
    final fut = client.runSession(
      deviceToken: 'good',
      clientVersion: '1.0.0',
      getSince: () async => null,
      onExport: (exported) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
    );
    // Drive the dialogue by responding to each frame the client writes.
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'server_version': '1.0.0'});
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'tables': {}, 'tombstones': [], 'generated_at': 't'});
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'applied': 0, 'skipped': 0});
    final result = await fut;
    expect(result.success, true);
    expect(stream.closed, true);
  });

  test('unauthorized response aborts and reports auth failure', () async {
    final stream = _FakeBtStream();
    final client = BtSessionClient(stream);
    final fut = client.runSession(
      deviceToken: 'bad',
      clientVersion: '1.0.0',
      getSince: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
    );
    await Future.delayed(Duration.zero);
    stream.deliver({'error': 'unauthorized'});
    final result = await fut;
    expect(result.success, false);
    expect(result.unauthorized, true);
  });

  test('error in import response is reported as failure but not unauthorized',
      () async {
    final stream = _FakeBtStream();
    final client = BtSessionClient(stream);
    final fut = client.runSession(
      deviceToken: 'good',
      clientVersion: '1.0.0',
      getSince: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
    );
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'server_version': '1.0.0'});
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'tables': {}, 'tombstones': []});
    await Future.delayed(Duration.zero);
    stream.deliver({'error': 'malformed frame'});
    final result = await fut;
    expect(result.success, false);
    expect(result.unauthorized, false);
  });
}
```

- [ ] **Step 2: Confirm fail**

Run: `cd clinic_mobile_app && flutter test test/bt_session_client_test.dart`
Expected: file-not-found on `bt_session_client.dart`.

- [ ] **Step 3: Implement the client**

Create `clinic_mobile_app/lib/services/bt_session_client.dart`:

```dart
import 'dart:async';
import 'dart:typed_data';

import 'bluetooth_frame_codec.dart';

/// Tiny abstraction over the underlying BT connection so tests can swap in a
/// fake without dragging in flutter_bluetooth_serial.
abstract class BtStream {
  Stream<Uint8List> get input;
  void writeBytes(List<int> bytes);
  Future<void> close();
}

/// Outcome of one Bluetooth sync round-trip.
class BtSessionResult {
  final bool success;
  final bool unauthorized;
  final String? errorMessage;
  const BtSessionResult.ok()
      : success = true, unauthorized = false, errorMessage = null;
  const BtSessionResult.unauthorized()
      : success = false, unauthorized = true, errorMessage = 'unauthorized';
  const BtSessionResult.failure(this.errorMessage)
      : success = false, unauthorized = false;
}

/// Runs one hello → sync_export → sync_import dialogue over the supplied stream.
/// On failure the stream is closed. The caller decides retry / cadence.
class BtSessionClient {
  final BtStream _stream;
  BtSessionClient(this._stream);

  Future<BtSessionResult> runSession({
    required String deviceToken,
    required String clientVersion,
    required Future<String?> Function() getSince,
    required Future<void> Function(Map<String, dynamic> exported) onExport,
    required Future<Map<String, dynamic>> Function() buildPushPayload,
    Duration handshakeTimeout = const Duration(seconds: 10),
  }) async {
    final reader = FrameReader();
    final responses = StreamController<Map<String, dynamic>>();
    late StreamSubscription<Uint8List> sub;
    sub = _stream.input.listen(
      (chunk) {
        reader.addBytes(chunk);
        while (true) {
          try {
            final frame = reader.next();
            if (frame == null) break;
            responses.add(frame);
          } on FormatException catch (e) {
            responses.addError(e);
            break;
          }
        }
      },
      onError: responses.addError,
      onDone: () => responses.close(),
      cancelOnError: false,
    );

    Future<Map<String, dynamic>> awaitOne() async {
      final r = await responses.stream.first.timeout(handshakeTimeout);
      return r;
    }

    Future<void> send(Map<String, dynamic> msg) async {
      _stream.writeBytes(BluetoothFrameCodec.encode(msg));
    }

    Future<BtSessionResult> _finishWith(BtSessionResult r) async {
      await sub.cancel();
      await responses.close();
      await _stream.close();
      return r;
    }

    try {
      await send({
        'op': 'hello',
        'device_token': deviceToken,
        'client_version': clientVersion,
      });
      final hello = await awaitOne();
      if (hello['error'] == 'unauthorized') {
        return _finishWith(const BtSessionResult.unauthorized());
      }
      if (hello['ok'] != true) {
        return _finishWith(BtSessionResult.failure('hello failed: $hello'));
      }

      final since = await getSince();
      await send({'op': 'sync_export', 'since': since});
      final exportResp = await awaitOne();
      if (exportResp['error'] != null) {
        return _finishWith(BtSessionResult.failure(exportResp['error'].toString()));
      }
      await onExport(exportResp);

      final push = await buildPushPayload();
      await send({'op': 'sync_import', 'tables': push['tables'], 'tombstones': push['tombstones']});
      final importResp = await awaitOne();
      if (importResp['error'] != null) {
        return _finishWith(BtSessionResult.failure(importResp['error'].toString()));
      }

      return _finishWith(const BtSessionResult.ok());
    } on TimeoutException {
      return _finishWith(BtSessionResult.failure('timeout'));
    } catch (e) {
      return _finishWith(BtSessionResult.failure(e.toString()));
    }
  }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd clinic_mobile_app && flutter test test/bt_session_client_test.dart`
Expected: 3 passed.

- [ ] **Step 5: Analyze**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: no new warnings.

- [ ] **Step 6: Commit**

```bash
git add clinic_mobile_app/lib/services/bt_session_client.dart clinic_mobile_app/test/bt_session_client_test.dart
git commit -m "feat(bt-mobile): protocol-over-stream session client"
```

---

## Task 10: Flutter local storage fields for BT

**Files:**
- Modify: `clinic_mobile_app/lib/services/local_storage_service.dart`

- [ ] **Step 1: Add the fields + methods**

Open `clinic_mobile_app/lib/services/local_storage_service.dart`. Add these constants alongside the existing `_cloudClinicIdKey`:

```dart
  static const _btEnabledKey = 'bt_enabled';
  static const _btBondedMacKey = 'bt_bonded_mac';
  static const _btBondedLabelKey = 'bt_bonded_label';
  static const _btLastSyncAtKey = 'bt_last_sync_at';
  static const _btLastErrorKey = 'bt_last_error';
```

At the bottom of the class (before the closing `}`), add:

```dart
  // ── Bluetooth peer (links this device to a clinic PC over BT-SPP) ──

  Future<bool> getBtEnabled() async {
    final v = await _storage.read(key: _btEnabledKey);
    return v == '1';
  }

  Future<void> setBtEnabled(bool enabled) =>
      _storage.write(key: _btEnabledKey, value: enabled ? '1' : '0');

  Future<String?> getBtBondedMac() => _storage.read(key: _btBondedMacKey);

  Future<String?> getBtBondedLabel() => _storage.read(key: _btBondedLabelKey);

  Future<void> setBtBondedPeer({required String mac, required String label}) async {
    await _storage.write(key: _btBondedMacKey, value: mac);
    await _storage.write(key: _btBondedLabelKey, value: label);
  }

  Future<void> clearBtBondedPeer() async {
    await _storage.delete(key: _btBondedMacKey);
    await _storage.delete(key: _btBondedLabelKey);
  }

  Future<String?> getBtLastSyncAt() => _storage.read(key: _btLastSyncAtKey);

  Future<void> setBtLastSyncAt(String iso) =>
      _storage.write(key: _btLastSyncAtKey, value: iso);

  Future<String?> getBtLastError() => _storage.read(key: _btLastErrorKey);

  Future<void> setBtLastError(String message) =>
      _storage.write(key: _btLastErrorKey, value: message);

  Future<void> clearBtLastError() => _storage.delete(key: _btLastErrorKey);
```

- [ ] **Step 2: Analyze**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: no new warnings.

- [ ] **Step 3: Commit**

```bash
git add clinic_mobile_app/lib/services/local_storage_service.dart
git commit -m "feat(bt-mobile): local-storage fields for bonded peer + status"
```

---

## Task 11: Flutter pubspec + manifest changes

**Files:**
- Modify: `clinic_mobile_app/pubspec.yaml`
- Modify: `clinic_mobile_app/android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Swap pubspec deps**

In `clinic_mobile_app/pubspec.yaml`, **remove** the line `flutter_blue_plus: ^1.31.15` and **add** in its place:

```yaml
  flutter_bluetooth_serial: ^0.4.0
  flutter_background_service: ^5.0.5
```

- [ ] **Step 2: Resolve deps**

Run: `cd clinic_mobile_app && flutter pub get`
Expected: both new packages resolved; `flutter_blue_plus` gone from `.dart_tool/package_config.json`.

- [ ] **Step 3: Update AndroidManifest**

Open `clinic_mobile_app/android/app/src/main/AndroidManifest.xml`. **After** the existing `<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />` line, add:

```xml
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

Inside the `<application>` element, before `</application>`, declare the foreground service:

```xml
        <service
            android:name="id.flutter.flutter_background_service.BackgroundService"
            android:foregroundServiceType="dataSync"
            android:exported="false" />
```

- [ ] **Step 4: Build sanity check**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: no new errors; warnings on the existing BLE references in `bluetooth_sync_service.dart` are expected and will go away in Task 12.

- [ ] **Step 5: Commit**

```bash
git add clinic_mobile_app/pubspec.yaml clinic_mobile_app/pubspec.lock clinic_mobile_app/android/app/src/main/AndroidManifest.xml
git commit -m "build(mobile): swap flutter_blue_plus → flutter_bluetooth_serial + add foreground service"
```

---

## Task 12: Flutter BluetoothSyncService rewrite

**Files:**
- Modify: `clinic_mobile_app/lib/services/bluetooth_sync_service.dart` (full rewrite)
- Create: `clinic_mobile_app/test/bluetooth_sync_service_test.dart`

Behaviour: hold the bonded MAC, expose `runOneSyncCycle()` that opens a `BluetoothConnection`, wraps it in a `BtStream`, runs `BtSessionClient.runSession`, and reports status. The 30 s loop runs from `ConnectivitySyncService` (Task 13) so this class stays a one-shot per-cycle worker — easier to test.

- [ ] **Step 1: Write the failing tests**

Create `clinic_mobile_app/test/bluetooth_sync_service_test.dart`:

```dart
import 'dart:async';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/bluetooth_frame_codec.dart';
import 'package:clinic_mobile_app/services/bt_session_client.dart';
import 'package:clinic_mobile_app/services/bluetooth_sync_service.dart';

class _ScriptedStream implements BtStream {
  final _in = StreamController<Uint8List>();
  final List<List<int>> writes = [];
  bool closed = false;
  final List<Map<String, dynamic>> _script;
  _ScriptedStream(this._script);
  @override
  Stream<Uint8List> get input => _in.stream;
  @override
  void writeBytes(List<int> bytes) {
    writes.add(bytes);
    if (_script.isNotEmpty) {
      final resp = _script.removeAt(0);
      Future.microtask(() => _in.add(BluetoothFrameCodec.encode(resp)));
    }
  }
  @override
  Future<void> close() async { closed = true; await _in.close(); }
}

void main() {
  test('runOneSyncCycle returns success on full round trip', () async {
    final stream = _ScriptedStream([
      {'ok': true, 'server_version': '1.0.0'},
      {'ok': true, 'tables': {}, 'tombstones': [], 'generated_at': 't'},
      {'ok': true, 'applied': 0, 'skipped': 0},
    ]);
    final svc = BluetoothSyncService.forTest(
      streamOpener: (mac) async => stream,
      deviceTokenLoader: () async => 'good',
      sinceLoader: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
      clientVersion: '1.0.0',
    );
    final result = await svc.runOneSyncCycle('00:11:22:33:44:55');
    expect(result.success, true);
    expect(stream.closed, true);
  });

  test('runOneSyncCycle reports unauthorized and stops loop', () async {
    final stream = _ScriptedStream([{'error': 'unauthorized'}]);
    final svc = BluetoothSyncService.forTest(
      streamOpener: (mac) async => stream,
      deviceTokenLoader: () async => 'bad',
      sinceLoader: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
      clientVersion: '1.0.0',
    );
    final result = await svc.runOneSyncCycle('00:11:22:33:44:55');
    expect(result.success, false);
    expect(result.unauthorized, true);
  });

  test('returns failure when opener throws (peer out of range)', () async {
    final svc = BluetoothSyncService.forTest(
      streamOpener: (_) async => throw 'cannot connect',
      deviceTokenLoader: () async => 'good',
      sinceLoader: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
      clientVersion: '1.0.0',
    );
    final result = await svc.runOneSyncCycle('00:11:22:33:44:55');
    expect(result.success, false);
    expect(result.unauthorized, false);
  });
}
```

- [ ] **Step 2: Confirm fail**

Run: `cd clinic_mobile_app && flutter test test/bluetooth_sync_service_test.dart`
Expected: errors on `BluetoothSyncService.forTest` / `streamOpener`.

- [ ] **Step 3: Replace the file**

Overwrite `clinic_mobile_app/lib/services/bluetooth_sync_service.dart` with:

```dart
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_bluetooth_serial/flutter_bluetooth_serial.dart';

import 'bt_session_client.dart';

/// Wraps a `BluetoothConnection` so the protocol client can use it via the
/// `BtStream` abstraction.
class _BtConnectionStream implements BtStream {
  final BluetoothConnection _conn;
  _BtConnectionStream(this._conn);
  @override
  Stream<Uint8List> get input => _conn.input ?? const Stream<Uint8List>.empty();
  @override
  void writeBytes(List<int> bytes) {
    _conn.output.add(Uint8List.fromList(bytes));
  }
  @override
  Future<void> close() async {
    try { await _conn.output.allSent; } catch (_) {}
    try { await _conn.close(); } catch (_) {}
  }
}

typedef BtStreamOpener = Future<BtStream> Function(String mac);
typedef DeviceTokenLoader = Future<String?> Function();
typedef SinceLoader = Future<String?> Function();
typedef OnExportHandler = Future<void> Function(Map<String, dynamic> exported);
typedef PushPayloadBuilder = Future<Map<String, dynamic>> Function();

/// One-shot Bluetooth sync runner. The 30-s cadence loop lives in
/// ConnectivitySyncService; this class just runs one cycle when called.
class BluetoothSyncService {
  final BtStreamOpener _open;
  final DeviceTokenLoader _loadToken;
  final SinceLoader _loadSince;
  final OnExportHandler _onExport;
  final PushPayloadBuilder _buildPush;
  final String _clientVersion;

  BluetoothSyncService._({
    required BtStreamOpener open,
    required DeviceTokenLoader loadToken,
    required SinceLoader loadSince,
    required OnExportHandler onExport,
    required PushPayloadBuilder buildPush,
    required String clientVersion,
  })  : _open = open,
        _loadToken = loadToken,
        _loadSince = loadSince,
        _onExport = onExport,
        _buildPush = buildPush,
        _clientVersion = clientVersion;

  factory BluetoothSyncService.production({
    required DeviceTokenLoader deviceTokenLoader,
    required SinceLoader sinceLoader,
    required OnExportHandler onExport,
    required PushPayloadBuilder buildPushPayload,
    required String clientVersion,
  }) {
    return BluetoothSyncService._(
      open: (mac) async {
        final conn = await BluetoothConnection.toAddress(mac)
            .timeout(const Duration(seconds: 10));
        return _BtConnectionStream(conn);
      },
      loadToken: deviceTokenLoader,
      loadSince: sinceLoader,
      onExport: onExport,
      buildPush: buildPushPayload,
      clientVersion: clientVersion,
    );
  }

  /// Test seam.
  factory BluetoothSyncService.forTest({
    required BtStreamOpener streamOpener,
    required DeviceTokenLoader deviceTokenLoader,
    required SinceLoader sinceLoader,
    required OnExportHandler onExport,
    required PushPayloadBuilder buildPushPayload,
    required String clientVersion,
  }) =>
      BluetoothSyncService._(
        open: streamOpener,
        loadToken: deviceTokenLoader,
        loadSince: sinceLoader,
        onExport: onExport,
        buildPush: buildPushPayload,
        clientVersion: clientVersion,
      );

  Future<BtSessionResult> runOneSyncCycle(String bondedMac) async {
    final token = await _loadToken();
    if (token == null || token.isEmpty) {
      return const BtSessionResult.failure('no device token');
    }
    final BtStream stream;
    try {
      stream = await _open(bondedMac);
    } catch (e) {
      return BtSessionResult.failure(e.toString());
    }
    final client = BtSessionClient(stream);
    return client.runSession(
      deviceToken: token,
      clientVersion: _clientVersion,
      getSince: _loadSince,
      onExport: _onExport,
      buildPushPayload: _buildPush,
    );
  }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd clinic_mobile_app && flutter test test/bluetooth_sync_service_test.dart`
Expected: 3 passed.

- [ ] **Step 5: Analyze + all tests**

Run:
```bash
cd clinic_mobile_app
flutter analyze
flutter test
```
Expected: zero new warnings; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add clinic_mobile_app/lib/services/bluetooth_sync_service.dart clinic_mobile_app/test/bluetooth_sync_service_test.dart
git commit -m "feat(bt-mobile): rewrite BluetoothSyncService over flutter_bluetooth_serial"
```

---

## Task 13: Hook BT into ConnectivitySyncService

**Files:**
- Modify: `clinic_mobile_app/lib/services/connectivity_sync_service.dart`
- Modify: `clinic_mobile_app/lib/state/app_state.dart`

`ConnectivitySyncService` already has a `syncViaBluetooth()` method that delegates to the BLE service. We rewire it to the new service, and add an auto-tick loop gated on LAN/cloud reachability.

- [ ] **Step 1: Rewire `syncViaBluetooth` + add the gated auto-loop**

Open `clinic_mobile_app/lib/services/connectivity_sync_service.dart`.

**Replace** the body of `Future<bool> syncViaBluetooth()` with the call below, and **add** the auto-loop fields + methods.

Final shape of the relevant pieces (paste this in place — preserves the rest of the file unchanged):

Replace:
```dart
  Future<bool> syncViaBluetooth() async {
    _emit(SyncStatus.syncing, 'Bluetooth sync…');
    final ok = await _bluetooth.scanAndSync();
    if (ok) {
      _activeLink = SyncLink.bluetooth;
      _emit(SyncStatus.synced, 'Synced · Bluetooth');
    } else {
      _activeLink = SyncLink.none;
      _emit(SyncStatus.error,
          _bluetooth.lastError ?? 'Bluetooth sync failed');
    }
    return ok;
  }
```

With:
```dart
  Future<bool> syncViaBluetooth(String bondedMac) async {
    _emit(SyncStatus.syncing, 'Bluetooth sync…');
    final result = await _bluetooth.runOneSyncCycle(bondedMac);
    if (result.success) {
      _activeLink = SyncLink.bluetooth;
      _emit(SyncStatus.synced, 'Synced · Bluetooth');
      await _storage.setBtLastSyncAt(DateTime.now().toIso8601String());
      await _storage.clearBtLastError();
      return true;
    }
    _activeLink = SyncLink.none;
    await _storage.setBtLastError(result.errorMessage ?? 'unknown');
    _emit(SyncStatus.error, result.errorMessage ?? 'Bluetooth sync failed');
    return false;
  }

  Timer? _btAutoTimer;

  /// Start the auto-fallback BT loop. Idempotent; safe to call repeatedly.
  void startBluetoothAutoLoop({Duration interval = const Duration(seconds: 30)}) {
    _btAutoTimer?.cancel();
    _btAutoTimer = Timer.periodic(interval, (_) => _btAutoTick());
    // also tick immediately so we don't wait 30 s on first activation
    unawaited(_btAutoTick());
  }

  void stopBluetoothAutoLoop() {
    _btAutoTimer?.cancel();
    _btAutoTimer = null;
  }

  Future<void> _btAutoTick() async {
    if (_status == SyncStatus.syncing) return;
    final mac = await _storage.getBtBondedMac();
    if (mac == null || mac.isEmpty) return;
    final enabled = await _storage.getBtEnabled();
    if (!enabled) return;
    // Skip if LAN or cloud just synced — fallback-only mode.
    final lanOk = await _isLanReachable();
    if (lanOk) return;
    final cloudOk = await _isCloudReachable();
    if (cloudOk) return;
    await syncViaBluetooth(mac);
  }

  Future<bool> _isLanReachable() async {
    final url = await _storage.getLocalUrl();
    final token = await _storage.getDeviceToken();
    if (url == null || url.isEmpty || token == null || token.isEmpty) return false;
    return _cloud.isReachable(url);
  }

  Future<bool> _isCloudReachable() async {
    final url = await _storage.getCloudUrl();
    final token = await _storage.getCloudClinicToken();
    if (url == null || url.isEmpty || token == null || token.isEmpty) return false;
    return _cloud.isReachable(url, clinicToken: token);
  }
```

Also update `void dispose()` to cancel the timer — replace its body with:
```dart
  void dispose() {
    _btAutoTimer?.cancel();
    _connectivitySub?.cancel();
    _statusController.close();
  }
```

(Remove the `_bluetooth.dispose();` line — the new BluetoothSyncService is stateless.)

Add `import 'dart:async';` at the top if it isn't already present (it is — leave it).

- [ ] **Step 2: Wire startup in `AppState`**

Open `clinic_mobile_app/lib/state/app_state.dart`. Find the `init()` method (search for `Future<void> init`). At the end of `init()` (after the existing service wiring), add:

```dart
    // Start the Bluetooth auto-fallback loop if a peer is bonded + enabled.
    final btEnabled = await _storage.getBtEnabled();
    final btMac = await _storage.getBtBondedMac();
    if (btEnabled && btMac != null && btMac.isNotEmpty) {
      _connectivity.startBluetoothAutoLoop();
    }
```

Find the constructor where `BluetoothSyncService` is built (search for `BluetoothSyncService(`). Replace its construction with the production factory:

```dart
    _bluetooth = BluetoothSyncService.production(
      deviceTokenLoader: _storage.getDeviceToken,
      sinceLoader: () => _storage.read(key: 'last_bt_sync_cursor'),
      onExport: (exported) async {
        // Reuse the InternetSyncService merge path so server-shape rows hit
        // the same merger that the LAN/cloud path uses.
        await _internet.applyExportedDelta(exported);
      },
      buildPushPayload: _internet.buildPushPayload,
      clientVersion: '1.0.0',
    );
```

> **Note:** if `_internet.applyExportedDelta` / `buildPushPayload` don't exist yet (they probably don't — those routines are inside `internet_sync_service.dart`), extract them by:
> 1. Open `clinic_mobile_app/lib/services/internet_sync_service.dart`.
> 2. Locate the section in the existing `syncAll()` that calls the HTTP export endpoint and then applies the response — move the "apply response" code into a new method `Future<void> applyExportedDelta(Map<String, dynamic> response) async { ... }`.
> 3. Similarly, locate the section that builds the push body — move into `Future<Map<String, dynamic>> buildPushPayload() async { ... return {'tables': ..., 'tombstones': ...}; }`.
> 4. Have `syncAll()` call these two new methods. Don't change behavior — pure refactor.

- [ ] **Step 3: Run analyzer**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: zero new errors. The old `_bluetooth.dispose()` and references to BLE state should be gone.

- [ ] **Step 4: Run all Flutter tests**

Run: `cd clinic_mobile_app && flutter test`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clinic_mobile_app/lib/services/connectivity_sync_service.dart clinic_mobile_app/lib/state/app_state.dart clinic_mobile_app/lib/services/internet_sync_service.dart
git commit -m "feat(bt-mobile): hook auto-fallback BT loop into ConnectivitySyncService"
```

---

## Task 14: Phone Settings → Bluetooth peer card

**Files:**
- Modify: `clinic_mobile_app/lib/screens/settings_screen.dart`

Surface: enable toggle, "Pick clinic PC" picker, status line.

- [ ] **Step 1: Add the card to the Settings screen**

Open `clinic_mobile_app/lib/screens/settings_screen.dart`. Find the **Cloud Account card** (search for `Cloud Account`). Insert this new widget block **after** the Cloud Account card:

```dart
ClinicCard(
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      SectionHeader(
        icon: Icons.bluetooth_rounded,
        titleEn: 'Bluetooth peer',
        titleAr: 'الاتصال عبر بلوتوث',
      ),
      const SizedBox(height: 12),
      Consumer<AppState>(
        builder: (context, app, _) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SwitchListTile.adaptive(
                value: app.btEnabled,
                onChanged: (v) => app.setBtEnabled(v),
                title: Text(app.locale == 'ar'
                    ? 'تفعيل المزامنة عبر بلوتوث'
                    : 'Enable Bluetooth sync'),
              ),
              const SizedBox(height: 8),
              if (app.btBondedLabel != null)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.devices_other_rounded),
                  title: Text(app.btBondedLabel!),
                  subtitle: Text(app.btBondedMac ?? ''),
                  trailing: TextButton(
                    onPressed: () => app.unbindBtPeer(),
                    child: Text(app.locale == 'ar' ? 'إزالة' : 'Remove'),
                  ),
                )
              else
                GradientButton(
                  label: app.locale == 'ar' ? 'اختر كمبيوتر العيادة' : 'Pick clinic PC',
                  icon: Icons.bluetooth_searching_rounded,
                  onPressed: () => _pickBondedPeer(context, app),
                ),
              const SizedBox(height: 8),
              Text(_btStatusLine(app),
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          );
        },
      ),
    ],
  ),
),
```

Add the helpers **inside the State class**:

```dart
  String _btStatusLine(AppState app) {
    if (!app.btEnabled) return app.locale == 'ar' ? 'متوقّفة' : 'Disabled';
    if (app.btBondedMac == null) {
      return app.locale == 'ar' ? 'لم يتم الاقتران' : 'Not paired';
    }
    if (app.btLastError != null && app.btLastError!.isNotEmpty) {
      return '⚠️ ${app.btLastError}';
    }
    if (app.btLastSyncAt != null && app.btLastSyncAt!.isNotEmpty) {
      return (app.locale == 'ar' ? 'آخر مزامنة: ' : 'Last sync: ') +
          app.btLastSyncAt!;
    }
    return app.locale == 'ar' ? 'في انتظار الاقتراب…' : 'Waiting to come into range…';
  }

  Future<void> _pickBondedPeer(BuildContext context, AppState app) async {
    final devices = await FlutterBluetoothSerial.instance.getBondedDevices();
    if (!context.mounted) return;
    if (devices.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(
          app.locale == 'ar'
              ? 'لا توجد أجهزة مقترنة — اقترن أولًا من إعدادات بلوتوث'
              : 'No bonded devices — pair in Android Bluetooth settings first')));
      return;
    }
    final picked = await showModalBottomSheet<BluetoothDevice>(
      context: context,
      builder: (_) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final d in devices)
              ListTile(
                leading: const Icon(Icons.computer_rounded),
                title: Text(d.name ?? d.address),
                subtitle: Text(d.address),
                onTap: () => Navigator.of(context).pop(d),
              ),
          ],
        ),
      ),
    );
    if (picked != null) {
      await app.bindBtPeer(mac: picked.address, label: picked.name ?? picked.address);
    }
  }
```

Add the imports at the top of the file if they're not already there:
```dart
import 'package:flutter_bluetooth_serial/flutter_bluetooth_serial.dart';
```

- [ ] **Step 2: Add `AppState` methods**

Open `clinic_mobile_app/lib/state/app_state.dart`. Add these getters + methods inside the class:

```dart
  // ── Bluetooth peer ───────────────────────────────────────────────────────
  bool _btEnabled = false;
  String? _btBondedMac;
  String? _btBondedLabel;
  String? _btLastSyncAt;
  String? _btLastError;

  bool get btEnabled => _btEnabled;
  String? get btBondedMac => _btBondedMac;
  String? get btBondedLabel => _btBondedLabel;
  String? get btLastSyncAt => _btLastSyncAt;
  String? get btLastError => _btLastError;

  Future<void> _loadBtState() async {
    _btEnabled = await _storage.getBtEnabled();
    _btBondedMac = await _storage.getBtBondedMac();
    _btBondedLabel = await _storage.getBtBondedLabel();
    _btLastSyncAt = await _storage.getBtLastSyncAt();
    _btLastError = await _storage.getBtLastError();
    notifyListeners();
  }

  Future<void> setBtEnabled(bool enabled) async {
    _btEnabled = enabled;
    await _storage.setBtEnabled(enabled);
    if (enabled && _btBondedMac != null && _btBondedMac!.isNotEmpty) {
      _connectivity.startBluetoothAutoLoop();
    } else {
      _connectivity.stopBluetoothAutoLoop();
    }
    notifyListeners();
  }

  Future<void> bindBtPeer({required String mac, required String label}) async {
    await _storage.setBtBondedPeer(mac: mac, label: label);
    _btBondedMac = mac;
    _btBondedLabel = label;
    if (_btEnabled) _connectivity.startBluetoothAutoLoop();
    notifyListeners();
  }

  Future<void> unbindBtPeer() async {
    _connectivity.stopBluetoothAutoLoop();
    await _storage.clearBtBondedPeer();
    _btBondedMac = null;
    _btBondedLabel = null;
    notifyListeners();
  }
```

In `init()`, at the very end, call:
```dart
    await _loadBtState();
```

- [ ] **Step 3: Analyze**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: zero new warnings.

- [ ] **Step 4: All Flutter tests**

Run: `cd clinic_mobile_app && flutter test`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clinic_mobile_app/lib/screens/settings_screen.dart clinic_mobile_app/lib/state/app_state.dart
git commit -m "feat(bt-mobile): Settings card — bond a clinic PC, status line"
```

---

## Task 15: Sync status bar — Bluetooth label

**Files:**
- Modify: `clinic_mobile_app/lib/widgets/sync_status_bar.dart` (only if it doesn't already render `SyncLink.bluetooth`)

- [ ] **Step 1: Inspect the existing widget**

Run: `grep -n "SyncLink\." clinic_mobile_app/lib/widgets/sync_status_bar.dart`
Expected: matches showing how `SyncLink.localWifi` / `SyncLink.cloud` are rendered. Confirm whether `SyncLink.bluetooth` is already handled.

- [ ] **Step 2: If `SyncLink.bluetooth` isn't handled, add the case**

Where the widget switches on `activeLink`, add the bluetooth branch alongside the existing ones. Example:

```dart
case SyncLink.bluetooth:
  return _row(
    icon: Icons.bluetooth_connected_rounded,
    label: locale == 'ar' ? 'بلوتوث' : 'Bluetooth',
    color: Colors.green,
  );
```

(Match the exact shape used by the existing `localWifi` and `cloud` branches — don't introduce a new pattern.)

- [ ] **Step 3: Analyze**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: zero new warnings.

- [ ] **Step 4: Commit (if changes made)**

```bash
git add clinic_mobile_app/lib/widgets/sync_status_bar.dart
git commit -m "feat(bt-mobile): render Bluetooth link in sync status bar"
```

If no changes were needed, skip the commit and note "already handled" in the next task.

---

## Task 16: README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find the Sync model section**

Run: `grep -n "## Sync model\|### Sync model\|Sync model" README.md`
Note the line number where the section ends.

- [ ] **Step 2: Add a Bluetooth subsection**

Immediately after the Sync model section's closing paragraph, insert:

```markdown
### Bluetooth sync (offline fallback)

When the phone can reach neither the LAN nor the cloud node, it falls back
to **classic Bluetooth (SPP)** with the desktop. Pair phone↔PC once in
Windows Bluetooth settings; in the local server's **Settings → Bluetooth
Sync** card, enable the toggle and pick the COM port Windows assigned to
the phone. On the phone, **Settings → Bluetooth peer** → "Pick clinic PC"
→ choose the bonded desktop.

From then on, whenever the phone is in range and Wi-Fi/cloud are
unreachable, an Android foreground service connects every 30 s and runs
one `hello → sync_export → sync_import` round-trip over a 4-byte
length-prefixed JSON protocol — same `{tables, tombstones}` envelope as
the HTTP `/api/sync/*` endpoints, reusing `_collect_sync_export` and
`_apply_sync_import` on the server. Last-write-wins by `updated_at` is
unchanged.

When Wi-Fi or cloud are reachable, the BT loop is dormant — wasted work
otherwise. Battery cost ≈ same as a smartwatch in standby. Configure
cadence with `bt_sync_interval_seconds` in the phone's local storage
(default 30 s).
```

- [ ] **Step 3: Run tests one more time as a regression net**

Run:
```bash
python -m pytest tests/ -q
cd clinic_mobile_app && flutter test && flutter analyze
```
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README — Bluetooth sync fallback section"
```

---

## Task 17: Manual end-to-end smoke + merge

**Files:** none — manual verification + branch merge.

- [ ] **Step 1: Build the desktop app and confirm BT thread starts**

Run: `python dental_clinic.py`
Expected: console prints `📡 Bluetooth sync ready (configure in Settings → Bluetooth Sync)`. No crashes. Open Settings page; the new BT card is present.

- [ ] **Step 2: Build the APK**

Run: `cd clinic_mobile_app && flutter build apk --release`
Expected: clean build. APK at `build/app/outputs/flutter-apk/app-release.apk`.

- [ ] **Step 3: Manual on-device verification (skip if no hardware available; note as "deferred")**

1. Pair the phone with the Windows PC in Windows Bluetooth settings. Note the assigned outgoing COM port.
2. In the desktop portal Settings → Bluetooth Sync: enable + pick the COM port → Save. Status line should change to "Waiting for a phone…".
3. Install the APK on the phone. Open Settings → Bluetooth peer → enable → "Pick clinic PC" → select the desktop. Status line: "Waiting to come into range…".
4. Turn Wi-Fi OFF on the phone. Within ~60 s the status should change to "Last sync: <ts>" on both sides.
5. Add a patient on the phone (still Wi-Fi off). Wait <60 s. Open the desktop portal — the patient appears.
6. Add an appointment on the desktop. Wait <60 s. The phone shows it.

- [ ] **Step 4: Merge back to the base branch**

Run:
```bash
git checkout backup/ui-backup-20260506-135130
git merge --ff-only feat/bluetooth-sync
git log --oneline -5
```
Expected: fast-forward; new commits on top of the base branch.

- [ ] **Step 5: Push (only if user has authorised)**

This step requires explicit user authorisation — do NOT run without it:
```bash
git push origin backup/ui-backup-20260506-135130
git branch -d feat/bluetooth-sync
```

---

## Verification matrix

| What | How |
|---|---|
| Frame codec correct on both sides | `pytest tests/test_bt_codec.py`, `flutter test test/bluetooth_frame_codec_test.dart` |
| Dispatcher reuses existing sync helpers | `pytest tests/test_bt_protocol.py` |
| Session driver handles auth + malformed frames | `pytest tests/test_bt_session.py` |
| Endpoints exist + locked behind login | `pytest tests/test_bt_endpoints.py` |
| Server thread re-reads settings, recovers from errors | `pytest tests/test_bt_worker.py` |
| Client session is correct over a fake stream | `flutter test test/bt_session_client_test.dart` |
| BluetoothSyncService aborts on unauthorized | `flutter test test/bluetooth_sync_service_test.dart` |
| Fallback gating: skip when LAN/cloud reachable | Manual smoke step 3 (steps 1-6) |
| No regression elsewhere | `pytest tests/` (target `145 passed`), `flutter analyze`, `flutter test` |
