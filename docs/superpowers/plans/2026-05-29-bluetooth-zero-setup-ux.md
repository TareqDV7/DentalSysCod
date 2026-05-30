# Zero-setup, plain-language Bluetooth sync — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the Windows COM-port setup, strip the desktop BT card to a single toggle, the mobile BT card to picker + toggle + sync button, and replace raw exception strings with auto-fix + plain-language error messages.

**Architecture:** Desktop adds a native Winsock `AF_BTH` RFCOMM listener (ctypes, no new pip dependency) that advertises its own SDP record under the standard SPP UUID — so the phone's existing `BluetoothConnection.toAddress(mac)` finds it. The current pyserial COM-port path is kept as automatic fallback. A small `_BtSocketStream` adapter lets the new accepted socket reuse the existing `_bt_serve_session` verbatim. Mobile gets a pure `btMessageFor` / `classifyBtError` helper wired into every entry point. Spec: `docs/superpowers/specs/2026-05-29-bluetooth-zero-setup-ux-design.md`.

**Tech Stack:** Python 3.10+ / Flask (`dental_clinic.py` single file), `ctypes` against `ws2_32`, pyserial (kept for fallback). Flutter / Dart for mobile (`flutter_bluetooth_serial`, `permission_handler`).

---

## Progress

- [x] **Task 1** — `_BtSocketStream` adapter — commit `b7b875f` — spec ✅, code-quality ✅
- [x] **Task 2** — Native AF_BTH RFCOMM listener (ctypes) — commit `717d124` — spec ✅, code-quality ✅ (with minors: dead `_RNRSERVICE_DELETE` constant; `recv` collapses errors→EOF — both documented tradeoffs)
- [x] **Task 3** — `bt_sync_server` native-preferred + COM-port fallback — commit `57a0f92` — spec ✅, **code-quality review pending** (paused before dispatch). Implementer caught a contradiction in the plan's fallback test (the `_BT_LOOP_RECONNECT_SLEEP=0.01` monkeypatch made `== ['COMTEST']` exact-once assertion fail) and dropped the conflicting monkeypatch — principled deviation, retained.
- [ ] **Task 4** — Desktop Settings UI: just the toggle
- [ ] **Task 5** — Installer: drop COM-port provisioning
- [ ] **Task 6** — Mobile `btMessageFor` + `classifyBtError` (TDD, pure)
- [ ] **Task 7** — Wire mobile error mapping + remove COM-port tip
- [ ] **Task 8** — README update + full verification + push

**Test counts on hold:** pytest 205 (199 baseline + 4 from T1 + 2 from T3). Flutter test count 50 (unchanged until T6 adds 17).

**Resume here:** dispatch the code-quality review subagent for commit `57a0f92` (T3) per the subagent-driven-development flow, then proceed to T4. The Step-3.3 plan caveat about existing `test_bt_worker.py` needing a defensive `OSError`-raising monkeypatch turned out to be unnecessary on this dev machine (no BT radio → `_bt_open_native_listener` raises `WSAError=10050` naturally). On a machine *with* a real BT radio, existing COM-driven tests may need that monkeypatch — re-check if resuming on a different host.

---

## File Structure

**Desktop (single-file convention — everything in `dental_clinic.py`):**
- New: `_BtSocketStream` class — duck-type a connected socket onto the `.read(n)/.write/.flush` interface `_bt_serve_session` already uses (dental_clinic.py:11843-11856 + `_read_exactly` codec at :11676-11686).
- New: ctypes definitions (`_GUID`, `_SOCKADDR_BTH`, `_SOCKET_ADDRESS`, `_CSADDR_INFO`, `_WSAQUERYSET`) + `_ws2` DLL binding, kept module-level near the other BT internals.
- New: `_bt_open_native_listener()` — binds + advertises + listens. Raises `OSError` if AF_BTH unsupported. Returns the listener handle.
- New: `_NativeBtSocket` — thin wrapper around the raw `SOCKET` handle exposing `.recv/.sendall/.close` so `_BtSocketStream` doesn't care it's not a Python socket.
- New: `_bt_native_accept(listener, stop_event)` + `_bt_accept_and_serve(listener, stop_event, db_path)` — small, injectable, testable.
- Modified: `bt_sync_server()` (dental_clinic.py:11935) — try native first, fall back to COM port.
- Modified: HTML/JS template Settings → Bluetooth Sync card (anchored near dental_clinic.py:3998, 4074, 7260-7316) — remove pill/table/log/advanced; keep toggle + conditional error line.

**Desktop tests:**
- New: `tests/test_bt_socket_stream.py` — `_BtSocketStream` round-trips the 4-byte length-prefixed codec.
- Extended: `tests/test_bt_worker.py` — native-listener available → native path; native returns `None` / raises → COM-port fallback path (existing behaviour).

**Installer:**
- Modified: `installer/DentaCare.iss` — drop the user-action follow-up message box; `provision_bt.ps1` stays in the tree but is no longer wired into the install run.

**Mobile (`clinic_mobile_app/`):**
- New: `lib/utils/bt_error_message.dart` — `BtFailure` enum + `classifyBtError(Object) → BtFailure` + `btMessageFor(BtFailure, locale) → String`. Pure.
- Modified: `lib/services/bluetooth_sync_service.dart` — return classified failure instead of raw `'$e'` strings.
- Modified: `lib/state/app_state.dart` — set `btLastError` via `btMessageFor`, never raw exceptions.
- Modified: `lib/screens/settings_screen.dart` — `_pickBondedPeer` + `_BtErrorBanner`: route through `btMessageFor`; remove the COM-port "tip" copy (settings_screen.dart:699-720).

**Mobile tests:**
- New: `test/bt_error_message_test.dart` — each `BtFailure` → expected EN + AR text; `classifyBtError` maps the expected exception classes.

**Docs:**
- Modified: `README.md` — update the BT sync section (no COM port; remove the Windows BT setup gotcha + COM-port pill references; refresh test counts).

---

## Task 1 — `_BtSocketStream` adapter

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\dental_clinic.py` (add a class near the existing BT helpers, e.g. just before `_bt_open_port` at line 11922)
- Test: `C:\Users\MSI\Desktop\clinic\tests\test_bt_socket_stream.py`

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_bt_socket_stream.py`:

