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
    assert b'unauthorized' in fake.out.getvalue()


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
