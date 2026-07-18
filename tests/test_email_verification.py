"""Task 8: profile email set + OTP verification; /api/staff gains email/role
management; /api/auth/me exposes role/email/email_verified.

POST /api/profile/email (self-service, any logged-in user): stores a
lowercased email, resets email_verified=0, issues+sends an 'email_verify'
OTP. 400 on malformed or duplicate (case-insensitive) email.

POST /api/profile/email/verify: consumes the OTP, sets email_verified=1 on
'ok', 400 otherwise.

/api/staff PUT accepts 'email' (admin-set: resets email_verified=0, re-issues
+ sends a fresh code) and 'role' (admin|dentist|staff: syncs
is_dentist = 1 iff role == 'dentist'; refuses to demote the last active
admin). /api/staff POST also accepts 'role' at insert time (default 'staff'),
syncing is_dentist the same way.
"""
import pytest

import dental_clinic
import permissions


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'email_verification_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


@pytest.fixture()
def sent_emails(monkeypatch):
    """Capture (to, template, params, lang) tuples; default to a successful send."""
    calls = []

    def _fake(to, template, params, lang='en'):
        calls.append((to, template, params, lang))
        return True, ''

    monkeypatch.setattr(dental_clinic, 'send_system_email', _fake)
    return calls


def _login_as(client, username='admin'):
    conn = dental_clinic.get_db_connection()
    uid = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()[0]
    conn.close()
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = username
    return uid