```python
"""_BtSocketStream wraps a socket-like object so _bt_serve_session reads/writes
through the same length-prefixed frame codec it uses for the COM-port path."""

import io
import pytest

import dental_clinic


class _FakeSocket:
    """Duck-types recv/sendall/close. recv returns up to N bytes from a buffer
    (so we can simulate partial reads), sendall accumulates outbound bytes."""

    def __init__(self, inbytes=b''):
        self._inbuf = io.BytesIO(inbytes)
        self.out = bytearray()
        self.closed = False

    def recv(self, n):
        return self._inbuf.read(n)

    def sendall(self, data):
        self.out.extend(data)

    def close(self):
        self.closed = True


def test_read_returns_requested_bytes_when_available():
    sock = _FakeSocket(b'abcdef')
    stream = dental_clinic._BtSocketStream(sock)
    assert stream.read(3) == b'abc'
    assert stream.read(3) == b'def'


def test_read_returns_partial_at_eof():
    sock = _FakeSocket(b'ab')
    stream = dental_clinic._BtSocketStream(sock)
    assert stream.read(4) == b'ab'  # short read; codec turns short into EOFError


def test_write_flushes_through_sendall():
    sock = _FakeSocket()
    stream = dental_clinic._BtSocketStream(sock)
    stream.write(b'hello')
    stream.flush()
    assert bytes(sock.out) == b'hello'


def test_round_trip_through_frame_codec():
    """The whole point: a frame encoded by encode_bt_frame must round-trip
    through _BtSocketStream → decode_bt_frame back to the same dict."""
    payload = {'op': 'hello', 'device_token': 'tok-1', 'version': '1.0.0'}
    encoded = dental_clinic.encode_bt_frame(payload)
    sock = _FakeSocket(encoded)
    stream = dental_clinic._BtSocketStream(sock)
    assert dental_clinic.decode_bt_frame(stream) == payload
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `rtk proxy python -m pytest tests/test_bt_socket_stream.py -v`
Expected: 4 failures with `AttributeError: module 'dental_clinic' has no attribute '_BtSocketStream'`.

- [ ] **Step 1.3: Implement `_BtSocketStream`**

In `dental_clinic.py`, just before `def _bt_open_port(...)` at line 11922, insert:

```python
class _BtSocketStream:
    """Adapts a connected socket-like object (anything with recv/sendall/close)
    onto the .read(n)/.write/.flush surface that _bt_serve_session +
    encode_bt_frame/decode_bt_frame already use for the COM-port path. Lets the
    new native RFCOMM listener reuse _bt_serve_session verbatim."""

    def __init__(self, sock):
        self._sock = sock

    def read(self, n):
        """Up to n bytes. Short reads (incl. zero on EOF) are allowed —
        decode_bt_frame's _read_exactly turns a short read into EOFError."""
        chunks = []
        remaining = n
        while remaining > 0:
            chunk = self._sock.recv(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)

    def write(self, data):
        self._sock.sendall(data)

    def flush(self):
        pass

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `rtk proxy python -m pytest tests/test_bt_socket_stream.py -v`
Expected: 4 passed.

- [ ] **Step 1.5: Commit**

```bash
git add tests/test_bt_socket_stream.py dental_clinic.py
git commit -m "feat(bt): _BtSocketStream adapter for native RFCOMM listener

Wraps a connected socket-like object onto the .read/.write/.flush interface
_bt_serve_session uses, so the upcoming native AF_BTH listener can reuse the
existing session/frame-codec logic verbatim."
```

---

## Task 2 — Native AF_BTH RFCOMM listener (ctypes)

This is the radio-path code. The ctypes structs + binding + `_bt_open_native_listener` cannot be meaningfully unit-tested (the Bluetooth stack is the dependency). The accept/serve loop **is** testable via injected seams (Task 3).

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\dental_clinic.py` (add module-level constants, structs, DLL bindings + helpers near the existing BT internals, just above `_BtSocketStream`)

- [ ] **Step 2.1: Add ctypes definitions and DLL bindings**

In `dental_clinic.py`, near the existing BT helpers (above `_BtSocketStream`), insert:

```python
# ── Native Windows RFCOMM listener (AF_BTH) ────────────────────────────────
#
# Replaces the Windows "Incoming COM port" requirement. The pyserial COM-port
# path remains as fallback in bt_sync_server() when this native path can't
# bind (older Windows / no BT radio / API error). See:
#   docs/superpowers/specs/2026-05-29-bluetooth-zero-setup-ux-design.md
#
# The radio cannot be unit-tested; the only testable seam is the accept→serve
# loop in _bt_accept_and_serve, which Task 3 exercises with injected fakes.

import ctypes as _ct
from ctypes import wintypes as _wt
import socket as _stdsocket  # importing initializes Winsock for the process

_AF_BTH = 32
_SOCK_STREAM = 1
_BTHPROTO_RFCOMM = 3
_BT_PORT_ANY = 0xFFFFFFFF  # (ULONG)-1; tells the stack to assign a channel
_NS_BTH = 16
_RNRSERVICE_REGISTER = 0
_RNRSERVICE_DELETE = 1
_INVALID_SOCKET = _ct.c_void_p(-1).value


class _GUID(_ct.Structure):
    _fields_ = [
        ('Data1', _wt.DWORD),
        ('Data2', _wt.WORD),
        ('Data3', _wt.WORD),
        ('Data4', _ct.c_ubyte * 8),
    ]


# Serial Port Profile service class UUID: 00001101-0000-1000-8000-00805F9B34FB
# Android's BluetoothConnection.toAddress() looks up this exact UUID via SDP.
_SPP_UUID = _GUID(
    0x00001101, 0x0000, 0x1000,
    (_ct.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB),
)


class _SOCKADDR_BTH(_ct.Structure):
    _fields_ = [
        ('addressFamily', _wt.USHORT),
        ('btAddr', _ct.c_ulonglong),
        ('serviceClassId', _GUID),
        ('port', _wt.ULONG),
    ]


class _SOCKET_ADDRESS(_ct.Structure):
    _fields_ = [
        ('lpSockaddr', _ct.POINTER(_SOCKADDR_BTH)),
        ('iSockaddrLength', _ct.c_int),
    ]


class _CSADDR_INFO(_ct.Structure):
    _fields_ = [
        ('LocalAddr', _SOCKET_ADDRESS),
        ('RemoteAddr', _SOCKET_ADDRESS),
        ('iSocketType', _ct.c_int),
        ('iProtocol', _ct.c_int),
    ]


class _WSAQUERYSET(_ct.Structure):
    _fields_ = [
        ('dwSize', _wt.DWORD),
        ('lpszServiceInstanceName', _wt.LPWSTR),
        ('lpServiceClassId', _ct.POINTER(_GUID)),
        ('lpVersion', _ct.c_void_p),
        ('lpszComment', _wt.LPWSTR),
        ('dwNameSpace', _wt.DWORD),
        ('lpNSProviderId', _ct.POINTER(_GUID)),
        ('lpszContext', _wt.LPWSTR),
        ('dwNumberOfProtocols', _wt.DWORD),
        ('lpafpProtocols', _ct.c_void_p),
        ('lpszQueryString', _wt.LPWSTR),
        ('dwNumberOfCsAddrs', _wt.DWORD),
        ('lpcsaBuffer', _ct.POINTER(_CSADDR_INFO)),
        ('dwOutputFlags', _wt.DWORD),
        ('lpBlob', _ct.c_void_p),
    ]


