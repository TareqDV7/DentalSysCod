"""Application-layer encryption for the two reminder credential fields
(SMTP password, SMS API key). Cloud-side databases are plaintext by
explicit prior scope decision (encryption-at-rest PR #23 covered the
desktop DB only) — these two fields are live third-party account
credentials, not clinic patient data, so they get their own narrow
encryption rather than reopening that scope decision.

No demo-key fallback: a missing or malformed CLINIC_CLOUD_REMINDER_KEY
fails loudly, matching this codebase's existing convention (serial_generator.py,
encryption_key.py) of never silently falling back to a guessable default.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    raw = os.environ.get('CLINIC_CLOUD_REMINDER_KEY', '').strip()
    if not raw:
        raise RuntimeError(
            'CLINIC_CLOUD_REMINDER_KEY is not set. Generate one with '
            '`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` '
            'and set it as an env var on the cloud node.'
        )
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'CLINIC_CLOUD_REMINDER_KEY is not a valid Fernet key: {exc}') from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise RuntimeError('Could not decrypt reminder credential — wrong key or corrupted value') from exc
