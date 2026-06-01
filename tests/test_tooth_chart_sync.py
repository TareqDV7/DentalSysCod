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
