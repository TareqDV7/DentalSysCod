"""Task 11: server-enforced per-dentist scoping on appointments.

role='dentist' sessions: reads limited to own rows + NULL-dentist rows
(legacy/front-desk bookings stay visible, read-only); forged dentist_id on
create is overridden with the session user; mutating another dentist's row
(or a NULL row) → 403. Admin sessions see and mutate everything, unchanged.
"""
import dental_clinic
import permissions
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'role_scope_appt_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _patient():
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _user(username, role):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist, role) '
        'VALUES (?, ?, ?, ?, ?)',
        (username, 'x', username, 1 if role == 'dentist' else 0, role))
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _appt(patient_id, dentist_id, when):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, duration, status, dentist_id) "
        "VALUES (?, ?, 30, 'scheduled', ?)", (patient_id, when, dentist_id))
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def _login(client, uid, username):
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = username


@pytest.fixture()
def world(client):
    pid = _patient()
    a = _user('drA', 'dentist')
    b = _user('drB', 'dentist')
    admin = _user('boss', 'admin')
    appt_a = _appt(pid, a, '2026-08-03 10:00')
    appt_b = _appt(pid, b, '2026-08-03 11:00')
    appt_null = _appt(pid, None, '2026-08-03 12:00')
    return {'pid': pid, 'a': a, 'b': b, 'admin': admin,
            'appt_a': appt_a, 'appt_b': appt_b, 'appt_null': appt_null}


def test_dentist_list_shows_own_and_null_only(client, world):
    _login(client, world['a'], 'drA')
    ids = {x['id'] for x in client.get('/api/appointments').get_json()}
    assert ids == {world['appt_a'], world['appt_null']}
    recent = {x['id'] for x in client.get('/api/appointments/recent').get_json()}
    assert recent == {world['appt_a'], world['appt_null']}


def test_admin_sees_all(client, world):
    _login(client, world['admin'], 'boss')
    ids = {x['id'] for x in client.get('/api/appointments').get_json()}
    assert ids == {world['appt_a'], world['appt_b'], world['appt_null']}


def test_forged_dentist_id_on_create_lands_as_self(client, world):
    _login(client, world['a'], 'drA')
    r = client.post('/api/appointments',
                    json={'patient_id': world['pid'],
                          'appointment_date': '2026-08-04 10:00',
                          'dentist_id': world['b']})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == world['a']


def test_dentist_cannot_mutate_other_dentists_row(client, world):
    _login(client, world['a'], 'drA')
    r = client.put(f"/api/appointments/{world['appt_b']}/status",
                   json={'status': 'cancelled'})
    assert r.status_code == 403
    assert r.get_json()['error'] == 'Not your record'
    r2 = client.delete(f"/api/appointments/{world['appt_b']}")
    assert r2.status_code == 403


def test_dentist_cannot_mutate_null_row(client, world):
    _login(client, world['a'], 'drA')
    r = client.put(f"/api/appointments/{world['appt_null']}/status",
                   json={'status': 'confirmed'})
    assert r.status_code == 403
    r2 = client.delete(f"/api/appointments/{world['appt_null']}")
    assert r2.status_code == 403


def test_dentist_can_mutate_own_row(client, world):
    _login(client, world['a'], 'drA')
    r = client.put(f"/api/appointments/{world['appt_a']}/status",
                   json={'status': 'completed'})
    assert r.status_code == 200
    r2 = client.delete(f"/api/appointments/{world['appt_a']}")
    assert r2.status_code == 200


def test_admin_can_mutate_any_row(client, world):
    _login(client, world['admin'], 'boss')
    for aid in (world['appt_a'], world['appt_b'], world['appt_null']):
        r = client.put(f'/api/appointments/{aid}/status', json={'status': 'confirmed'})
        assert r.status_code == 200
    r2 = client.delete(f"/api/appointments/{world['appt_b']}")
    assert r2.status_code == 200


def test_anonymous_scope_helper_is_empty(client, world):
    # dentist_scope outside any session must be a no-op filter
    with dental_clinic.app.test_request_context('/'):
        conn = dental_clinic.get_db_connection()
        frag, params = dental_clinic.dentist_scope(conn.cursor(), 'a')
        conn.close()
    assert frag == '' and params == []
