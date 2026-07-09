"""Automatic one-time migration of an existing plaintext clinic database to
SQLCipher encryption. Must never leave the clinic without a working,
openable database — every failure path restores the pre-migration backup."""
import sqlite3

import pytest

import dental_clinic


def _make_plaintext_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute('CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name TEXT)')
    conn.execute("INSERT INTO patients (first_name) VALUES ('Alice')")
    conn.execute("INSERT INTO patients (first_name) VALUES ('Bob')")
    conn.commit()
    conn.close()


def test_migrates_plaintext_db_and_preserves_all_rows(tmp_path, monkeypatch):
    db_path = tmp_path / 'clinic.db'
    _make_plaintext_db(db_path)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is True

    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(str(db_path)).execute('SELECT * FROM patients').fetchall()

    conn = dental_clinic.get_db_connection()
    rows = conn.execute('SELECT first_name FROM patients ORDER BY id').fetchall()
    conn.close()
    assert [r[0] for r in rows] == ['Alice', 'Bob']


def test_already_encrypted_db_is_a_no_op(tmp_path, monkeypatch):
    db_path = tmp_path / 'clinic.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')
    conn = dental_clinic.get_db_connection()  # creates it encrypted directly (init_database() isn't converted until Task 5)
    conn.execute('CREATE TABLE t (id INTEGER)')
    conn.commit()
    conn.close()

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False


def test_secret_key_bootstrap_artifact_is_not_treated_as_a_pre_existing_db(tmp_path, monkeypatch):
    """_load_or_create_secret_key() runs at module *import* time (well before
    __main__ / migrate_db_to_encrypted() is even reached) and always leaves a
    DB_NAME file behind holding just the Flask secret-key row — even on a
    brand-new install that has never run init_database(). This must NOT be
    mistaken for a genuine pre-existing clinic database that needs migrating.

    Since Task 5, both _load_or_create_secret_key() and init_database() open
    DB_NAME via get_db_connection(), so this bootstrap artifact is encrypted
    from the moment it's created — _is_plaintext_sqlite() already excludes it
    from migration for that reason. _has_clinic_schema()'s bootstrap check
    (guarding the case where the file *is* plaintext, e.g. pre-migration on an
    existing install) is exercised by test_nonexistent_db_is_a_no_op and the
    already-encrypted case below."""
    db_path = tmp_path / 'clinic.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')
    dental_clinic._load_or_create_secret_key()  # simulates the import-time bootstrap write

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False

    # init_database() must still be able to build the real schema on top of
    # the untouched bootstrap file — this is what would crash if the bootstrap
    # artifact got wrongly treated as a stale/corrupt file.
    dental_clinic.init_database()
    conn = dental_clinic.get_db_connection()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert 'patients' in tables


def test_nonexistent_db_is_a_no_op(tmp_path, monkeypatch):
    db_path = tmp_path / 'does_not_exist.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False


def test_failure_mid_migration_restores_pre_migration_backup(tmp_path, monkeypatch):
    db_path = tmp_path / 'clinic.db'
    _make_plaintext_db(db_path)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')

    def _boom(*a, **kw):
        raise RuntimeError('simulated failure mid-export')

    monkeypatch.setattr(dental_clinic, '_sqlcipher_export', _boom)

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False  # migration did not silently "succeed"

    # The original plaintext DB must still be intact and readable — the
    # clinic is never left without a working database.
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute('SELECT first_name FROM patients ORDER BY id').fetchall()
    conn.close()
    assert [r[0] for r in rows] == ['Alice', 'Bob']