try:
    _ws2 = _ct.WinDLL('ws2_32', use_last_error=True)
    _ws2.socket.restype = _ct.c_void_p
    _ws2.socket.argtypes = [_ct.c_int, _ct.c_int, _ct.c_int]
    _ws2.bind.restype = _ct.c_int
    _ws2.bind.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.c_int]
    _ws2.listen.restype = _ct.c_int
    _ws2.listen.argtypes = [_ct.c_void_p, _ct.c_int]
    _ws2.accept.restype = _ct.c_void_p
    _ws2.accept.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.POINTER(_ct.c_int)]
    _ws2.recv.restype = _ct.c_int
    _ws2.recv.argtypes = [_ct.c_void_p, _ct.c_char_p, _ct.c_int, _ct.c_int]
    _ws2.send.restype = _ct.c_int
    _ws2.send.argtypes = [_ct.c_void_p, _ct.c_char_p, _ct.c_int, _ct.c_int]
    _ws2.closesocket.restype = _ct.c_int
    _ws2.closesocket.argtypes = [_ct.c_void_p]
    _ws2.getsockname.restype = _ct.c_int
    _ws2.getsockname.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.POINTER(_ct.c_int)]
    _ws2.WSASetServiceW.restype = _ct.c_int
    _ws2.WSASetServiceW.argtypes = [_ct.POINTER(_WSAQUERYSET), _ct.c_int, _wt.DWORD]
    _BT_NATIVE_AVAILABLE = True
except (AttributeError, OSError):
    # Not Windows, or ws2_32 missing the symbols we need (very old SKUs).
    _ws2 = None
    _BT_NATIVE_AVAILABLE = False
```

- [ ] **Step 2.2: Add the `_NativeBtSocket` wrapper, `_bt_open_native_listener`, `_bt_native_accept`, and `_bt_accept_and_serve`**

Append to the same block:

```python
class _NativeBtSocket:
    """Duck-types recv/sendall/close around a raw Winsock SOCKET handle so
    _BtSocketStream doesn't care it's not a Python socket."""

    def __init__(self, handle):
        self._h = handle

    def recv(self, n):
        buf = _ct.create_string_buffer(n)
        ret = _ws2.recv(self._h, buf, n, 0)
        if ret <= 0:
            return b''  # EOF or error — caller treats as EOF
        return bytes(buf.raw[:ret])

    def sendall(self, data):
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            chunk = bytes(view[offset:])
            ret = _ws2.send(self._h, chunk, len(chunk), 0)
            if ret <= 0:
                raise OSError(
                    f'BT send failed: WSAError={_ct.get_last_error()}')
            offset += ret

    def close(self):
        try:
            _ws2.closesocket(self._h)
        except Exception:
            pass


def _bt_open_native_listener():
    """Open + advertise + listen on an AF_BTH RFCOMM socket. Returns the
    listening socket handle, or raises OSError if the native path is
    unavailable on this machine. Caller (bt_sync_server) treats OSError as
    "fall back to COM port".

    Side effect: publishes an SDP record under the SPP UUID so Android's
    BluetoothConnection.toAddress() finds us without a fixed channel."""
    if not _BT_NATIVE_AVAILABLE:
        raise OSError('AF_BTH not available on this build')
    _stdsocket  # ensure Winsock is started (importing is sufficient)
    sock = _ws2.socket(_AF_BTH, _SOCK_STREAM, _BTHPROTO_RFCOMM)
    if sock in (None, 0) or sock == _INVALID_SOCKET:
        raise OSError(
            f'AF_BTH socket() failed: WSAError={_ct.get_last_error()}')
    addr = _SOCKADDR_BTH()
    addr.addressFamily = _AF_BTH
    addr.btAddr = 0
    addr.serviceClassId = _SPP_UUID
    addr.port = _BT_PORT_ANY
    if _ws2.bind(sock, _ct.byref(addr), _ct.sizeof(addr)) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'AF_BTH bind() failed: WSAError={err}')
    addr_len = _ct.c_int(_ct.sizeof(addr))
    if _ws2.getsockname(sock, _ct.byref(addr), _ct.byref(addr_len)) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'AF_BTH getsockname() failed: WSAError={err}')
    if _ws2.listen(sock, 1) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'AF_BTH listen() failed: WSAError={err}')
    # Publish SDP record so the phone finds us by SPP UUID.
    csa = _CSADDR_INFO()
    csa.LocalAddr.lpSockaddr = _ct.pointer(addr)
    csa.LocalAddr.iSockaddrLength = _ct.sizeof(addr)
    csa.iSocketType = _SOCK_STREAM
    csa.iProtocol = _BTHPROTO_RFCOMM
    wqs = _WSAQUERYSET()
    wqs.dwSize = _ct.sizeof(wqs)
    wqs.lpszServiceInstanceName = 'DentaCare Sync'
    wqs.lpServiceClassId = _ct.pointer(_SPP_UUID)
    wqs.dwNameSpace = _NS_BTH
    wqs.dwNumberOfCsAddrs = 1
    wqs.lpcsaBuffer = _ct.pointer(csa)
    if _ws2.WSASetServiceW(_ct.byref(wqs), _RNRSERVICE_REGISTER, 0) != 0:
        err = _ct.get_last_error()
        _ws2.closesocket(sock)
        raise OSError(f'WSASetService(REGISTER) failed: WSAError={err}')
    return sock


def _bt_close_native_listener(handle):
    """Best-effort teardown. Windows drops the SDP record when the registering
    process exits, so we just close the socket — sufficient for daemon=True."""
    try:
        if handle:
            _ws2.closesocket(handle)
    except Exception:
        pass


def _bt_native_accept(listener_handle, stop_event):
    """Block on accept() for one connection. stop_event is honored at the
    session boundary by the outer worker loop (same model the COM-port path
    uses); daemon=True kills any in-flight accept on process exit."""
    addr = _SOCKADDR_BTH()
    addr_len = _ct.c_int(_ct.sizeof(addr))
    handle = _ws2.accept(
        listener_handle, _ct.byref(addr), _ct.byref(addr_len))
    if handle is None or handle == _INVALID_SOCKET:
        return None
    return handle


def _bt_accept_and_serve(listener_handle, stop_event, db_path=None,
                         _accept_fn=None, _wrap_sock=None):
    """Accept one peer, wrap, dispatch via _bt_serve_session. Returns the
    processed flag from _bt_serve_session (False = EOF before any frame).

    _accept_fn / _wrap_sock are injectable seams for tests; defaults are the
    real Winsock accept + _NativeBtSocket."""
    accept_fn = _accept_fn or _bt_native_accept
    wrap_fn = _wrap_sock or (lambda h: _NativeBtSocket(h))
    conn_handle = accept_fn(listener_handle, stop_event)
    if conn_handle is None:
        return False
    sock = wrap_fn(conn_handle)
    stream = _BtSocketStream(sock)
    try:
        return _bt_serve_session(stream, stream, db_path=db_path)
    finally:
        try:
            sock.close()
        except Exception:
            pass
```

- [ ] **Step 2.3: Verify the module still imports + compiles cleanly**

Run: `rtk proxy python -m py_compile dental_clinic.py`
Expected: exits 0, no output.

Run: `rtk proxy python -c "import dental_clinic; print(dental_clinic._BT_NATIVE_AVAILABLE)"`
Expected: prints `True` on Windows, `False` elsewhere. No exceptions.

- [ ] **Step 2.4: Run existing tests to confirm nothing regressed**

Run: `rtk proxy python -m pytest tests/ -q`
Expected: same count as before (199), all passing.

- [ ] **Step 2.5: Commit**

```bash
git add dental_clinic.py
git commit -m "feat(bt): native AF_BTH RFCOMM listener via ctypes (no COM port)

