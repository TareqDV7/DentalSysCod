"""The three new odontogram tables sync like every other SYNC_TABLES entry."""

import sqlite3

import pytest

import dental_clinic


AUTH = {'X-Device-Token': 'test-token'}

_STANDARD_CONDITIONS = [
    {'name': 'Healthy',          'name_ar': 'سليم',       'color': '#22c55e', 'sort_order': 0},
    {'name': 'Decay',            'name_ar': 'تسوّس',      'color': '#ef4444', 'sort_order': 1},
    {'name': 'Filled',           'name_ar': 'حشوة',       'color': '#3b82f6', 'sort_order': 2},
    {'name': 'Crown',            'name_ar': 'تاج',        'color': '#a855f7', 'sort_order': 3},
    {'name': 'Root canal',       'name_ar': 'علاج عصب',   'color': '#f59e0b', 'sort_order': 4},
    {'name': 'Missing',          'name_ar': 'مفقود',      'color': '#6b7280', 'sort_order': 5},
    {'name': 'Implant',          'name_ar': 'زرعة',       'color': '#06b6d4', 'sort_order': 6},
    {'name': 'Needs extraction', 'name_ar': 'يحتاج خلع',  'color': '#dc2626', 'sort_order': 7},
]


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
        for cond in _STANDARD_CONDITIONS:
            test_client.post('/api/tooth-conditions', json=cond)
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


def test_multi_condition_rows_export_and_tombstone(client):
    pid = _patient()
    conds = client.get('/api/tooth-conditions').get_json()
    decay = next(c['id'] for c in conds if c['name'] == 'Decay')
    crown = next(c['id'] for c in conds if c['name'] == 'Crown')
    client.post(f'/api/patients/{pid}/tooth-chart',
                json={'tooth_no': '16', 'conditions': [{'condition_id': decay}, {'condition_id': crown}]})
    rows = client.get('/api/sync/export', headers=AUTH).get_json()['tables']['patient_tooth_chart']
    assert sum(1 for r in rows if r['tooth_no'] == '16') == 2
    # drop one → tombstone propagates
    client.post(f'/api/patients/{pid}/tooth-chart',
                json={'tooth_no': '16', 'conditions': [{'condition_id': crown}]})
    exported = client.get('/api/sync/export', headers=AUTH).get_json()
    assert any(t['table_name'] == 'patient_tooth_chart' for t in exported['tombstones'])
