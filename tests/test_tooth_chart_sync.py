"""The three new odontogram tables sync like every other SYNC_TABLES entry."""

import sqlite3

import pytest

import dental_clinic


AUTH = {'X-Device-Token': 'test-token'}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO paired_devices (device_id, device_name, device_token) VALUES (?,?,?)',
                ('dev-test', 'Test Device', 'test-token'))
    conn.commit()
    conn.close()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def test_new_tables_in_sync_export(client):
    data = client.get('/api/sync/export', headers=AUTH).get_json()
    assert 'tooth_conditions' in data['tables']
    assert 'patient_tooth_chart' in data['tables']
    assert 'treatment_plan_teeth' in data['tables']
    assert len(data['tables']['tooth_conditions']) >= 8


def _patient():
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                ('Sync', 'Tooth', '0593'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_chart_row_exports_and_imports(client):
    pid = _patient()
    decay = next(c['id'] for c in client.get('/api/tooth-conditions').get_json() if c['name'] == 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})

    exported = client.get('/api/sync/export', headers=AUTH).get_json()
    chart_rows = exported['tables']['patient_tooth_chart']
    assert any(r['tooth_no'] == '16' for r in chart_rows)

    resp = client.post('/api/sync/import', headers=AUTH, json={'tables': {'patient_tooth_chart': chart_rows}})
    assert resp.status_code == 200


def test_chart_delete_tombstone_propagates(client):
    pid = _patient()
    decay = next(c['id'] for c in client.get('/api/tooth-conditions').get_json() if c['name'] == 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    client.delete(f'/api/patients/{pid}/tooth-chart/16')

    exported = client.get('/api/sync/export', headers=AUTH).get_json()
    assert any(t['table_name'] == 'patient_tooth_chart' for t in exported['tombstones'])
