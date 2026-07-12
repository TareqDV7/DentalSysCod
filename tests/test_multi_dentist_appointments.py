"""dentist_id on appointments: auto-fills from the session user when they're
a dentist, leaves it unset otherwise, is overridable, and round-trips through
both GET code paths (get_db_connection() with and without with_row_factory)."""
import dental_clinic
import permissions
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_appt_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(client=None):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _dentist(username='dr1', display_name='Dr. One'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 1)',
        (username, 'x', display_name),
    )
    uid = cur.lastrowid
    # RBAC gates POST /api/appointments behind appointments.edit -- a
    # raw-inserted user (bypassing the /api/staff creation flow) starts with
    # zero granted permissions, so any session-authenticated POST in these
    # tests would 403 before the dentist_id logic ever runs.
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _front_desk(username='fd1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 0)',
        (username, 'x', 'Front Desk'),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def test_post_auto_fills_dentist_id_from_dentist_session(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-01 10:00:00',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == dentist_id


def test_post_leaves_dentist_id_unset_for_non_dentist_session(client):
    pid = _patient()
    fd_id = _front_desk()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-02 10:00:00',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] is None


def test_post_accepts_explicit_dentist_id_override(client):
    pid = _patient()
    fd_id = _front_desk()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-03 10:00:00', 'dentist_id': dentist_id,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == dentist_id


def test_post_rejects_explicit_non_dentist_id(client):
    pid = _patient()
    fd_id = _front_desk()
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-04 10:00:00', 'dentist_id': fd_id,
    })
    assert r.status_code == 400


def test_get_appointments_includes_dentist_id(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-05 10:00:00',
    })
    rows = client.get('/api/appointments').get_json()
    assert rows[0]['dentist_id'] == dentist_id


def test_post_empty_string_dentist_id_treated_as_unset(client):
    # The desktop form always submits dentist_id (via FormData), so an
    # "Unassigned" selection arrives as '' not a missing key -- this must
    # fall through to the same auto-fill path as omitting the field
    # entirely, not be treated as an invalid explicit value.
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-06 10:00:00', 'dentist_id': '',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == dentist_id
