import base64
import pytest
import serial_generator


def test_generate_keypair_roundtrips():
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    assert isinstance(priv_b64, str) and isinstance(pub_b64, str)
    # 32-byte raw seed / public key
    assert len(base64.b64decode(priv_b64)) == 32
    assert len(base64.b64decode(pub_b64)) == 32


def test_sign_and_verify_token():
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    payload = {'v': 2, 'serial': 'DENTAL-AAAA-0001', 'max_devices': 3}
    token = serial_generator.sign_serial_token(payload, priv_b64)
    assert token.count('.') == 1
    ok, got = serial_generator.verify_serial_token(token, pub_b64)
    assert ok is True
    assert got['serial'] == 'DENTAL-AAAA-0001'


def test_tampered_token_fails():
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    token = serial_generator.sign_serial_token({'serial': 'X'}, priv_b64)
    payload_part, sig_part = token.split('.')
    bad = base64.urlsafe_b64encode(b'{"serial":"Y"}').decode().rstrip('=')
    ok, _ = serial_generator.verify_serial_token(f'{bad}.{sig_part}', pub_b64)
    assert ok is False


def test_random_string_fails():
    _, pub_b64 = serial_generator.generate_keypair()
    ok, _ = serial_generator.verify_serial_token('not-a-token', pub_b64)
    assert ok is False


def test_wrong_key_fails():
    priv1, _ = serial_generator.generate_keypair()
    _, pub2 = serial_generator.generate_keypair()
    token = serial_generator.sign_serial_token({'serial': 'X'}, priv1)
    ok, _ = serial_generator.verify_serial_token(token, pub2)
    assert ok is False


def test_sign_with_bad_seed_raises():
    with pytest.raises(Exception):
        serial_generator.sign_serial_token({'serial': 'X'}, 'not-valid-base64-seed!!')
