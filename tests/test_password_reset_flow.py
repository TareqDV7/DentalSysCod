"""Task 7: forgot/reset password via emailed OTP.

POST /api/login/forgot always returns 200 {'sent': True} — byte-identical
regardless of whether the account exists, has a verified email, or the email
relay fails. The real outcome is only ever logged server-side. POST
/api/login/reset returns one generic 400 {'error': 'Invalid or expired code'}
for any code/account failure (only the too-short-password 400 differs, since
that's pre-validation before any user lookup happens).
"""
from datetime import datetime, timedelta

import pytest
from flask import jsonify

import dental_clinic

# Built via the app's own jsonify so byte-for-byte comparisons below aren't
# tripped up by Flask's actual separator/whitespace/sort-key conventions.
with dental_clinic.app.app_context():
    GENERIC_SENT = jsonify({'sent': True}).get_data()
    GENERIC_FAIL = jsonify({'error': 'Invalid or expired code'}).get_data()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'password_reset_test.db'
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


def _seed_user(username='doc', email='doc@x.com', password='correcthorse',
               is_active=1, email_verified=1, failed_login_count=0, locked_until=None):
    conn = dental_clinic.get_db_connection()
    conn.execute(
        'INSERT INTO users (username, password_hash, email, email_verified, is_active, '
        'failed_login_count, locked_until, must_change_password) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
        (username, dental_clinic.hash_password(password), email, email_verified, is_active,
         failed_login_count, locked_until))
    conn.commit()
    conn.close()


def _row(username='doc'):
    return dental_clinic.get_db_connection(with_row_factory=True).execute(
        'SELECT id, password_hash, failed_login_count, locked_until FROM users WHERE username = ?',
        (username,)).fetchone()


def _forgot(client, identifier):
    return client.post('/api/login/forgot', json={'identifier': identifier})


def _reset(client, identifier, code, new_password):
    return client.post('/api/login/reset',
                       json={'identifier': identifier, 'code': code, 'new_password': new_password})


def test_forgot_unknown_identifier_returns_generic_sent_true(client, sent_emails):
    resp = _forgot(client, 'nobody@nowhere.com')
    assert resp.status_code == 200
    assert resp.data == GENERIC_SENT
    assert sent_emails == []


def test_forgot_known_verified_user_sends_and_matches_unknown_response(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', email_verified=1)
    known_resp = _forgot(client, 'doc@x.com')
    unknown_resp = _forgot(client, 'nobody@nowhere.com')
    assert known_resp.status_code == unknown_resp.status_code == 200
    assert known_resp.data == unknown_resp.data == GENERIC_SENT
    # The real outcome (a send happened) is only visible server-side.
    assert len(sent_emails) == 1
    to, template, params, lang = sent_emails[0]
    assert to == 'doc@x.com'
    assert template == 'password_reset'
    assert 'code' in params and len(params['code']) == 6
    assert lang == 'en'


def test_forgot_known_user_without_email_same_response_no_send(client, sent_emails):
    _seed_user(username='doc', email='', email_verified=0)
    resp = _forgot(client, 'doc')
    assert resp.status_code == 200
    assert resp.data == GENERIC_SENT
    assert sent_emails == []


def test_forgot_known_user_unverified_email_same_response_no_send(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', email_verified=0)
    resp = _forgot(client, 'doc@x.com')
    assert resp.status_code == 200
    assert resp.data == GENERIC_SENT
    assert sent_emails == []


def test_forgot_relay_failure_same_generic_response(client, monkeypatch):
    _seed_user(username='doc', email='doc@x.com', email_verified=1)
    monkeypatch.setattr(dental_clinic, 'send_system_email',
                        lambda to, template, params, lang='en': (False, 'unreachable'))
    resp = _forgot(client, 'doc@x.com')
    assert resp.status_code == 200
    assert resp.data == GENERIC_SENT


def test_forgot_empty_identifier_returns_generic_response(client, sent_emails):
    resp = _forgot(client, '')
    assert resp.status_code == 200
    assert resp.data == GENERIC_SENT
    assert sent_emails == []


def test_forgot_reset_happy_path_end_to_end(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', password='oldpassword', email_verified=1)
    resp = _forgot(client, 'doc@x.com')
    assert resp.status_code == 200
    code = sent_emails[0][2]['code']

    reset_resp = _reset(client, 'doc@x.com', code, 'brandnewpass')
    assert reset_resp.status_code == 200
    assert reset_resp.get_json() == {'success': True}

    login_resp = client.post('/login', data={'username': 'doc@x.com', 'password': 'brandnewpass'},
                             follow_redirects=False)
    assert login_resp.status_code in (301, 302)


def test_reset_wrong_code_returns_generic_400(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', email_verified=1)
    _forgot(client, 'doc@x.com')
    resp = _reset(client, 'doc@x.com', '000000', 'brandnewpass')
    assert resp.status_code == 400
    assert resp.data == GENERIC_FAIL


def test_reset_unknown_identifier_returns_generic_400(client):
    resp = _reset(client, 'nobody@nowhere.com', '123456', 'brandnewpass')
    assert resp.status_code == 400
    assert resp.data == GENERIC_FAIL


def test_reset_expired_code_returns_generic_400(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', email_verified=1)
    _forgot(client, 'doc@x.com')
    code = sent_emails[0][2]['code']
    conn = dental_clinic.get_db_connection()
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds')
    conn.execute('UPDATE auth_codes SET expires_at = ?', (past,))
    conn.commit()
    conn.close()
    resp = _reset(client, 'doc@x.com', code, 'brandnewpass')
    assert resp.status_code == 400
    assert resp.data == GENERIC_FAIL


def test_reset_code_is_single_use(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', password='oldpassword', email_verified=1)
    _forgot(client, 'doc@x.com')
    code = sent_emails[0][2]['code']
    first = _reset(client, 'doc@x.com', code, 'brandnewpass')
    assert first.status_code == 200
    second = _reset(client, 'doc@x.com', code, 'anotherpass')
    assert second.status_code == 400
    assert second.data == GENERIC_FAIL


def test_reset_clears_lockout_and_resets_failed_count(client, sent_emails):
    locked_until = (datetime.utcnow() + timedelta(minutes=15)).isoformat(timespec='seconds')
    _seed_user(username='doc', email='doc@x.com', email_verified=1,
               failed_login_count=5, locked_until=locked_until)
    _forgot(client, 'doc@x.com')
    code = sent_emails[0][2]['code']
    resp = _reset(client, 'doc@x.com', code, 'brandnewpass')
    assert resp.status_code == 200
    row = _row('doc')
    assert row['failed_login_count'] == 0
    assert row['locked_until'] is None


def test_reset_too_short_password_returns_distinct_400(client, sent_emails):
    _seed_user(username='doc', email='doc@x.com', email_verified=1)
    _forgot(client, 'doc@x.com')
    code = sent_emails[0][2]['code']
    resp = _reset(client, 'doc@x.com', code, 'abc')
    assert resp.status_code == 400
    assert resp.data != GENERIC_FAIL
    assert resp.get_json()['error'] != 'Invalid or expired code'
