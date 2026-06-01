"""Editable tooth-condition catalog (mirrors the treatment_procedures catalog)."""

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


def test_core_eight_seeded(client):
    rows = client.get('/api/tooth-conditions').get_json()
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


def test_update_condition(client):
    rows = client.get('/api/tooth-conditions').get_json()
    decay_id = next(c['id'] for c in rows if c['name'] == 'Decay')
    r = client.put(f'/api/tooth-conditions/{decay_id}', json={
        'name': 'Decay', 'name_ar': 'نخر', 'color': '#b91c1c', 'sort_order': 1, 'active': 1,
    })
    assert r.status_code == 200
    rows = client.get('/api/tooth-conditions').get_json()
    decay = next(c for c in rows if c['id'] == decay_id)
    assert decay['name_ar'] == 'نخر'
    assert decay['color'] == '#b91c1c'


def test_soft_delete_condition(client):
    rows = client.get('/api/tooth-conditions').get_json()
    implant_id = next(c['id'] for c in rows if c['name'] == 'Implant')
    assert client.delete(f'/api/tooth-conditions/{implant_id}').status_code == 200
    active_names = {c['name'] for c in client.get('/api/tooth-conditions').get_json()}
    assert 'Implant' not in active_names
    all_rows = client.get('/api/tooth-conditions?all=1').get_json()
    implant = next(c for c in all_rows if c['id'] == implant_id)
    assert implant['active'] == 0
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='tooth_conditions' AND row_id=?", (implant_id,))
    assert cur.fetchone()[0] == 1
    conn.close()
