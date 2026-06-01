"""Per-patient tooth chart: upsert, clear, FDI validation, scoping."""

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


def _patient(name='Tooth', last='Chart', phone='0590'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _condition_id(client, name):
    rows = client.get('/api/tooth-conditions').get_json()
    return next(r['id'] for r in rows if r['name'] == name)


def test_chart_table_exists(client):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patient_tooth_chart'")
    assert cur.fetchone() is not None
    conn.close()


def test_is_valid_fdi():
    valid = ['11', '18', '21', '28', '31', '38', '41', '48', '34', '16']
    invalid = ['10', '19', '51', '85', '09', '99', '1', '111', '5a', 'ab', '', None, ' 16']
    for s in valid:
        assert dental_clinic._is_valid_fdi(s) is True, s
    for s in invalid:
        assert dental_clinic._is_valid_fdi(s) is False, s
