"""The legacy ``treatment_catalog`` table is merged into ``treatment_procedures``.

A fresh database should just set the migration flag (no work to do).
A database with the old table should have its rows copied (matched by name —
duplicates ignored), then the table dropped. A second ``init_database()`` call
must be a no-op (idempotent).
"""

import os
import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'fresh.db')
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db_path)
    return db_path


@pytest.fixture()
def legacy_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'legacy.db')
    # Pre-create a treatment_catalog table with some rows (the old schema).
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE treatment_catalog (
            id INTEGER PRIMARY KEY,
            name_ar TEXT,
            name_en TEXT,
            default_price REAL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT, updated_at TEXT
        )
    ''')
    conn.execute(
        'INSERT INTO treatment_catalog (name_ar, name_en, default_price, is_active) '
        'VALUES (?, ?, ?, 1)', ('placeholder', 'Special Filling', 199)
    )
    conn.execute(
        'INSERT INTO treatment_catalog (name_ar, name_en, default_price, is_active) '
        'VALUES (?, ?, ?, 1)', ('OnlyArabic', '', 50)
    )
    # A name that clashes with a default procedure — must be ignored, not duplicated.
    conn.execute(
        'INSERT INTO treatment_catalog (name_ar, name_en, default_price, is_active) '
        'VALUES (?, ?, ?, 1)', ('clean', 'Cleaning', 12345)
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db_path)
    return db_path


def _proc_names(db_path):
    conn = sqlite3.connect(db_path)
    rows = [r[0] for r in conn.execute(
        'SELECT name FROM treatment_procedures ORDER BY name COLLATE NOCASE')]
    conn.close()
    return rows


def _table_exists(db_path, table):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    conn.close()
    return row is not None


def _flag(db_path):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key='treatment_catalog_migrated'"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def test_fresh_db_marks_flag_and_has_no_catalog_table(fresh_db):
    dental_clinic.init_database()
    assert not _table_exists(fresh_db, 'treatment_catalog')
    assert _flag(fresh_db) == '1'


def test_legacy_rows_migrate_into_procedures(legacy_db):
    dental_clinic.init_database()
    names = _proc_names(legacy_db)
    # New names from the catalog ended up in procedures.
    assert 'Special Filling' in names
    assert 'OnlyArabic' in names
    # Clashing name ('Cleaning') stayed as the seeded default — no duplicates.
    assert names.count('Cleaning') == 1
    # And the legacy table was dropped + the flag set.
    assert not _table_exists(legacy_db, 'treatment_catalog')
    assert _flag(legacy_db) == '1'


def test_second_init_is_a_noop(legacy_db):
    dental_clinic.init_database()
    before = _proc_names(legacy_db)
    dental_clinic.init_database()
    after = _proc_names(legacy_db)
    assert before == after
    assert not _table_exists(legacy_db, 'treatment_catalog')
