"""DPAPI-protected encryption key generation and retrieval.

win32crypt is Windows-only and not meaningfully mockable across platforms in
a way that proves anything real, so these tests monkeypatch
encryption_key._protect/_unprotect with a reversible XOR stand-in that
exercises the exact same code paths (generate-once, persist, re-read,
never regenerate) without depending on the real Windows DPAPI call. The
real DPAPI call itself was already validated against a frozen build in
Task 1's spike and is a single one-line call in this module (Step 3) —
there is nothing else in it worth a live Windows-only test for.
"""
import pytest

import encryption_key


@pytest.fixture(autouse=True)
def fake_dpapi(monkeypatch):
    def _fake_protect(raw_bytes):
        return bytes(b ^ 0xFF for b in raw_bytes)

    def _fake_unprotect(blob):
        return bytes(b ^ 0xFF for b in blob)

    monkeypatch.setattr(encryption_key, '_protect', _fake_protect)
    monkeypatch.setattr(encryption_key, '_unprotect', _fake_unprotect)


def test_first_call_generates_and_persists_a_32_byte_key(tmp_path):
    key = encryption_key.get_or_create_key(tmp_path)
    assert len(key) == 32
    assert (tmp_path / encryption_key.KEY_FILENAME).exists()


def test_second_call_returns_the_same_key_not_a_new_one(tmp_path):
    key1 = encryption_key.get_or_create_key(tmp_path)
    key2 = encryption_key.get_or_create_key(tmp_path)
    assert key1 == key2


def test_key_file_on_disk_is_not_the_raw_key(tmp_path):
    key = encryption_key.get_or_create_key(tmp_path)
    on_disk = (tmp_path / encryption_key.KEY_FILENAME).read_bytes()
    assert on_disk != key  # must be the protected blob, not raw key material
