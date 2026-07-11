"""Encrypt/decrypt for the two credential fields (SMTP password, SMS API
key) that would otherwise sit as plaintext columns on the cloud node's
unencrypted per-clinic databases (see design spec Decision 4)."""
import pytest
from cryptography.fernet import Fernet

import reminder_crypto


@pytest.fixture()
def key(monkeypatch):
    k = Fernet.generate_key().decode()
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', k)
    return k


def test_encrypt_then_decrypt_roundtrips(key):
    ciphertext = reminder_crypto.encrypt('hunter2')
    assert ciphertext != 'hunter2'
    assert reminder_crypto.decrypt(ciphertext) == 'hunter2'


def test_encrypt_raises_without_key(monkeypatch):
    monkeypatch.delenv('CLINIC_CLOUD_REMINDER_KEY', raising=False)
    with pytest.raises(RuntimeError):
        reminder_crypto.encrypt('hunter2')


def test_decrypt_raises_with_wrong_key(key):
    ciphertext = reminder_crypto.encrypt('hunter2')
    import os
    os.environ['CLINIC_CLOUD_REMINDER_KEY'] = Fernet.generate_key().decode()
    with pytest.raises(RuntimeError):
        reminder_crypto.decrypt(ciphertext)


def test_encrypt_raises_on_malformed_key(monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', 'not-a-valid-fernet-key')
    with pytest.raises(RuntimeError):
        reminder_crypto.encrypt('hunter2')
