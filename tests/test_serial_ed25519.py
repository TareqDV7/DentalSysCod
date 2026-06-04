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


import dental_clinic


def test_dental_verifier_accepts_valid_token(monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    token = serial_generator.sign_serial_token(
        {'serial': 'DENTAL-AAAA-0001', 'max_devices': 3,
         'grace_until': '2999-01-01T00:00:00Z'}, priv_b64)
    ok, reason, payload = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', token)
    assert ok is True, reason
    assert payload['max_devices'] == 3


def test_dental_verifier_rejects_random(monkeypatch):
    _, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    ok, reason, payload = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', 'garbage')
    assert ok is False and payload is None


def test_dental_verifier_rejects_serial_mismatch(monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    token = serial_generator.sign_serial_token({'serial': 'OTHER-0002'}, priv_b64)
    ok, reason, _ = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', token)
    assert ok is False


def test_dental_verifier_malformed_grace_is_rejected(monkeypatch):
    priv_b64, pub_b64 = serial_generator.generate_keypair()
    monkeypatch.setattr(dental_clinic, '_SERIAL_PUBLIC_KEY_B64', pub_b64)
    token = serial_generator.sign_serial_token(
        {'serial': 'DENTAL-AAAA-0001', 'grace_until': 'never'}, priv_b64)
    ok, reason, _ = dental_clinic._verify_serial_token('DENTAL-AAAA-0001', token)
    assert ok is False  # malformed grace must hard-fail, not silently pass


def test_load_private_seed(tmp_path):
    import json
    priv_b64, _ = serial_generator.generate_keypair()
    f = tmp_path / 'key.json'
    f.write_text(json.dumps({'alg': 'ed25519', 'private': priv_b64}))
    assert serial_generator.load_private_seed(str(f)) == priv_b64


def test_no_demo_key_fallback(tmp_path):
    # A missing key file must NOT silently sign with a baked-in demo key.
    with pytest.raises((SystemExit, FileNotFoundError, ValueError)):
        serial_generator.load_private_seed(str(tmp_path / 'nope.json'))
