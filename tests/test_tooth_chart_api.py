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


def test_upsert_then_update_keeps_one_row(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    crown = _condition_id(client, 'Crown')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': crown})
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM patient_tooth_chart WHERE patient_id=? AND tooth_no=?', (pid, '16'))
    assert cur.fetchone()[0] == 1
    conn.close()
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['16']['condition_name'] == 'Crown'


def test_null_condition_clears_tooth(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    r = client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': None})
    assert r.status_code == 200
    assert '16' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='patient_tooth_chart'")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_delete_endpoint_clears_tooth(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '21', 'condition_id': decay})
    assert client.delete(f'/api/patients/{pid}/tooth-chart/21').status_code == 200
    assert '21' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']


def test_invalid_fdi_rejected_on_upsert(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    for bad in ['99', '51', '5a', '1']:
        r = client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': bad, 'condition_id': decay})
        assert r.status_code == 400, bad


def test_unknown_condition_rejected(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': 99999})
    assert r.status_code == 400
