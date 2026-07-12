"""dentist_id on patient_followups -- same auto-fill/override/reject rules as
appointments (Task 2). GET needs no code change: patient_followups() already
returns `dict(row)` from a with_row_factory=True cursor, so a new column
appears automatically -- this file just proves that."""
import dental_clinic
import permissions
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_followup_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient():
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _dentist(username='dr1'):
    # Raw INSERT bypasses the /api/staff creation flow, which is what
    # normally grants permissions -- without this, RBAC's appointments.edit/
    # followups.edit/billing.edit gate 403s every session-authenticated POST
    # in these tests before the dentist_id logic ever runs (found the hard
    # way in Task 2's execution).
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, 'x', 'Dr. One', 1)",
        (username,),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _front_desk(username='fd1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, 'x', 'Front Desk', 0)",
        (username,),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _followup(client, pid, **overrides):
    payload = {'followup_date': '15/06/2026', 'treatment_procedure': 'Filling', 'price': 100}
    payload.update(overrides)
    return client.post(f'/api/patients/{pid}/followups', json=payload)


def test_post_auto_fills_from_dentist_session(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = _followup(client, pid)
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['dentist_id'] == dentist_id


def test_post_leaves_unset_for_non_dentist_session(client):
    pid = _patient()
    fd_id = _front_desk()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    _followup(client, pid)
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['dentist_id'] is None


def test_post_rejects_explicit_non_dentist_id(client):
    pid = _patient()
    fd_id = _front_desk()
    r = _followup(client, pid, dentist_id=fd_id)
    assert r.status_code == 400
