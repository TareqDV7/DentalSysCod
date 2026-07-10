"""get_db_connection() must open the database through SQLCipher with the
DPAPI-protected key, so the resulting .db file cannot be read by vanilla
sqlite3.

The fixture deliberately does NOT call dental_clinic.init_database(): as of
this task, init_database() still opens the database with a raw
sqlite3.connect(DB_NAME) internally (that's converted in a later task, not
this one), so relying on it here would produce an unencrypted file and give
a false sense of coverage. Instead the fixture builds the minimal schema
directly through get_db_connection() itself, which is exactly the code path
under test.
"""
import sqlite3

import pytest

import dental_clinic

_APP_SETTINGS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''


@pytest.fixture()
def encrypted_db(tmp_path, monkeypatch):
    test_db = tmp_path / 'enc_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    conn = dental_clinic.get_db_connection()
    conn.execute(_APP_SETTINGS_SCHEMA)
    conn.commit()
    conn.close()
    return test_db


def test_database_file_is_not_readable_by_vanilla_sqlite3(encrypted_db):
    # app_settings exists (the fixture created it), so a vanilla sqlite3
    # connection failing here means the *file itself* isn't parseable as
    # SQLite — i.e. it's actually encrypted — not merely that the table is
    # missing.
    with pytest.raises(sqlite3.DatabaseError):
        conn = sqlite3.connect(str(encrypted_db))
        conn.execute('SELECT * FROM app_settings').fetchall()


def test_get_db_connection_can_read_and_write(encrypted_db):
    conn = dental_clinic.get_db_connection()
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('t', 'v')")
    conn.commit()
    row = conn.execute("SELECT value FROM app_settings WHERE key = 't'").fetchone()
    conn.close()
    assert row[0] == 'v'
