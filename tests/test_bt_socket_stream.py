"""_BtSocketStream wraps a socket-like object so _bt_serve_session reads/writes
through the same length-prefixed frame codec it uses for the COM-port path."""

import io

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
