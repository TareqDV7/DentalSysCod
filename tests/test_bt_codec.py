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