Adds _bt_open_native_listener — binds an AF_BTH RFCOMM socket, publishes the
SPP SDP record via WSASetService so Android's BluetoothConnection.toAddress
finds us by UUID, and listens. _NativeBtSocket duck-types recv/sendall/close
so _BtSocketStream + _bt_serve_session reuse the existing session/frame-codec
logic unchanged. Untestable in isolation (radio path); the wiring into
bt_sync_server with COM-port fallback is in the next commit."
```

---

## Task 3 — Rework `bt_sync_server` for native-preferred + COM-port fallback

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\dental_clinic.py:11935-11983` (`bt_sync_server`)
- Test: `C:\Users\MSI\Desktop\clinic\tests\test_bt_worker.py` (extend)

- [ ] **Step 3.1: Write the failing tests**

Add to `tests/test_bt_worker.py` (after the existing tests; reuse the `_FakePort` class already in the file):

```python
def test_loop_prefers_native_listener_when_available(tmp_path, monkeypatch):
    """When _bt_open_native_listener returns a handle, the loop uses
    _bt_accept_and_serve and never touches _bt_open_port (COM)."""
    db = tmp_path / 'wn.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    dental_clinic.write_app_setting(cur, 'bt_sync_enabled', '1')
    conn.commit()
    conn.close()

    native_open_calls = []
    accept_serve_calls = []
    com_open_calls = []

    def fake_native_open():
        native_open_calls.append(True)
        return object()  # opaque "handle" — only passed back to accept_and_serve

    def fake_accept_and_serve(handle, stop_event, db_path=None):
        accept_serve_calls.append(handle)
        return True  # processed one frame

    def fake_com_open(port, **kwargs):
        com_open_calls.append(port)
        return _FakePort(b'')

    stop = threading.Event()
    monkeypatch.setattr(dental_clinic, '_bt_open_native_listener', fake_native_open)
    monkeypatch.setattr(dental_clinic, '_bt_accept_and_serve', fake_accept_and_serve)
    monkeypatch.setattr(dental_clinic, '_bt_close_native_listener', lambda h: None)
    monkeypatch.setattr(dental_clinic, '_bt_open_port', fake_com_open)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_SLEEP', 0.01)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_RECONNECT_SLEEP', 0.01)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_ERROR_SLEEP', 0.01)

    t = threading.Thread(target=dental_clinic.bt_sync_server, args=(stop,))
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    assert native_open_calls, 'native listener was not opened'
    assert accept_serve_calls, 'native accept-and-serve was not invoked'
    assert not com_open_calls, 'COM-port fallback was used when native was available'


def test_loop_falls_back_to_com_port_when_native_unavailable(tmp_path, monkeypatch):
    """When _bt_open_native_listener raises OSError, the loop uses the existing
    COM-port path with the configured / auto-picked port."""
    db = tmp_path / 'wf.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    dental_clinic.write_app_setting(cur, 'bt_sync_enabled', '1')
    dental_clinic.write_app_setting(cur, 'bt_sync_com_port', 'COMTEST')
    conn.commit()
    conn.close()

    def fake_native_open():
        raise OSError('AF_BTH not available on this build')

    com_open_calls = []
    fake = _FakePort(dental_clinic.encode_bt_frame({'op': 'hello', 'device_token': 'x'}))

    def fake_com_open(port, **kwargs):
        com_open_calls.append(port)
        return fake

    stop = threading.Event()
    monkeypatch.setattr(dental_clinic, '_bt_open_native_listener', fake_native_open)
    monkeypatch.setattr(dental_clinic, '_bt_open_port', fake_com_open)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_SLEEP', 0.01)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_RECONNECT_SLEEP', 0.01)
    monkeypatch.setattr(dental_clinic, '_BT_LOOP_ERROR_SLEEP', 0.01)

    t = threading.Thread(target=dental_clinic.bt_sync_server, args=(stop,))
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    assert com_open_calls == ['COMTEST'], (
        f'COM-port fallback not invoked correctly: {com_open_calls}')
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `rtk proxy python -m pytest tests/test_bt_worker.py -v -k "prefers_native or falls_back"`
Expected: both fail (function/attribute missing, or the existing loop ignores the native seam).

- [ ] **Step 3.3: Rewrite `bt_sync_server` (dental_clinic.py:11935-11983)**

Replace the existing `bt_sync_server` body with:

```python
def bt_sync_server(stop_event=None):
    """Daemon loop: each cycle, re-read settings, prefer the native AF_BTH
    listener (no Windows COM port), fall back to the existing pyserial
    COM-port path if the native one can't bind. Skipped on cloud / debug
    parent.

    Module-level _bt_server_listening reflects whichever path currently holds
    the listener open, so /api/bt/status's diagnostic stays accurate."""
    import serial as _pyserial
    global _bt_server_listening
    while stop_event is None or not stop_event.is_set():
        try:
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            enabled = read_app_setting(cur, 'bt_sync_enabled', '0') == '1'
            com_port_setting = (read_app_setting(cur, 'bt_sync_com_port', '') or '').strip()
            conn.close()
        except sqlite3.Error:
            enabled, com_port_setting = False, ''
        if not enabled:
            _bt_server_listening = False
            _bt_sleep(_BT_LOOP_SLEEP, stop_event)
            continue
        # Strategy: try the native RFCOMM listener first. Any OSError → fall
        # back to the COM-port path (today's behaviour) so legacy machines
        # don't regress.
        native_handle = None
        try:
            native_handle = _bt_open_native_listener()
        except OSError as exc:
            # Don't stamp this as a user-facing error; the fallback will run.
            _bt_record_attempt(
                op='listen', outcome='rejected',
                detail=f'native unavailable: {exc} — using COM fallback')
        if native_handle is not None:
            _bt_server_listening = True
            try:
                processed = _bt_accept_and_serve(native_handle, stop_event)
            except Exception as exc:  # noqa: BLE001
                _bt_record_error(f'{type(exc).__name__}: {exc}')
                processed = False
            finally:
                _bt_server_listening = False
                _bt_close_native_listener(native_handle)
            if processed:
                _bt_record_success()
            _bt_sleep(_BT_LOOP_RECONNECT_SLEEP, stop_event)
            continue
        # ── COM-port fallback (legacy path) ──
        port = com_port_setting or _bt_pick_default_port()
        if not port:
            _bt_server_listening = False
            _bt_record_error('no bluetooth port available')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)
            continue
        try:
            ser = _bt_open_port(port)
            _bt_server_listening = True
            try:
                with ser:
                    processed = _bt_serve_session(ser, ser)
            finally:
                _bt_server_listening = False
            if processed:
                _bt_record_success()
            _bt_sleep(_BT_LOOP_RECONNECT_SLEEP, stop_event)
        except _pyserial.SerialException as exc:
            _bt_server_listening = False
            _bt_record_error(f'serial: {exc}')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)
        except Exception as exc:  # noqa: BLE001
            _bt_server_listening = False
            _bt_record_error(f'{type(exc).__name__}: {exc}')
            _bt_sleep(_BT_LOOP_ERROR_SLEEP, stop_event)
