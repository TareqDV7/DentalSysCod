"""Task 9: staff email invites + admin security alert emails.

POST /api/staff with an email but no password issues a one-time 6-digit
code (auth_codes, same mechanism as OTP login/reset) that becomes the
temporary password; the invited account is force-flagged to change it on
first login (must_change_password=1) and email_verified=1 immediately —
receiving and using the invite code from that inbox already proves mailbox
ownership, so there is no separate verify-email step to redo. The invite
send is best-effort: a relay failure still returns 200 (the account exists
either way) but reports sent=False. Password-ful creation is unchanged.

_alert_admins(event, detail) fires a fire-and-forget 'security_alert' email
to every active, verified admin on account lockout, password change/reset,
and new-staff-account events. It must never raise, since it is called deep
inside auth-critical code paths that must not break if alerting fails.
"""
import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'invite_and_alerts_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


@pytest.fixture()
def sent_emails(monkeypatch):
    """Capture (to, template, params, lang) tuples for send_system_email;
    defaults to a successful send."""
    calls = []

    def _fake(to, template, params, lang='en'):
        calls.append((to, template, params, lang))
        return True, ''

    monkeypatch.setattr(dental_clinic, 'send_system_email', _fake)
    return calls


@pytest.fixture()
def async_alerts(monkeypatch):
    """Capture (to, template, params, lang) tuples for send_system_email_async."""
    calls = []

    def _fake(to, template, params, lang='en'):
        calls.append((to, template, params, lang))

    monkeypatch.setattr(dental_clinic, 'send_system_email_async', _fake)
    return calls


def _login_as(client, username='admin'):
    conn = dental_clinic.get_db_connection()
    uid = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()[0]
    conn.close()
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = username
    return uid


def _user_row(username):
    conn = dental_clinic.get_db_connection(with_row_factory=True)
    row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return row


def _seed_admin(username, email, email_verified=1, is_active=1):
    conn = dental_clinic.get_db_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, role, email, email_verified, "
        "is_active, must_change_password) VALUES (?, ?, 'admin', ?, ?, ?, 0)",
        (username, dental_clinic.hash_password('pw123456'), email, email_verified, is_active))
    conn.commit()
    conn.close()


def _seed_staff(username, email, email_verified=1):
    conn = dental_clinic.get_db_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, role, email, email_verified, "
        "is_active, must_change_password) VALUES (?, ?, 'staff', ?, ?, 1, 0)",
        (username, dental_clinic.hash_password('pw123456'), email, email_verified))
    conn.commit()
    conn.close()


# --- POST /api/staff invite branch -------------------------------------------

