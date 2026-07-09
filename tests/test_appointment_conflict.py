"""Double-booking guard for POST /api/appointments.

The conflict check must treat BOTH active states — `scheduled` and `confirmed`
— as occupying the slot. `cancelled`/`completed` free it.
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


def _patient(name='A'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, 'B', '0500'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _book(client, pid, when='2026-06-01T10:00', duration=30, status=None):
    body = {'patient_id': pid, 'appointment_date': when, 'duration': duration}
    if status:
        body['status'] = status
    return client.post('/api/appointments', json=body)


@pytest.mark.parametrize('blocking_status', ['scheduled', 'confirmed'])
def test_overlap_blocked_for_active_statuses(client, blocking_status):
    first = _book(client, _patient('One'), when='2026-06-01T10:00', duration=30,
                  status=blocking_status)
    assert first.status_code == 200, first.get_json()
    # Overlapping slot for a different patient must be rejected.
    second = _book(client, _patient('Two'), when='2026-06-01T10:15', duration=30)
    assert second.status_code == 409, second.get_json()


@pytest.mark.parametrize('freed_status', ['cancelled', 'completed'])
def test_overlap_allowed_when_slot_freed(client, freed_status):
    first = _book(client, _patient('One'), when='2026-06-01T10:00', duration=30,
                  status=freed_status)
    assert first.status_code == 200, first.get_json()
    # The slot is free again — overlapping booking is allowed.
    second = _book(client, _patient('Two'), when='2026-06-01T10:15', duration=30)
    assert second.status_code == 200, second.get_json()