```

- [ ] **Step 3.4: Run the new + existing tests**

Run: `rtk proxy python -m pytest tests/test_bt_worker.py -v`
Expected: all `test_bt_worker.py` tests pass (existing + 2 new).

- [ ] **Step 3.5: Run the full test suite**

Run: `rtk proxy python -m pytest tests/ -q`
Expected: 201 passed (199 baseline + 4 new in Task 1 − ?; recount as needed; key invariant: zero failures).

- [ ] **Step 3.6: Commit**

```bash
git add tests/test_bt_worker.py dental_clinic.py
git commit -m "feat(bt): bt_sync_server prefers native listener, falls back to COM port

Each cycle: try _bt_open_native_listener; on success use _bt_accept_and_serve.
On OSError (older Windows / no radio / API error) fall through to the existing
pyserial COM-port path, preserving today's behaviour as a safety net.
Two new test_bt_worker.py tests cover both branches via injected seams."
```

---

## Task 4 — Desktop Settings UI: just the toggle

The Bluetooth Sync card in the embedded HTML/JS template (in `dental_clinic.py`) loses the listener pill, paired-phones table, recent-attempts log, and the advanced COM-port disclosure. What remains: the toggle + a one-line plain error rendered **only** when `/api/bt/status` reports a `last_error`.

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\dental_clinic.py` (template strings near :3998, :4074, and the JS render block near :7260-7316)

- [ ] **Step 4.1: Locate the current BT card markup**

Run: `rtk proxy grep -n "Bluetooth Sync\|bt-sync-card\|Advanced — pick COM\|paired phones\|Recent connection log\|btSyncToggle\|btStatusPill" dental_clinic.py | head -30`
Expected: a handful of line numbers around 3998, 4074, 7260-7316.

- [ ] **Step 4.2: Reduce the card HTML to a toggle + conditional error**

Replace the entire Bluetooth Sync card markup block (find it by the `data-en="A paired phone syncs over Bluetooth…"` string at dental_clinic.py:3998 and the `<summary data-en="Advanced — pick COM port manually"` at :4074 — the card runs from the surrounding `<section>`/`<div>` open through its close) with:

```html
<section class="settings-card" id="bt-sync-card">
  <h3 data-en="Bluetooth sync" data-ar="مزامنة بلوتوث">Bluetooth sync</h3>
  <p class="muted"
     data-en="When the phone can't reach Wi-Fi or the cloud, it syncs with this PC over Bluetooth. Pair your phone in Windows Bluetooth settings once, then flip the toggle."
     data-ar="عندما لا يمكن للهاتف الوصول إلى الواي فاي أو السحابة، يقوم بالمزامنة مع هذا الحاسوب عبر البلوتوث. قم بإقران الهاتف في إعدادات بلوتوث ويندوز مرة واحدة، ثم قم بتفعيل المفتاح.">
    When the phone can't reach Wi-Fi or the cloud, it syncs with this PC over Bluetooth. Pair your phone in Windows Bluetooth settings once, then flip the toggle.
  </p>
  <label class="toggle-row">
    <input type="checkbox" id="btSyncToggle" />
    <span data-en="Bluetooth sync" data-ar="مزامنة بلوتوث">Bluetooth sync</span>
  </label>
  <div id="btSyncError" class="error-line" style="display:none;"
       role="alert" aria-live="polite"></div>
</section>
```

(The exact surrounding class names — `settings-card`, `toggle-row`, `error-line` — should match siblings in the same template. If a sibling uses different class names for cards / toggles, mirror them so the new block inherits the same styling.)

- [ ] **Step 4.3: Simplify the JS that drives the card**

Locate the JS block near dental_clinic.py:7260-7316 that today builds the `<option>` list for the advanced port dropdown and renders the listener pill / paired-phones table / recent-attempts table. Replace its render function with:

```javascript
async function renderBtCard() {
  const res = await fetch('/api/bt/status');
  if (!res.ok) return;
  const s = await res.json();
  const toggle = document.getElementById('btSyncToggle');
  const errLine = document.getElementById('btSyncError');
  if (toggle) toggle.checked = !!s.enabled;
  if (errLine) {
    if (s.last_error) {
      errLine.textContent = friendlyBtDesktopError(s.last_error);
      errLine.style.display = '';
    } else {
      errLine.textContent = '';
      errLine.style.display = 'none';
    }
  }
}

function friendlyBtDesktopError(raw) {
  // Map the (server-side) last_error string to plain language. Server errors
  // we know about: "no bluetooth port available", "serial: ...", "OSError: ...".
  // Everything else falls through to a friendly catch-all.
  const r = (raw || '').toLowerCase();
  const ar = (document.documentElement.getAttribute('lang') || 'en') === 'ar';
  if (r.includes('no bluetooth port') || r.includes('af_bth')) {
    return ar
      ? 'تعذّر بدء البلوتوث — تحقق من تشغيل البلوتوث في هذا الحاسوب.'
      : "Bluetooth couldn't start — is this PC's Bluetooth turned on?";
  }
  if (r.includes('serial')) {
    return ar
      ? 'تعذّر فتح منفذ البلوتوث.'
      : "Couldn't open the Bluetooth port.";
  }
  return ar ? 'حدث خطأ في مزامنة البلوتوث.' : 'Bluetooth sync hit an error.';
}

async function setBtEnabled(enabled) {
  await fetch('/api/bt/configure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  renderBtCard();
}

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('btSyncToggle');
  if (toggle) toggle.addEventListener('change', e => setBtEnabled(e.target.checked));
  renderBtCard();
  setInterval(renderBtCard, 10000);
});
```

Delete (or comment out) the old render code that built `available_ports` `<option>` lists, the paired-phones table, the recent-attempts table, and the listener pill. The diagnostic fields keep flowing on `/api/bt/status`; the UI just stops rendering them.

- [ ] **Step 4.4: Compile + run tests to confirm no Python regression**

Run: `rtk proxy python -m py_compile dental_clinic.py`
Expected: exits 0.

Run: `rtk proxy python -m pytest tests/ -q`
Expected: still all green.

- [ ] **Step 4.5: Manual smoke (one minute)**

Run from a second terminal: `rtk proxy python dental_clinic.py` (source mode), open `http://localhost:5000/`, log in, navigate to Settings, locate the **Bluetooth sync** card. Confirm:
- Only the toggle is visible. No listener pill, paired-phones table, connection log, or COM-port dropdown.
- Flipping the toggle still POSTs `/api/bt/configure`.
- No error line is shown in the default case.

If the toggle styling doesn't match siblings, adjust class names in Step 4.2.

- [ ] **Step 4.6: Commit**