def _create_staff(client, username, password='pw123456', **extra):
    payload = {'username': username, 'password': password}
    payload.update(extra)
    r = client.post('/api/staff', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()['id']


def _user_row(username):
    conn = dental_clinic.get_db_connection(with_row_factory=True)
    row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return row


# --- POST /api/profile/email ------------------------------------------------

def test_set_email_requires_login(client):
    r = client.post('/api/profile/email', json={'email': 'doc@x.com'})
    assert r.status_code == 401


def test_set_email_lowercases_row_and_sends_code(client, sent_emails):
    _login_as(client, 'admin')
    r = client.post('/api/profile/email', json={'email': 'Doc@Example.COM'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['success'] is True
    assert body['sent'] is True

    row = _user_row('admin')
    assert row['email'] == 'doc@example.com'
    assert row['email_verified'] == 0

    assert len(sent_emails) == 1
    to, template, params, lang = sent_emails[0]
    assert to == 'doc@example.com'
    assert template == 'email_verify'
    assert 'code' in params and len(params['code']) == 6
    assert lang == 'en'


def test_set_email_malformed_returns_400(client, sent_emails):
    _login_as(client, 'admin')
    r = client.post('/api/profile/email', json={'email': 'not-an-email'})
    assert r.status_code == 400
    assert sent_emails == []


def test_set_email_rejects_case_variant_duplicate(client, sent_emails):
    _create_staff(client, 'dr2')
    conn = dental_clinic.get_db_connection()
    conn.execute("UPDATE users SET email = 'shared@x.com' WHERE username = 'dr2'")
    conn.commit()
    conn.close()

    _login_as(client, 'admin')
    r = client.post('/api/profile/email', json={'email': 'Shared@X.com'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'That email is already in use'
    assert sent_emails == []


def test_set_email_send_failure_still_returns_200_and_stores_email(client, monkeypatch):
    monkeypatch.setattr(dental_clinic, 'send_system_email',
                        lambda to, template, params, lang='en': (False, 'unreachable'))
    _login_as(client, 'admin')
    r = client.post('/api/profile/email', json={'email': 'doc@x.com'})
    assert r.status_code == 200
    assert r.get_json()['sent'] is False
    row = _user_row('admin')
    assert row['email'] == 'doc@x.com'


# --- POST /api/profile/email/verify -----------------------------------------

def test_verify_requires_login(client):
    r = client.post('/api/profile/email/verify', json={'code': '000000'})
    assert r.status_code == 401


def test_verify_wrong_code_returns_400(client, sent_emails):
    _login_as(client, 'admin')
    client.post('/api/profile/email', json={'email': 'doc@x.com'})
    r = client.post('/api/profile/email/verify', json={'code': '000000'})
    assert r.status_code == 400
    row = _user_row('admin')
    assert row['email_verified'] == 0


def test_verify_right_code_sets_email_verified(client, sent_emails):
    _login_as(client, 'admin')
    client.post('/api/profile/email', json={'email': 'doc@x.com'})
    code = sent_emails[0][2]['code']
    r = client.post('/api/profile/email/verify', json={'code': code})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    row = _user_row('admin')
    assert row['email_verified'] == 1


# --- /api/staff GET/PUT email/role -------------------------------------------

def test_staff_get_includes_email_role_fields(client):
    _login_as(client, 'admin')
    rows = client.get('/api/staff').get_json()
    admin_row = next(u for u in rows if u['username'] == 'admin')
    assert 'email' in admin_row
    assert 'email_verified' in admin_row
    assert 'role' in admin_row
    assert admin_row['role'] == 'admin'


def test_admin_put_email_resets_verified_and_reissues_code(client, sent_emails):
    dr2_id = _create_staff(client, 'dr2')
    _login_as(client, 'admin')
    # Verify an initial email first, then have admin overwrite it via PUT.
    conn = dental_clinic.get_db_connection()
    conn.execute('UPDATE users SET email = ?, email_verified = 1 WHERE id = ?',
                 ('old@x.com', dr2_id))
    conn.commit()
    conn.close()

    r = client.put(f'/api/staff/{dr2_id}', json={'email': 'New@X.com'})
    assert r.status_code == 200, r.get_data(as_text=True)

    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        'SELECT email, email_verified FROM users WHERE id = ?', (dr2_id,)).fetchone()
    assert row['email'] == 'new@x.com'
    assert row['email_verified'] == 0

    assert len(sent_emails) == 1
    to, template, params, lang = sent_emails[0]
    assert to == 'new@x.com'
    assert template == 'email_verify'
    assert len(params['code']) == 6


def test_put_email_rejects_case_variant_duplicate(client, sent_emails):
    dr2_id = _create_staff(client, 'dr2')
    _create_staff(client, 'dr3')
    conn = dental_clinic.get_db_connection()
    conn.execute("UPDATE users SET email = 'taken@x.com' WHERE username = 'dr3'")
    conn.commit()
    conn.close()

    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{dr2_id}', json={'email': 'Taken@X.com'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'That email is already in use'


def test_put_role_change_to_dentist_syncs_is_dentist(client):
    staff_id = _create_staff(client, 'personA')
    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{staff_id}', json={'role': 'dentist'})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        'SELECT role, is_dentist FROM users WHERE id = ?', (staff_id,)).fetchone()
    assert row['role'] == 'dentist'
    assert row['is_dentist'] == 1


def test_put_role_change_back_to_staff_clears_is_dentist(client):
    staff_id = _create_staff(client, 'personB', role='dentist')
    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{staff_id}', json={'role': 'staff'})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        'SELECT role, is_dentist FROM users WHERE id = ?', (staff_id,)).fetchone()
    assert row['role'] == 'staff'
    assert row['is_dentist'] == 0


def test_put_invalid_role_returns_400(client):
    staff_id = _create_staff(client, 'personC')
    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{staff_id}', json={'role': 'superuser'})
    assert r.status_code == 400


def test_put_role_change_keeps_permission_grants_untouched(client):
    staff_id = _create_staff(client, 'personD', permissions=['patients.view'])
    _login_as(client, 'admin')
    client.put(f'/api/staff/{staff_id}', json={'role': 'dentist'})
    conn = dental_clinic.get_db_connection()
    granted = permissions.get_permissions(conn.cursor(), staff_id)
    conn.close()
    assert 'patients.view' in granted


def test_demote_last_active_admin_returns_400(client):
    # 'admin' (uid=1) is the only role='admin' account — demoting it would
    # leave the clinic with zero admins.
    _login_as(client, 'admin')
    r = client.put('/api/staff/1', json={'role': 'staff'})
    assert r.status_code == 400
    assert 'admin' in r.get_json()['error'].lower()
    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        "SELECT role FROM users WHERE id = 1").fetchone()
    assert row['role'] == 'admin'


def test_demote_admin_succeeds_when_another_admin_exists(client):
    second_id = _create_staff(client, 'owner2', role='admin')
    _login_as(client, 'admin')
    r = client.put('/api/staff/1', json={'role': 'staff'})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        "SELECT role FROM users WHERE id = 1").fetchone()
    assert row['role'] == 'staff'
    # sanity: the second admin is unaffected
    row2 = dental_clinic.get_db_connection(with_row_factory=True).execute(
        "SELECT role FROM users WHERE id = ?", (second_id,)).fetchone()
    assert row2['role'] == 'admin'


# --- POST /api/staff role at insert -------------------------------------------

def test_post_staff_with_role_sets_role_and_is_dentist(client):
    new_id = _create_staff(client, 'dr9', role='dentist')
    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        'SELECT role, is_dentist FROM users WHERE id = ?', (new_id,)).fetchone()
    assert row['role'] == 'dentist'
    assert row['is_dentist'] == 1


def test_post_staff_defaults_role_to_staff(client):
    new_id = _create_staff(client, 'fd9')
    row = dental_clinic.get_db_connection(with_row_factory=True).execute(
        'SELECT role FROM users WHERE id = ?', (new_id,)).fetchone()
    assert row['role'] == 'staff'


def test_post_staff_rejects_invalid_role(client):
    r = client.post('/api/staff', json={'username': 'bad1', 'password': 'pw123456', 'role': 'superuser'})
    assert r.status_code == 400


# --- /api/auth/me -------------------------------------------------------------

def test_auth_me_includes_role_email_and_verified(client, sent_emails):
    _login_as(client, 'admin')
    client.post('/api/profile/email', json={'email': 'doc@x.com'})
    r = client.get('/api/auth/me')
    body = r.get_json()
    assert body['role'] == 'admin'
    assert body['email'] == 'doc@x.com'
    assert body['email_verified'] is False

    code = sent_emails[0][2]['code']
    client.post('/api/profile/email/verify', json={'code': code})
    r2 = client.get('/api/auth/me')
    assert r2.get_json()['email_verified'] is True
