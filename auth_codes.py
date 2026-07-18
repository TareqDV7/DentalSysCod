"""OTP auth codes + one-time admin recovery codes. Cursor-level pure
functions, mirroring permissions.py: no connection management here.
Hashing is pbkdf2:sha256 explicitly (frozen-exe rule — see
dental_clinic.PASSWORD_HASH_METHOD)."""
import secrets
import string
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
_HASH_METHOD = 'pbkdf2:sha256'
_RECOVERY_ALPHABET = string.ascii_uppercase + string.digits


def _now():
    return datetime.utcnow()


def issue_code(cursor, user_id, purpose):
    """Create a fresh 6-digit code for (user, purpose); voids any prior
    active codes so only the newest one works. Returns plaintext code —
    caller emails it and must never store it."""
    cursor.execute(
        'UPDATE auth_codes SET consumed = 1 WHERE user_id = ? AND purpose = ? AND consumed = 0',
        (user_id, purpose))
    code = f'{secrets.randbelow(1000000):06d}'
    expires = (_now() + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(timespec='seconds')
    cursor.execute(
        'INSERT INTO auth_codes (user_id, purpose, code_hash, expires_at) VALUES (?, ?, ?, ?)',
        (user_id, purpose, generate_password_hash(code, method=_HASH_METHOD), expires))
    return code


def verify_code(cursor, user_id, purpose, code):
    """Returns 'ok' (and consumes) | 'expired' | 'invalid' | 'locked'."""
    row = cursor.execute(
        'SELECT id, code_hash, expires_at, attempts FROM auth_codes '
        'WHERE user_id = ? AND purpose = ? AND consumed = 0 '
        'ORDER BY id DESC LIMIT 1', (user_id, purpose)).fetchone()
    if not row:
        return 'invalid'
    code_id, code_hash, expires_at, attempts = row[0], row[1], row[2], row[3]
    if attempts >= MAX_ATTEMPTS:
        return 'locked'
    if _now().isoformat(timespec='seconds') > expires_at:
        return 'expired'
    if not check_password_hash(code_hash, str(code or '')):
        cursor.execute('UPDATE auth_codes SET attempts = attempts + 1 WHERE id = ?', (code_id,))
        return 'locked' if attempts + 1 >= MAX_ATTEMPTS else 'invalid'
    cursor.execute('UPDATE auth_codes SET consumed = 1 WHERE id = ?', (code_id,))
    return 'ok'


def issue_recovery_code(cursor):
    """One-time clinic recovery code XXXX-XXXX-XXXX-XXXX. Voids prior unused
    codes. Returns plaintext exactly once — show/print, never store."""
    cursor.execute("UPDATE admin_recovery SET used_at = 'voided' WHERE used_at IS NULL")
    groups = [''.join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(4)]
    code = '-'.join(groups)
    cursor.execute('INSERT INTO admin_recovery (code_hash) VALUES (?)',
                   (generate_password_hash(code, method=_HASH_METHOD),))
    return code


def redeem_recovery_code(cursor, code):
    row = cursor.execute(
        'SELECT id, code_hash FROM admin_recovery WHERE used_at IS NULL '
        'ORDER BY id DESC LIMIT 1').fetchone()
    normalized = (code or '').strip().upper()
    if not row or not check_password_hash(row[1], normalized):
        return False
    cursor.execute("UPDATE admin_recovery SET used_at = datetime('now') WHERE id = ?", (row[0],))
    return True
