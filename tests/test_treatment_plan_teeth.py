"""Multi-tooth treatment plans via the treatment_plan_teeth link table."""

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


def _patient(name='Plan', last='Teeth', phone='0591'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_plan_teeth_table_exists(client):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='treatment_plan_teeth'")
    assert cur.fetchone() is not None
    conn.close()


def _create_plan(client, pid, teeth, name='Upper crowns'):
    r = client.post('/api/treatment-plans', json={
        'patient_id': pid, 'plan_name': name, 'teeth': teeth,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()['id']


def _plan(client, plan_id):
    plans = client.get('/api/treatment-plans').get_json()
    return next(p for p in plans if p['id'] == plan_id)


def test_create_plan_with_teeth(client):
    pid = _patient()
    plan_id = _create_plan(client, pid, ['16', '26', '36'])
    plan = _plan(client, plan_id)
    assert sorted(plan['teeth']) == ['16', '26', '36']
    assert plan['patient_name'] == 'Plan Teeth'


def test_invalid_tooth_skipped_on_create(client):
    pid = _patient()
    plan_id = _create_plan(client, pid, ['16', '99', 'junk', '36'])
    plan = _plan(client, plan_id)
    assert sorted(plan['teeth']) == ['16', '36']


def test_update_plan_teeth_diffs(client):
    pid = _patient()
    plan_id = _create_plan(client, pid, ['16', '26'])
    r = client.put(f'/api/treatment-plans/{plan_id}', json={
        'plan_name': 'Upper crowns', 'teeth': ['26', '46'],
    })
    assert r.status_code == 200
    assert sorted(_plan(client, plan_id)['teeth']) == ['26', '46']
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='treatment_plan_teeth'")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_delete_plan_cascades_teeth(client):
    pid = _patient()
    plan_id = _create_plan(client, pid, ['16', '26', '36'])
    assert client.delete(f'/api/treatment-plans/{plan_id}').status_code == 200
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM treatment_plan_teeth WHERE plan_id = ?', (plan_id,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='treatment_plan_teeth'")
    assert cur.fetchone()[0] == 3
    conn.close()


def test_put_without_teeth_key_leaves_links_untouched(client):
    pid = _patient()
    plan_id = _create_plan(client, pid, ['16', '26'])
    # A PUT that doesn't mention teeth (e.g. a status-only edit) must not clear links.
    r = client.put(f'/api/treatment-plans/{plan_id}', json={
        'plan_name': 'Upper crowns', 'status': 'active',
    })
    assert r.status_code == 200
    assert sorted(_plan(client, plan_id)['teeth']) == ['16', '26']
