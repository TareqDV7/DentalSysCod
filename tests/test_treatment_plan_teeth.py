"""Multi-tooth treatment plans via the treatment_plan_teeth link table."""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(name='Plan', last='Teeth', phone='0591'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_plan_teeth_table_exists(client):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='treatment_plan_teeth'")
    assert cur.fetchone() is not None
    conn.close()
