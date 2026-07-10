"""Tooth-chart GET shape: marked teeth, legacy auto-adopt, computed badges."""

import sqlite3

import pytest

import dental_clinic


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
    with dental_clinic.app.test_client() as test_client:
        for cond in _STANDARD_CONDITIONS:
            test_client.post('/api/tooth-conditions', json=cond)
        yield test_client


def _patient(name='Chart', last='Badge', phone='0592'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _condition_id(client, name):
    return next(c['id'] for c in client.get('/api/tooth-conditions').get_json() if c['name'] == name)


def _followup(client, pid, tooth_no, price=0, payment=0, discount=0):
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/06/2026', 'treatment_procedure': 'Tx',
        'tooth_no': tooth_no, 'price': price, 'discount': discount, 'payment': payment,
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def test_empty_chart(client):
    pid = _patient()
    data = client.get(f'/api/patients/{pid}/tooth-chart').get_json()
    assert data['teeth'] == {}
    assert len(data['conditions']) >= 8


def test_marked_tooth_has_condition_and_color(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay, 'note': 'distal'})
    tooth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']
    assert tooth['source'] == 'chart'
    c = tooth['conditions'][0]
    assert c['condition_id'] == decay
    assert c['condition_name'] == 'Decay'
    assert c['color'].startswith('#')
    assert c['note'] == 'distal'


def test_unpaid_balance_badge_from_followups(client):
    pid = _patient()
    _followup(client, pid, '26', price=300, payment=100)
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['26']['source'] == 'legacy'
    assert teeth['26']['unpaid_balance'] == 200
    assert teeth['26']['has_plan'] is False


def test_has_plan_badge(client):
    pid = _patient()
    client.post('/api/treatment-plans', json={'patient_id': pid, 'plan_name': 'P', 'teeth': ['36']})
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['36']['has_plan'] is True


def test_legacy_junk_tooth_ignored(client):
    pid = _patient()
    _followup(client, pid, 'upper left', price=100)
    _followup(client, pid, '51', price=100)
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert 'upper left' not in teeth
    assert '51' not in teeth


def test_explicit_mark_overrides_legacy_source(client):
    pid = _patient()
    _followup(client, pid, '16', price=100)
    filled = _condition_id(client, 'Filled')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': filled})
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['16']['source'] == 'chart'
    assert teeth['16']['conditions'][0]['condition_name'] == 'Filled'


def test_chart_scoped_to_patient(client):
    a, b = _patient(phone='0001'), _patient(phone='0002')
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{a}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    assert client.get(f'/api/patients/{b}/tooth-chart').get_json()['teeth'] == {}


def test_unpaid_balance_excludes_deleted_followup(client):
    pid = _patient()
    _followup(client, pid, '26', price=300, payment=0)  # 300 owed
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    fid = rows[0]['id']
    client.delete(f'/api/patients/{pid}/followups/{fid}')  # remove it
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    # Tooth 26 should no longer carry a phantom balance (and may drop out entirely).
    assert teeth.get('26', {}).get('unpaid_balance', 0) == 0


def test_delete_invalid_fdi_rejected(client):
    pid = _patient()
    assert client.delete(f'/api/patients/{pid}/tooth-chart/junk').status_code == 400