def test_invite_creates_user_flagged_for_change(client, sent_emails):
    _login_as(client, 'admin')
    r = client.post('/api/staff', json={'username': 'dr9', 'email': 'dr9@x.com'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['success'] is True
    assert body['invited'] is True
    assert body['sent'] is True
    assert body['id']

    row = _user_row('dr9')
    assert row['must_change_password'] == 1
    assert row['email_verified'] == 1
    assert row['email'] == 'dr9@x.com'

    assert len(sent_emails) == 1
    to, template, params, lang = sent_emails[0]
    assert to == 'dr9@x.com'
    assert template == 'staff_invite'
    assert params['username'] == 'dr9'
    code = params['code']
    assert isinstance(code, str) and len(code) == 6 and code.isdigit()
    assert lang == 'en'


def test_invite_login_with_code_then_forces_password_change(client, sent_emails):
    _login_as(client, 'admin')
    client.post('/api/staff', json={'username': 'dr9', 'email': 'dr9@x.com'})
    code = sent_emails[0][2]['code']

    with dental_clinic.app.test_client() as c2:
        r = c2.post('/login', data={'username': 'dr9', 'password': code},
                    follow_redirects=False)
        assert r.status_code in (301, 302)
        with c2.session_transaction() as sess:
            assert sess.get('uid')

        # First-run forced-change gate must catch the invited account too.
        r2 = c2.get('/')
        assert r2.status_code == 302
        assert r2.headers['Location'].endswith('/change-password')

        # And the change itself succeeds with the code as "current_password".
        r3 = c2.post('/change-password', data={
            'current_password': code,
            'new_password': 'newpass1',
            'confirm_password': 'newpass1',
        })
        assert r3.status_code == 302
        assert r3.headers['Location'].endswith('/')

    row = _user_row('dr9')
    assert row['must_change_password'] == 0


def test_invite_send_failure_still_returns_200_and_user_exists(client, monkeypatch):
    monkeypatch.setattr(dental_clinic, 'send_system_email',
                        lambda to, template, params, lang='en': (False, 'unreachable'))
    _login_as(client, 'admin')
    r = client.post('/api/staff', json={'username': 'dr10', 'email': 'dr10@x.com'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['invited'] is True
    assert body['sent'] is False

    row = _user_row('dr10')
    assert row is not None
    assert row['must_change_password'] == 1
    assert row['email_verified'] == 1


def test_no_email_no_password_returns_400(client):
    _login_as(client, 'admin')
    r = client.post('/api/staff', json={'username': 'dr11'})
    assert r.status_code == 400


def test_password_present_creation_is_unchanged(client, sent_emails):
    _login_as(client, 'admin')
    r = client.post('/api/staff', json={'username': 'dr12', 'password': 'pw123456'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body.get('invited', False) is False
    row = _user_row('dr12')
    assert row['must_change_password'] == 0
    assert row['email_verified'] == 0
    assert sent_emails == []


def test_password_and_email_together_uses_password_not_invite(client, sent_emails):
    _login_as(client, 'admin')
    r = client.post('/api/staff', json={
        'username': 'dr13', 'password': 'pw123456', 'email': 'dr13@x.com'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body.get('invited', False) is False
    row = _user_row('dr13')
    assert row['must_change_password'] == 0
    assert sent_emails == []


# --- _alert_admins ------------------------------------------------------------

def test_alert_admins_only_notifies_verified_active_admins(client, async_alerts):
    _seed_admin('admin2', 'verified-admin@x.com', email_verified=1)
    _seed_admin('admin3', 'unverified-admin@x.com', email_verified=0)
    _seed_staff('staffer', 'verified-staff@x.com', email_verified=1)

    dental_clinic._alert_admins('test_event', 'some detail')

    recipients = {call[0] for call in async_alerts}
    # 'admin' (the seeded default account) has no email on file, so it's
    # excluded the same way the unverified admin and the verified staffer are.
    assert recipients == {'verified-admin@x.com'}
    for call in async_alerts:
        assert call[1] == 'security_alert'
        assert call[2]['event'] == 'test_event'
        assert call[2]['detail'] == 'some detail'


def test_password_change_triggers_alert_to_verified_admins_only(client, async_alerts):
    _seed_admin('admin2', 'verified-admin@x.com', email_verified=1)
    _seed_admin('admin3', 'unverified-admin@x.com', email_verified=0)
    _login_as(client, 'admin')
    r = client.post('/change-password', data={
        'current_password': 'admin',
        'new_password': 'newpass1',
        'confirm_password': 'newpass1',
    })
    assert r.status_code == 302
    recipients = {call[0] for call in async_alerts}
    assert recipients == {'verified-admin@x.com'}


def test_staff_create_triggers_alert_to_verified_admins_only(client, sent_emails, async_alerts):
    _seed_admin('admin2', 'verified-admin@x.com', email_verified=1)
    _seed_admin('admin3', 'unverified-admin@x.com', email_verified=0)
    _login_as(client, 'admin')
    r = client.post('/api/staff', json={'username': 'newperson', 'password': 'pw123456'})
    assert r.status_code == 200, r.get_data(as_text=True)
    recipients = {call[0] for call in async_alerts}
    assert recipients == {'verified-admin@x.com'}


def test_alert_admins_never_raises_when_send_fails(client, monkeypatch):
    def _boom(to, template, params, lang='en'):
        raise RuntimeError('boom')

    monkeypatch.setattr(dental_clinic, 'send_system_email_async', _boom)
    _seed_admin('admin2', 'verified-admin@x.com', email_verified=1)

    # Must not raise even though the (monkeypatched) send call blows up.
    dental_clinic._alert_admins('test_event', 'detail')


def test_alert_admins_never_raises_on_db_error(client, monkeypatch):
    def _boom_conn(*args, **kwargs):
        raise RuntimeError('db unavailable')

    monkeypatch.setattr(dental_clinic, 'get_db_connection', _boom_conn)
    # Must not raise even though it can't open a DB connection at all.
    dental_clinic._alert_admins('test_event', 'detail')
