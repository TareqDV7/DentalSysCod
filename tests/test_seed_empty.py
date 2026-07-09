"""A fresh database ships with empty catalogs (no demo seed)."""
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    return str(db)


def test_no_seeded_procedures(fresh_db):
    conn = dental_clinic.get_db_connection()
    # Fresh installs show an empty picker (the reserved id=0 sentinel ships inactive).
    n = conn.execute('SELECT COUNT(*) FROM treatment_procedures WHERE active = 1').fetchone()[0]
    conn.close()
    assert n == 0


def test_no_seeded_tooth_conditions(fresh_db):
    conn = dental_clinic.get_db_connection()
    n = conn.execute('SELECT COUNT(*) FROM tooth_conditions').fetchone()[0]
    conn.close()
    assert n == 0
