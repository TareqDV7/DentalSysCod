import sqlite3

import pytest

import auth_codes


@pytest.fixture
def cur():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE auth_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0, consumed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE admin_recovery (id INTEGER PRIMARY KEY AUTOINCREMENT, code_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, used_at TEXT);
    ''')
    yield conn.cursor()
    conn.close()


def test_issue_returns_six_digits_and_hashes(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    assert len(code) == 6 and code.isdigit()
    row = cur.execute('SELECT code_hash FROM auth_codes').fetchone()
    assert code not in row[0]                      # stored hashed, never plaintext
    assert row[0].startswith('pbkdf2:sha256')      # frozen-exe-safe method


def test_verify_ok_consumes(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'ok'
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'invalid'  # single use


def test_new_code_voids_old(cur):
    old = auth_codes.issue_code(cur, 1, 'password_reset')
    new = auth_codes.issue_code(cur, 1, 'password_reset')
    assert auth_codes.verify_code(cur, 1, 'password_reset', old) == 'invalid'
    assert auth_codes.verify_code(cur, 1, 'password_reset', new) == 'ok'


def test_purposes_isolated(cur):
    code = auth_codes.issue_code(cur, 1, 'email_verify')
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'invalid'


def test_expired(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    cur.execute("UPDATE auth_codes SET expires_at = '2000-01-01T00:00:00'")
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'expired'


def test_attempt_lockout(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    for _ in range(auth_codes.MAX_ATTEMPTS):
        assert auth_codes.verify_code(cur, 1, 'password_reset', '000000') in ('invalid', 'locked')
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'locked'


def test_recovery_roundtrip(cur):
    code = auth_codes.issue_recovery_code(cur)
    assert len(code) == 19 and code.count('-') == 3
    assert auth_codes.redeem_recovery_code(cur, code) is True
    assert auth_codes.redeem_recovery_code(cur, code) is False  # single use


def test_recovery_regenerate_voids_old(cur):
    old = auth_codes.issue_recovery_code(cur)
    auth_codes.issue_recovery_code(cur)
    assert auth_codes.redeem_recovery_code(cur, old) is False
