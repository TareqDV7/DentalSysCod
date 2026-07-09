"""Per-patient tooth chart: upsert, clear, FDI validation, scoping."""

import sqlite3

import pytest

import dental_clinic


_STANDARD_CONDITIONS = [
    {'name': 'Decay',     'name_ar': 'تسوّس',   'color': '#ef4444', 'sort_order': 1},
    {'name': 'Crown',     'name_ar': 'تاج',     'color': '#a855f7', 'sort_order': 3},
    {'name': 'Filled',    'name_ar': 'حشوة',    'color': '#3b82f6', 'sort_order': 2},
    {'name': 'Root canal','name_ar': 'علاج عصب','color': '#f59e0b', 'sort_order': 4},
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


def _patient(name='Tooth', last='Chart', phone='0590'):
    conn = dental_clinic.get_db_connection()
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


def _post_conditions(client, pid, tooth, items):
    return client.post(f'/api/patients/{pid}/tooth-chart',
                       json={'tooth_no': tooth, 'conditions': items})


def test_chart_table_exists(client):
    conn = dental_clinic.get_db_connection()
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


def test_get_returns_conditions_list(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    crown = _condition_id(client, 'Crown')
    _post_conditions(client, pid, '16', [
        {'condition_id': decay, 'note': 'distal'},
        {'condition_id': crown, 'note': 'PFM'},
    ])
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert {c['condition_name'] for c in conds} == {'Decay', 'Crown'}
    notes = {c['condition_name']: c['note'] for c in conds}
    assert notes['Decay'] == 'distal' and notes['Crown'] == 'PFM'
    assert all('color' in c and 'condition_id' in c for c in conds)


def test_post_conditions_replaces_set(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    crown = _condition_id(client, 'Crown')
    rc = _condition_id(client, 'Root canal')
    _post_conditions(client, pid, '16', [{'condition_id': decay}, {'condition_id': crown}])
    _post_conditions(client, pid, '16', [{'condition_id': crown}, {'condition_id': rc}])
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert {c['condition_name'] for c in conds} == {'Crown', 'Root canal'}
    conn = dental_clinic.get_db_connection()
    n = conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='patient_tooth_chart'").fetchone()[0]
    conn.close()
    assert n >= 1


def test_post_empty_conditions_clears_tooth(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    _post_conditions(client, pid, '16', [{'condition_id': decay}])
    assert _post_conditions(client, pid, '16', []).status_code == 200
    assert '16' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']


def test_legacy_single_condition_still_works(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert [c['condition_name'] for c in conds] == ['Decay']


def test_legacy_null_condition_clears_tooth(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    assert client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': None}).status_code == 200
    assert '16' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']


def test_post_dedupes_repeated_condition(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    _post_conditions(client, pid, '16', [{'condition_id': decay}, {'condition_id': decay, 'note': 'x'}])
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert len(conds) == 1


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