```bash
git add dental_clinic.py
git commit -m "feat(bt-ui): desktop card reduced to a single toggle

Removes the listener pill, paired-phones table, recent-attempts log, and the
advanced COM-port dropdown from Settings → Bluetooth sync. A single plain-
language line appears only when /api/bt/status reports last_error. The
diagnostic data still populates server-side and remains on /api/bt/status."
```

---

## Task 5 — Installer: drop COM-port provisioning from the critical path

The native listener advertises its own SDP record, so an Incoming COM port is no longer needed. The provisioning script stays in the repo (it's still useful when the COM-port fallback runs on a machine that needs the legacy port), but the installer no longer gates setup on it and no longer pops the follow-up message box.

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\installer\DentaCare.iss`

- [ ] **Step 5.1: Find the current provisioning hook**

Run: `rtk proxy grep -n "provision_bt\|Bluetooth COM\|exit code 2\|user-action" installer/DentaCare.iss`
Expected: one or two lines referencing the script + the follow-up MsgBox.

- [ ] **Step 5.2: Remove the provisioning step from the install flow**

In `installer/DentaCare.iss`, delete (or comment out with `;`) the `[Run]` entry that invokes `provision_bt.ps1` and the `MsgBox`/`Code` block that surfaces the "user action required" notice. Leave the file `provision_bt.ps1` itself in `installer/` — it remains useful for an admin to run manually if the native path can't bind on their machine and they want to force the COM-port fallback to work.

- [ ] **Step 5.3: Spot-check the installer file**

Run: `rtk proxy grep -n "provision_bt\|Bluetooth COM" installer/DentaCare.iss`
Expected: no hits (or only an explanatory comment).

- [ ] **Step 5.4: Commit**

```bash
git add installer/DentaCare.iss
git commit -m "chore(installer): drop Incoming-COM-port provisioning from install flow

The native AF_BTH listener (dental_clinic.py) publishes its own SPP SDP
record, so the Incoming COM port is no longer required. provision_bt.ps1
stays in the tree for the rare COM-port fallback case but is no longer
invoked by the installer."
```

---

## Task 6 — Mobile: `btMessageFor` + `classifyBtError` (TDD, pure)

**Files:**
- Create: `C:\Users\MSI\Desktop\clinic\clinic_mobile_app\lib\utils\bt_error_message.dart`
- Test: `C:\Users\MSI\Desktop\clinic\clinic_mobile_app\test\bt_error_message_test.dart`

- [ ] **Step 6.1: Write the failing test**

Create `clinic_mobile_app/test/bt_error_message_test.dart`:

```dart
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:clinic_mobile_app/utils/bt_error_message.dart';

void main() {
  group('btMessageFor — English', () {
    test('phoneBtOff', () {
      expect(btMessageFor(BtFailure.phoneBtOff, 'en'),
          'Turn on Bluetooth to sync.');
    });
    test('permissionDenied', () {
      expect(btMessageFor(BtFailure.permissionDenied, 'en'),
          'Allow Bluetooth permission in Android settings to sync.');
    });
    test('noPeerSelected', () {
      expect(btMessageFor(BtFailure.noPeerSelected, 'en'),
          'Choose your clinic PC first.');
    });
    test('notBonded', () {
      expect(btMessageFor(BtFailure.notBonded, 'en'),
          "Pair the clinic PC in your phone's Bluetooth settings first.");
    });
    test('peerUnreachable', () {
      expect(btMessageFor(BtFailure.peerUnreachable, 'en'),
          "Couldn't reach the clinic PC. Make sure it's on, nearby, and its Bluetooth is on.");
    });
    test('unknown', () {
      expect(btMessageFor(BtFailure.unknown, 'en'),
          'Bluetooth sync hit a problem. Please try again.');
    });
  });

  group('btMessageFor — Arabic', () {
    test('phoneBtOff (ar)', () {
      expect(btMessageFor(BtFailure.phoneBtOff, 'ar'),
          'قم بتشغيل البلوتوث للمزامنة.');
    });
    test('permissionDenied (ar)', () {
      expect(btMessageFor(BtFailure.permissionDenied, 'ar'),
          'يرجى السماح بإذن البلوتوث في إعدادات أندرويد للمزامنة.');
    });
    test('noPeerSelected (ar)', () {
      expect(btMessageFor(BtFailure.noPeerSelected, 'ar'),
          'اختر حاسوب العيادة أولاً.');
    });
    test('notBonded (ar)', () {
      expect(btMessageFor(BtFailure.notBonded, 'ar'),
          'قم بإقران حاسوب العيادة في إعدادات بلوتوث الهاتف أولاً.');
    });
    test('peerUnreachable (ar)', () {
      expect(btMessageFor(BtFailure.peerUnreachable, 'ar'),
          'تعذّر الوصول إلى حاسوب العيادة. تأكد من أنه قيد التشغيل وقريب والبلوتوث مفعّل.');
    });
    test('unknown (ar)', () {
      expect(btMessageFor(BtFailure.unknown, 'ar'),
          'حدثت مشكلة في مزامنة البلوتوث. يرجى المحاولة مرة أخرى.');
    });
  });

  group('classifyBtError', () {
    test('TimeoutException → peerUnreachable', () {
      expect(classifyBtError(TimeoutException('connect timed out')),
          BtFailure.peerUnreachable);
    });
    test('connect failed string → peerUnreachable', () {
      expect(classifyBtError(Exception('BT connect failed: PlatformException')),
          BtFailure.peerUnreachable);
    });
    test('read failed string → peerUnreachable', () {
      expect(classifyBtError(Exception('read failed, socket might closed')),
          BtFailure.peerUnreachable);
    });
    test('generic Exception → unknown', () {
      expect(classifyBtError(Exception('something else entirely')),
          BtFailure.unknown);
    });
    test('null/empty → unknown', () {
      expect(classifyBtError(''), BtFailure.unknown);
    });
  });
}
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter test test/bt_error_message_test.dart`
Expected: all fail — module / functions don't exist yet.

- [ ] **Step 6.3: Implement the helper**

Create `clinic_mobile_app/lib/utils/bt_error_message.dart`:

```dart
/// Classified Bluetooth-sync failure. The caller picks the concrete enum value
/// based on what it knows (BT on/off, permission, peer chosen, etc.). The one
/// catch-all — `peerUnreachable` — covers everything classic BT can't tell
/// apart from the phone side (PC's BT off, PC asleep, app closed, out of range).
enum BtFailure {
  phoneBtOff,
  permissionDenied,
  noPeerSelected,
  notBonded,
  peerUnreachable,
  unknown,
}

/// Map a thrown exception/error from the BT connection or session path to a
/// `BtFailure`. Used in catch blocks where the caller doesn't already know the
/// failure category. Heuristic — checks for the well-known strings the
/// flutter_bluetooth_serial layer surfaces; everything else → unknown.
BtFailure classifyBtError(Object error) {
  if (error is TimeoutException) return BtFailure.peerUnreachable;
  final s = error.toString().toLowerCase();
  if (s.contains('connect failed') ||
      s.contains('read failed') ||
      s.contains('socket might closed') ||
      s.contains('connection refused') ||
      s.contains('host is down') ||
      s.contains('no route')) {
    return BtFailure.peerUnreachable;
  }
  return BtFailure.unknown;
}

/// Plain-language message for a given failure, in the caller's locale.
/// `locale` follows the app's `'en'` / `'ar'` convention used elsewhere.
String btMessageFor(BtFailure kind, String locale) {
  final ar = locale == 'ar';
  switch (kind) {
    case BtFailure.phoneBtOff:
      return ar
          ? 'قم بتشغيل البلوتوث للمزامنة.'
          : 'Turn on Bluetooth to sync.';
    case BtFailure.permissionDenied:
      return ar
          ? 'يرجى السماح بإذن البلوتوث في إعدادات أندرويد للمزامنة.'
          : 'Allow Bluetooth permission in Android settings to sync.';
    case BtFailure.noPeerSelected:
      return ar
          ? 'اختر حاسوب العيادة أولاً.'
          : 'Choose your clinic PC first.';
    case BtFailure.notBonded:
      return ar
          ? 'قم بإقران حاسوب العيادة في إعدادات بلوتوث الهاتف أولاً.'
          : "Pair the clinic PC in your phone's Bluetooth settings first.";
    case BtFailure.peerUnreachable:
      return ar
          ? 'تعذّر الوصول إلى حاسوب العيادة. تأكد من أنه قيد التشغيل وقريب والبلوتوث مفعّل.'
          : "Couldn't reach the clinic PC. Make sure it's on, nearby, and its Bluetooth is on.";
    case BtFailure.unknown:
      return ar
          ? 'حدثت مشكلة في مزامنة البلوتوث. يرجى المحاولة مرة أخرى.'
          : 'Bluetooth sync hit a problem. Please try again.';
  }
}
```

The `TimeoutException` import path matters for the test: it's in `dart:async`. Add `import 'dart:async';` at the top of `bt_error_message.dart`:

```dart
import 'dart:async';

enum BtFailure { ... }
```

- [ ] **Step 6.4: Run test to verify it passes**

Run: `cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter test test/bt_error_message_test.dart`
Expected: all green.

- [ ] **Step 6.5: Run the full Flutter suite + analyzer**

Run: `cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter analyze && flutter test`
Expected: `No issues found!` and all tests pass.

- [ ] **Step 6.6: Commit**

```bash
git add clinic_mobile_app/lib/utils/bt_error_message.dart clinic_mobile_app/test/bt_error_message_test.dart
git commit -m "feat(mobile): btMessageFor + classifyBtError plain-language helper

Pure function: classifyBtError maps thrown exceptions/timeouts to a
BtFailure enum; btMessageFor renders bilingual EN/AR plain-language text
for each kind. The one catch-all category — peerUnreachable — covers
everything classic BT can't distinguish from the phone side."
```

---

## Task 7 — Wire mobile error mapping into entry points; remove COM-port tip

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\clinic_mobile_app\lib\services\bluetooth_sync_service.dart` (around lines 140-150, 168-172)
- Modify: `C:\Users\MSI\Desktop\clinic\clinic_mobile_app\lib\state\app_state.dart` (the `syncViaBluetoothNow` + auto-tick error paths that set `btLastError`)
- Modify: `C:\Users\MSI\Desktop\clinic\clinic_mobile_app\lib\screens\settings_screen.dart:611-651` (`_pickBondedPeer`) and `:699-720` (`_BtErrorBanner`)

- [ ] **Step 7.1: Strip raw `$e` from `bluetooth_sync_service.dart`**

Open `clinic_mobile_app/lib/services/bluetooth_sync_service.dart`.

Replace the strings produced by `_autoPair` and `_runSessionOnce` so they no longer interpolate raw exception text into anything the UI will render. Concretely:

Lines 140-150 — `_autoPair` catch block — change:

```dart
} on TimeoutException catch (e) {
  final detail = e.message ?? '';
  return _AutoPairOutcome.failure(
      'BT connect timed out (10s) — is the clinic PC listening? $detail'
          .trim());
} on Exception catch (e) {
  return _AutoPairOutcome.failure('BT connect failed: $e');
} catch (e) {
  return _AutoPairOutcome.failure('BT connect failed: $e');
}
```

to:

```dart
} on TimeoutException catch (_) {
  return _AutoPairOutcome.failure('peer-unreachable:timeout');
} on Exception catch (e) {
  return _AutoPairOutcome.failure('peer-unreachable:${e.runtimeType}');
} catch (e) {
  return _AutoPairOutcome.failure('peer-unreachable:${e.runtimeType}');
}
```

(The string is now a stable token the caller pattern-matches via `classifyBtError`. Raw exception text never enters the user-facing pipeline.)

Lines 168-172 — `_runSessionOnce` catch block — change:

```dart
} catch (e) {
  return BtSessionResult.failure(e.toString());
}
```

to:

```dart
} catch (e) {
  return BtSessionResult.failure('peer-unreachable:${e.runtimeType}');
}
```

- [ ] **Step 7.2: Update `app_state.dart` to render via `btMessageFor`**

Open `clinic_mobile_app/lib/state/app_state.dart`. Find every assignment to `btLastError` (or the equivalent field driving `_BtErrorBanner`). For each, route the error through `btMessageFor`:

```dart
import 'package:clinic_mobile_app/utils/bt_error_message.dart';

// ... inside the class ...

void _setBtError(BtFailure kind) {
  btLastError = btMessageFor(kind, locale); // `locale` is the existing 'en'/'ar' field
  notifyListeners();
}
```

Replace catch blocks of the form `btLastError = e.toString()` with:

```dart
btLastError = btMessageFor(classifyBtError(e), locale);
notifyListeners();
```

…and replace the explicit error states in the BT auto-tick / manual-sync paths with the right `BtFailure` value:

- "no peer chosen" → `BtFailure.noPeerSelected`
- "BT off / requestEnable returned false" → `BtFailure.phoneBtOff`
- "permission denied" → `BtFailure.permissionDenied`
- "not bonded" → `BtFailure.notBonded`
- any uncaught exception in the BT path → `classifyBtError(e)`

- [ ] **Step 7.3: Update `settings_screen.dart:611-651` (`_pickBondedPeer`) and `:699-720` (`_BtErrorBanner`)**

Open `clinic_mobile_app/lib/screens/settings_screen.dart`.

In `_pickBondedPeer` (around line 611), replace the existing literal strings:

```dart
snack('Bluetooth permission denied — grant it in Android settings', ...);
```

with:

```dart
snack(btMessageFor(BtFailure.permissionDenied, app.locale), ...);
```

Similarly for:
- `'Turn Bluetooth on, then try again'` → `btMessageFor(BtFailure.phoneBtOff, app.locale)`
- `'Could not access Bluetooth: $e'` → `btMessageFor(classifyBtError(e), app.locale)`
- `'No bonded devices — pair in Android Bluetooth settings first'` → `btMessageFor(BtFailure.notBonded, app.locale)`

For `_BtErrorBanner` (around line 699-720): delete the COM-port "tip" block (the `'Tip: on the clinic PC, open Settings → Bluetooth Sync, check the COM port pill is green.'` line and its surrounding widget). The banner now renders only `app.btLastError` (which is already friendly text after Step 7.2).

- [ ] **Step 7.4: Add the import where needed**

At the top of `settings_screen.dart` and `app_state.dart`, add (if not already present):

```dart
import 'package:clinic_mobile_app/utils/bt_error_message.dart';
```

- [ ] **Step 7.5: Run analyzer + tests**

Run: `cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter analyze`
Expected: `No issues found!` (fix any reported lints inline).

Run: `cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter test`
Expected: all tests pass (existing 50 + new `bt_error_message_test.dart`).

- [ ] **Step 7.6: Commit**

```bash
git add clinic_mobile_app/lib/services/bluetooth_sync_service.dart clinic_mobile_app/lib/state/app_state.dart clinic_mobile_app/lib/screens/settings_screen.dart
git commit -m "feat(mobile): plain-language BT errors wired into every entry point

Raw PlatformException / exception strings no longer reach the user. Auto-pair
+ session catch blocks produce stable 'peer-unreachable:<Type>' tokens which
classifyBtError → btMessageFor renders bilingually. The COM-port 'tip' under
the Bluetooth peer card is gone — it referenced desktop internals that no
longer exist."
```

---

## Task 8 — README update + full verification + push

**Files:**
- Modify: `C:\Users\MSI\Desktop\clinic\README.md` (Bluetooth sync section + Windows BT setup gotcha + test counts + file-tree blurb if needed)

- [ ] **Step 8.1: Update the Bluetooth-sync section of README**

Open `C:\Users\MSI\Desktop\clinic\README.md`. Locate the **Bluetooth sync (offline fallback)** section (it starts around the "When the phone can reach neither the LAN nor the cloud node…" sentence). Edit it so that:

- The "auto-picks the right COM port" / status pill / Listener indicator / paired-phones table / recent connection log / Advanced dropdown paragraph is removed.
- A short replacement: "On the PC, flip the **Bluetooth sync** toggle in Settings — that's it. The PC registers its own Bluetooth service (no Windows COM port to create); the phone finds it by standard Serial Port UUID. On the phone, **Settings → Bluetooth peer** → 'Pick clinic PC' → choose the bonded desktop."
- The **Windows BT setup gotcha** paragraph (about *Incoming COM port* + the `read failed… ret -1` error + `provision_bt.ps1`) is reduced to a one-line note: "Earlier builds required a manual *Incoming COM port* setup in Windows; this is no longer needed — the desktop registers its own Bluetooth service directly. A `provision_bt.ps1` script is still shipped for the rare COM-port fallback path."
- Update the Bluetooth sync error references: the desktop card surfaces only a single plain message on failure; the mobile card produces bilingual plain-language messages via `lib/utils/bt_error_message.dart` (mention this in the file-tree blurb where the other mobile services are listed).

- [ ] **Step 8.2: Refresh test counts**

After the previous tasks added: 4 desktop tests (Task 1), 2 desktop tests (Task 3), and ~17 Dart tests (Task 6), the counts shift. Re-run the suites to get current numbers:

Run: `rtk proxy python -m pytest tests/ -q | tail -3`
Note the passed count (call it `P_NEW`).

Run: `cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter test 2>&1 | tail -2`
Note the "+N: All tests passed!" count (call it `F_NEW`).

In `README.md` replace the "199 tests across 27 suites" and "50 tests" figures with `P_NEW` / `F_NEW` and the corresponding suite count. Mention the two new suites: `test_bt_socket_stream.py` (desktop) and `bt_error_message_test.dart` (mobile).

- [ ] **Step 8.3: Full verification**

Run all three in sequence:

```bash
rtk proxy python -m py_compile dental_clinic.py
rtk proxy python -m pytest tests/ -q
cd "C:\Users\MSI\Desktop\clinic\clinic_mobile_app" && flutter analyze && flutter test
```

Expected:
- `py_compile`: exits 0, no output.
- `pytest`: all green; count matches what you wrote into README.
- `flutter analyze`: `No issues found!`
- `flutter test`: all green; count matches what you wrote into README.

- [ ] **Step 8.4: Commit + push**

```bash
git add README.md
git commit -m "docs: README — zero-port Bluetooth sync; refresh test counts

Reflect the native AF_BTH listener (no Incoming COM port to create), the
toggle-only desktop UI, and the plain-language mobile error helper. Test
counts refreshed for the new test_bt_socket_stream.py + bt_error_message_test
suites."
git push origin main
```

- [ ] **Step 8.5: Note the hardware smoke gate**

This plan does not — and cannot — verify the end-to-end radio path. Surface a clear ask to the user once everything above is merged:

> "Implementation is in. The end-to-end phone↔PC sync over the native listener (with Wi-Fi off) still needs your on-device smoke test. Steps:
> 1. Pair phone+PC in Windows Bluetooth settings (normal 'Add a Bluetooth device').
> 2. On the desktop, Settings → flip the **Bluetooth sync** toggle on.
> 3. On the phone, Settings → 'Choose your clinic PC' → pick the desktop.
> 4. Turn the phone's Wi-Fi off.
> 5. Tap **Sync now via Bluetooth** on the phone.
> 6. Confirm the first cycle issues a token (silently) and a second cycle moves a real record (e.g. a new patient) both directions.
> If anything looks off, send back the desktop's `last_error` (from `/api/bt/status`) and the snack/banner message from the phone."

---

## Self-review

**Spec coverage:**
- Native RFCOMM listener — Tasks 1, 2, 3. ✓
- COM-port fallback preserved — Task 3 (test_loop_falls_back_to_com_port_when_native_unavailable). ✓
- Desktop UI: toggle + conditional error — Task 4. ✓
- Mobile UI: keep toggle / picker / sync button; remove COM-port tip — Task 7. ✓
- `btErrorMessage` (`btMessageFor` + `classifyBtError`) — Task 6 (TDD) + Task 7 (wiring). ✓
- Installer no longer gates on COM port — Task 5. ✓
- Diagnostics kept server-side but UI removed — Task 4 (UI removal; `/api/bt/status` payload unchanged). ✓
- Hardware smoke gate honestly surfaced — Task 8 Step 5. ✓
- Open question (truly silent desktop vs. conditional error line) — implemented as "conditional error line" per the design default; flip in Step 4.3's `renderBtCard` to `errLine.style.display = 'none'` always if the user vetoes.

**Type / naming consistency:**
- `_bt_open_native_listener`, `_bt_accept_and_serve`, `_bt_close_native_listener`, `_BtSocketStream`, `_NativeBtSocket`, `_BT_NATIVE_AVAILABLE`: same identifiers used across Tasks 1–3. ✓
- `BtFailure` enum cases (`phoneBtOff`, `permissionDenied`, `noPeerSelected`, `notBonded`, `peerUnreachable`, `unknown`): same in Tasks 6 + 7. ✓
- `classifyBtError(Object) → BtFailure`, `btMessageFor(BtFailure, String) → String`: same signatures across tests + implementation + wiring.

**Placeholder scan:** no TBD/TODO; every step has concrete code or concrete commands.
