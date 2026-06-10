"""Editable tooth-condition catalog (mirrors the treatment_procedures catalog)."""

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
        yield test_client


@pytest.fixture()
def seeded_client(client):
    """Client with the standard 8 tooth conditions pre-inserted via the API."""
    for cond in _STANDARD_CONDITIONS:
        client.post('/api/tooth-conditions', json=cond)
    return client


def test_core_eight_seeded(seeded_client):
    """The API can store and retrieve conditions with full display metadata."""
    rows = seeded_client.get('/api/tooth-conditions').get_json()
    names = {r['name'] for r in rows}
    assert {'Healthy', 'Decay', 'Filled', 'Crown', 'Root canal',
            'Missing', 'Implant', 'Needs extraction'} <= names
    # Catalog carries display metadata.
    decay = next(r for r in rows if r['name'] == 'Decay')
    assert decay['color'].startswith('#')
    assert decay['name_ar']
    assert 'sort_order' in decay


def test_create_condition(client):
    r = client.post('/api/tooth-conditions', json={
        'name': 'Veneer', 'name_ar': 'فينير', 'color': '#10b981', 'sort_order': 9,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    names = {c['name'] for c in client.get('/api/tooth-conditions').get_json()}
    assert 'Veneer' in names


def test_duplicate_condition_rejected(client):
    client.post('/api/tooth-conditions', json={'name': 'Sealant'})
    r = client.post('/api/tooth-conditions', json={'name': 'Sealant'})
    assert r.status_code == 409


def test_blank_name_rejected(client):
    r = client.post('/api/tooth-conditions', json={'name': '   '})
    assert r.status_code == 400


def test_update_condition(seeded_client):
    rows = seeded_client.get('/api/tooth-conditions').get_json()
    decay_id = next(c['id'] for c in rows if c['name'] == 'Decay')
    r = seeded_client.put(f'/api/tooth-conditions/{decay_id}', json={
        'name': 'Decay', 'name_ar': 'نخر', 'color': '#b91c1c', 'sort_order': 1, 'active': 1,
    })
    assert r.status_code == 200
    rows = seeded_client.get('/api/tooth-conditions').get_json()
    decay = next(c for c in rows if c['id'] == decay_id)
    assert decay['name_ar'] == 'نخر'
    assert decay['color'] == '#b91c1c'


def test_soft_delete_condition(seeded_client):
    rows = seeded_client.get('/api/tooth-conditions').get_json()
    implant_id = next(c['id'] for c in rows if c['name'] == 'Implant')
    assert seeded_client.delete(f'/api/tooth-conditions/{implant_id}').status_code == 200
    active_names = {c['name'] for c in seeded_client.get('/api/tooth-conditions').get_json()}
    assert 'Implant' not in active_names
    all_rows = seeded_client.get('/api/tooth-conditions?all=1').get_json()
    implant = next(c for c in all_rows if c['id'] == implant_id)
    assert implant['active'] == 0
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='tooth_conditions' AND row_id=?", (implant_id,))
    assert cur.fetchone()[0] == 1
    conn.close()
