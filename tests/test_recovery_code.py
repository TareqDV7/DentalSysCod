"""Task 10: one-time admin recovery code — offline escape hatch when the
admin is locked out and email is unavailable.

POST /api/settings/recovery-code (staff.manage-gated): returns the plaintext
XXXX-XXXX-XXXX-XXXX exactly once, voiding any prior unused code.

POST /api/login/recover (pre-auth): {code, new_password} redeems the code,
resets the OLDEST active admin's password, clears their lockout, auto-issues
a replacement code, and returns it alongside the recovered username.
"""
import pytest

import dental_clinic
import permissions


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'recovery_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _login_as(client, username='admin'):
    conn = dental_clinic.get_db_connection()
    uid = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()[0]
    conn.close()
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = username
    return uid


def _generate(client):
    r = client.post('/api/settings/recovery-code')
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()['code']


def test_generate_returns_formatted_code(client):
    _login_as(client)
    code = _generate(client)
    parts = code.split('-')
    assert len(parts) == 4 and all(len(p) == 4 for p in parts)
    # never stored in plaintext
    conn = dental_clinic.get_db_connection()
    rows = conn.execute('SELECT code_hash FROM admin_recovery').fetchall()
    conn.close()
    assert rows and all(code not in r[0] for r in rows)


def test_generate_requires_staff_manage(client):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, role) "
        "VALUES ('plain', ?, 'P', 'staff')", (dental_clinic.hash_password('pw'),))
    conn.commit()
    conn.close()
    _login_as(client, 'plain')
    r = client.post('/api/settings/recovery-code')
    assert r.status_code == 403


def test_recover_resets_oldest_admin_and_rotates_code(client, monkeypatch):
    alerts = []
    monkeypatch.setattr(dental_clinic, 'send_system_email_async',
                        lambda *a, **k: alerts.append(a))
    _login_as(client)
    code = _generate(client)
    with client.session_transaction() as sess:
        sess.clear()

    r = client.post('/api/login/recover',
                    json={'code': code, 'new_password': 'rescued1'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['success'] is True
    assert body['username'] == 'admin'
    fresh = body['new_recovery_code']
    assert fresh != code and len(fresh.split('-')) == 4

    # old code dead, even repeated
    r2 = client.post('/api/login/recover',
                     json={'code': code, 'new_password': 'again123'})
    assert r2.status_code == 400

    # admin can now log in with the new password
    r3 = client.post('/login', data={'username': 'admin', 'password': 'rescued1'})
    assert r3.status_code == 302


def test_recover_clears_lockout(client):
    _login_as(client)
    code = _generate(client)
    conn = dental_clinic.get_db_connection()
    conn.execute("UPDATE users SET failed_login_count = 5, "
                 "locked_until = '2099-01-01T00:00:00' WHERE username = 'admin'")
    conn.commit()
    conn.close()
    with client.session_transaction() as sess:
        sess.clear()

    r = client.post('/api/login/recover',
                    json={'code': code, 'new_password': 'rescued1'})
    assert r.status_code == 200
    conn = dental_clinic.get_db_connection(with_row_factory=True)
    row = conn.execute("SELECT failed_login_count, locked_until FROM users "
                       "WHERE username = 'admin'").fetchone()
    conn.close()
    assert row['failed_login_count'] == 0 and row['locked_until'] is None


def test_recover_wrong_code_400(client):
    _login_as(client)
    _generate(client)
    with client.session_transaction() as sess:
        sess.clear()
    r = client.post('/api/login/recover',
                    json={'code': 'AAAA-BBBB-CCCC-DDDD', 'new_password': 'rescued1'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'Invalid recovery code'


def test_regenerate_voids_prior(client):
    _login_as(client)
    old = _generate(client)
    _generate(client)  # regenerating voids the first
    with client.session_transaction() as sess:
        sess.clear()
    r = client.post('/api/login/recover',
                    json={'code': old, 'new_password': 'rescued1'})
    assert r.status_code == 400


def test_recover_short_password_400(client):
    _login_as(client)
    code = _generate(client)
    with client.session_transaction() as sess:
        sess.clear()
    r = client.post('/api/login/recover', json={'code': code, 'new_password': 'ab'})
    assert r.status_code == 400
