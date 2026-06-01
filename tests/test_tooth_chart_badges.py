"""Tooth-chart GET shape: marked teeth, legacy auto-adopt, computed badges."""

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


def _patient(name='Chart', last='Badge', phone='0592'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
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
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['16']['condition_id'] == decay
    assert teeth['16']['condition_name'] == 'Decay'
    assert teeth['16']['color'].startswith('#')
    assert teeth['16']['note'] == 'distal'
    assert teeth['16']['source'] == 'chart'


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
    assert teeth['16']['condition_name'] == 'Filled'


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
