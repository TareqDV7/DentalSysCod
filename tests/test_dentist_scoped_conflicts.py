"""Dentist-scoped overlap check for POST /api/appointments.

Two DIFFERENT named dentists may be booked in the same slot (they're
different people, not double-booking each other). An unassigned booking
(dentist_id NULL) is clinic-wide risk and conflicts against everything,
including other unassigned bookings, per
docs/superpowers/specs/2026-07-12-per-dentist-scheduling-design.md
Decision 3.
"""
import dental_clinic
import permissions
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'dentist_scoped_conflicts_test.db'
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


def _dentist(username):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 1)',
        (username, 'x', username),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _book(client, pid, dentist_id=None, when='2026-09-01T10:00', duration=30):
    body = {'patient_id': pid, 'appointment_date': when, 'duration': duration}
    if dentist_id is not None:
        body['dentist_id'] = dentist_id
    return client.post('/api/appointments', json=body)


def test_same_dentist_overlap_still_blocked(client):
    dr = _dentist('dr_a')
    first = _book(client, _patient('One'), dentist_id=dr, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=dr, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_different_dentists_overlap_allowed(client):
    dr_a = _dentist('dr_a')
    dr_b = _dentist('dr_b')
    first = _book(client, _patient('One'), dentist_id=dr_a, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=dr_b, when='2026-09-01T10:15')
    assert second.status_code == 200, second.get_json()


def test_unassigned_new_conflicts_with_assigned_existing(client):
    dr_a = _dentist('dr_a')
    first = _book(client, _patient('One'), dentist_id=dr_a, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=None, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_assigned_new_conflicts_with_unassigned_existing(client):
    first = _book(client, _patient('One'), dentist_id=None, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    dr_a = _dentist('dr_a')
    second = _book(client, _patient('Two'), dentist_id=dr_a, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_both_unassigned_overlap_blocked(client):
    first = _book(client, _patient('One'), dentist_id=None, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=None, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_different_dentists_non_overlapping_times_never_conflict(client):
    dr_a = _dentist('dr_a')
    dr_b = _dentist('dr_b')
    first = _book(client, _patient('One'), dentist_id=dr_a, when='2026-09-01T10:00', duration=30)
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=dr_b, when='2026-09-01T11:00', duration=30)
    assert second.status_code == 200, second.get_json()
