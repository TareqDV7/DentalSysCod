"""DPAPI-protected encryption key for the clinic database.

The key is generated once and stored DPAPI-protected in machine scope
(CRYPTPROTECT_LOCAL_MACHINE) — not user scope — because the interactive
desktop app and the installed background Windows service may run under
different Windows execution contexts (the logged-in user vs. a service
account), and both must be able to unprotect the same key without
prompting anyone. See docs/superpowers/specs/2026-07-07-security-hardening-
rbac-design.md, Decision 6.
"""
import os
from pathlib import Path

KEY_FILENAME = 'encryption.key'
_KEY_BYTES = 32
_CRYPTPROTECT_LOCAL_MACHINE = 0x4

# Test-only escape hatch: win32crypt has no Linux/macOS build at all, so
# ubuntu-latest CI can't import it. Off by default everywhere, including in
# the frozen Windows build — nothing in production ever sets this env var.
# tests/conftest.py sets it (only on non-Windows) before dental_clinic is
# imported, which also propagates to any subprocess a test spawns via
# env={**os.environ, ...} (see tests/test_service_mode.py). This is not a
# substitute for real DPAPI validation — that's Task 1's frozen-build spike
# — it just lets the rest of the suite exercise real SQLCipher (genuine
# manylinux wheels, no stub needed) through get_db_connection() on Linux.
_FAKE_DPAPI = os.environ.get('CLINIC_TEST_FAKE_DPAPI') == '1'


def _protect(raw_bytes):
    if _FAKE_DPAPI:
        return bytes(b ^ 0xFF for b in raw_bytes)
    import win32crypt
    blob = win32crypt.CryptProtectData(
        raw_bytes, 'DentaCare DB encryption key', None, None, None,
        _CRYPTPROTECT_LOCAL_MACHINE)
    return bytes(blob)


def _unprotect(blob):
    if _FAKE_DPAPI:
        return bytes(b ^ 0xFF for b in blob)
    import win32crypt
    _, raw = win32crypt.CryptUnprotectData(
        blob, None, None, None, _CRYPTPROTECT_LOCAL_MACHINE)
    return bytes(raw)


def get_or_create_key(data_dir: Path) -> bytes:
    """Return the raw 32-byte database encryption key, generating and
    DPAPI-protecting a new one on first call for this data_dir."""
    key_path = Path(data_dir) / KEY_FILENAME
    if key_path.exists():
        protected = key_path.read_bytes()
        return _unprotect(protected)
    raw_key = os.urandom(_KEY_BYTES)
    protected = _protect(raw_key)
    key_path.write_bytes(protected)
    return raw_key
