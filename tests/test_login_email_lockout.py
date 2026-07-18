"""Task 6: login accepts email OR username in the same 'username' form field;
5 consecutive failed attempts locks the account for LOCKOUT_MINUTES (per-user,
not global); a successful login resets the failure counter. Anti-enumeration:
wrong-password and no-such-user share the same generic error message; the
lockout message is allowed to differ (it's post-attempt throttling feedback)."""
from datetime import datetime, timedelta

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'login_lockout_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _seed_user(username='doc', email='doc@x.com', password='correcthorse',
                is_active=1, failed_login_count=0, locked_until=None):
    conn = dental_clinic.get_db_connection()
    conn.execute(
        'INSERT INTO users (username, password_hash, email, is_active, '
        'failed_login_count, locked_until, must_change_password) '
        'VALUES (?, ?, ?, ?, ?, ?, 0)',
        (username, dental_clinic.hash_password(password), email, is_active,
         failed_login_count, locked_until))
    conn.commit()
    conn.close()


def _row(username='doc'):
    return dental_clinic.get_db_connection().execute(
        'SELECT failed_login_count, locked_until FROM users WHERE username = ?',
        (username,)).fetchone()


def _login(client, identifier, password):
    return client.post('/login', data={'username': identifier, 'password': password},
                       follow_redirects=False)


def test_login_with_email_succeeds(client):
    _seed_user(username='doc', email='doc@x.com', password='correcthorse')
    resp = _login(client, 'doc@x.com', 'correcthorse')
    assert resp.status_code in (301, 302)
    with client.session_transaction() as sess:
        assert sess.get('uid')
        assert sess.get('uname') == 'doc'


def test_login_with_username_still_works(client):
    _seed_user(username='doc', email='doc@x.com', password='correcthorse')
    resp = _login(client, 'doc', 'correcthorse')
    assert resp.status_code in (301, 302)
    with client.session_transaction() as sess:
        assert sess.get('uid')


def test_sixth_attempt_with_correct_password_still_rejected_while_locked(client):
    _seed_user(username='doc', email='doc@x.com', password='correcthorse')
    for _ in range(5):
        resp = _login(client, 'doc@x.com', 'wrongpass')
        assert resp.status_code == 401
    row = _row()
    assert row[0] == 5
    assert row[1] is not None  # locked_until now set

    # 6th attempt: correct password, but still locked.
    resp = _login(client, 'doc@x.com', 'correcthorse')
    assert resp.status_code == 401
    assert b'too many failed attempts' in resp.data.lower()
    with client.session_transaction() as sess:
        assert not sess.get('uid')


def test_locked_until_in_past_allows_login_and_resets_counter(client):
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds')
    _seed_user(username='doc', email='doc@x.com', password='correcthorse',
               failed_login_count=5, locked_until=past)
    resp = _login(client, 'doc@x.com', 'correcthorse')
    assert resp.status_code in (301, 302)
    with client.session_transaction() as sess:
        assert sess.get('uid')
    row = _row()
    assert row[0] == 0
    assert row[1] is None


def test_inactive_user_with_email_cannot_login(client):
    _seed_user(username='doc', email='doc@x.com', password='correcthorse', is_active=0)
    resp = _login(client, 'doc@x.com', 'correcthorse')
    assert resp.status_code == 401
    assert b'invalid username or password' in resp.data.lower()
    with client.session_transaction() as sess:
        assert not sess.get('uid')
