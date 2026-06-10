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
    conn = sqlite3.connect(fresh_db)
    # id=0 is the reserved system procedure ('مراجعة') — not a doctor-managed catalog row.
    n = conn.execute('SELECT COUNT(*) FROM treatment_procedures WHERE id > 0').fetchone()[0]
    conn.close()
    assert n == 0


def test_no_seeded_tooth_conditions(fresh_db):
    conn = sqlite3.connect(fresh_db)
    n = conn.execute('SELECT COUNT(*) FROM tooth_conditions').fetchone()[0]
    conn.close()
    assert n == 0
