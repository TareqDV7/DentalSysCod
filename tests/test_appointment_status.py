"""Regression cover for /api/appointments/<id>/status.

The PUT used to reject ``confirmed`` (it only accepted ``no_show`` which the UI
never sends) and silently 400 for any UI dropdown change to *Confirmed*.
"""

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


def _make_appointment(client):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                ('A', 'B', '0500'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-06-01T10:00', 'duration': 30,
    })
    assert r.status_code == 200
    return r.get_json()['id']


@pytest.mark.parametrize('status', ['scheduled', 'confirmed', 'completed', 'cancelled'])
def test_valid_statuses_accepted(client, status):
    aid = _make_appointment(client)
    r = client.put(f'/api/appointments/{aid}/status', json={'status': status})
    assert r.status_code == 200

    conn = dental_clinic.get_db_connection()
    row = conn.execute('SELECT status FROM appointments WHERE id = ?', (aid,)).fetchone()
    conn.close()
    assert row[0] == status


def test_bogus_status_rejected(client):
    aid = _make_appointment(client)
    r = client.put(f'/api/appointments/{aid}/status', json={'status': 'no_show'})
    assert r.status_code == 400

    r = client.put(f'/api/appointments/{aid}/status', json={'status': 'totally-made-up'})
    assert r.status_code == 400
