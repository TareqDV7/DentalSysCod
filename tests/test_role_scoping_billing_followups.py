"""Task 12: per-dentist scoping for billing + followups (same rule as
appointments — Task 11): dentist reads own + NULL rows; forged dentist_id on
create forced to self; mutating another dentist's (or NULL) row → 403; admin
unchanged. The patient-profile aggregate's billing/followups/appointments
sub-lists are scoped the same way.
"""
import dental_clinic
import permissions
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'role_scope_bf_test.db'
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


def _billing_row(pid, dentist_id):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO billing (patient_id, invoice_number, amount, subtotal, paid_amount, "
        "balance_due, payment_status, dentist_id) VALUES (?, ?, 100, 100, 0, 100, 'pending', ?)",
        (pid, f'INV-{dentist_id or 0}-{cur.lastrowid or 0}', dentist_id))
    bid = cur.lastrowid
    conn.commit()
    conn.close()
    return bid


def _followup_row(pid, dentist_id):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO patient_followups (patient_id, followup_date, treatment_procedure, "
        "price, payment, remaining_amount, dentist_id) VALUES (?, '2026-08-01', 'Filling', "
        "50, 0, 50, ?)", (pid, dentist_id))
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


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
    return {
        'pid': pid, 'a': a, 'b': b, 'admin': admin,
        'bill_a': _billing_row(pid, a), 'bill_b': _billing_row(pid, b),
        'bill_null': _billing_row(pid, None),
        'fu_a': _followup_row(pid, a), 'fu_b': _followup_row(pid, b),
        'fu_null': _followup_row(pid, None),
    }


# --- billing -----------------------------------------------------------------

def test_billing_list_scoped_for_dentist(client, world):
    _login(client, world['a'], 'drA')
    ids = {x['id'] for x in client.get('/api/billing').get_json()}
    assert ids == {world['bill_a'], world['bill_null']}


def test_billing_list_admin_sees_all(client, world):
    _login(client, world['admin'], 'boss')
    ids = {x['id'] for x in client.get('/api/billing').get_json()}
    assert ids == {world['bill_a'], world['bill_b'], world['bill_null']}


def test_billing_forged_dentist_id_lands_as_self(client, world):
    _login(client, world['a'], 'drA')
    r = client.post('/api/billing', json={'patient_id': world['pid'], 'subtotal': 10,
                                          'dentist_id': world['b']})
    assert r.status_code == 200, r.get_data(as_text=True)
    conn = dental_clinic.get_db_connection()
    row = conn.execute('SELECT dentist_id FROM billing ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    assert row[0] == world['a']


def test_billing_delete_cross_dentist_403(client, world):
    _login(client, world['a'], 'drA')
    assert client.delete(f"/api/billing/{world['bill_b']}").status_code == 403
    assert client.delete(f"/api/billing/{world['bill_null']}").status_code == 403
    assert client.delete(f"/api/billing/{world['bill_a']}").status_code == 200


def test_billing_delete_admin_any(client, world):
    _login(client, world['admin'], 'boss')
    assert client.delete(f"/api/billing/{world['bill_b']}").status_code == 200


# --- followups ---------------------------------------------------------------

def test_followups_list_scoped_for_dentist(client, world):
    _login(client, world['a'], 'drA')
    ids = {x['id'] for x in client.get(f"/api/patients/{world['pid']}/followups").get_json()}
    assert ids == {world['fu_a'], world['fu_null']}


def test_followups_list_admin_sees_all(client, world):
    _login(client, world['admin'], 'boss')
    ids = {x['id'] for x in client.get(f"/api/patients/{world['pid']}/followups").get_json()}
    assert ids == {world['fu_a'], world['fu_b'], world['fu_null']}


def test_followup_forged_dentist_id_lands_as_self(client, world):
    _login(client, world['a'], 'drA')
    r = client.post(f"/api/patients/{world['pid']}/followups",
                    json={'followup_date': '2026-08-05', 'treatment_procedure': 'Scaling',
                          'price': 30, 'dentist_id': world['b']})
    assert r.status_code == 200, r.get_data(as_text=True)
    conn = dental_clinic.get_db_connection()
    row = conn.execute('SELECT dentist_id FROM patient_followups ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    assert row[0] == world['a']


def test_followup_mutate_cross_dentist_403(client, world):
    _login(client, world['a'], 'drA')
    pid = world['pid']
    assert client.put(f"/api/patients/{pid}/followups/{world['fu_b']}",
                      json={'followup_date': '2026-08-06', 'treatment_procedure': 'X',
                            'price': 1}).status_code == 403
    assert client.delete(f"/api/patients/{pid}/followups/{world['fu_null']}").status_code == 403
    assert client.delete(f"/api/patients/{pid}/followups/{world['fu_a']}").status_code == 200


def test_followup_mutate_admin_any(client, world):
    _login(client, world['admin'], 'boss')
    pid = world['pid']
    assert client.delete(f"/api/patients/{pid}/followups/{world['fu_b']}").status_code == 200


# --- patient profile aggregate ----------------------------------------------

def test_patient_profile_lists_scoped_for_dentist(client, world):
    _login(client, world['a'], 'drA')
    prof = client.get(f"/api/patients/{world['pid']}/full-profile").get_json()
    bill_ids = {x['id'] for x in prof['billing']}
    fu_ids = {x['id'] for x in prof['followups']}
    assert bill_ids == {world['bill_a'], world['bill_null']}
    assert fu_ids == {world['fu_a'], world['fu_null']}


def test_patient_profile_admin_unscoped(client, world):
    _login(client, world['admin'], 'boss')
    prof = client.get(f"/api/patients/{world['pid']}/full-profile").get_json()
    assert {x['id'] for x in prof['billing']} == {world['bill_a'], world['bill_b'], world['bill_null']}
