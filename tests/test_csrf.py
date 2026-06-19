import pytest

import dental_clinic


@pytest.fixture()
def app_ctx(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    return dental_clinic.app


def test_get_or_create_csrf_token_is_stable_within_session(app_ctx):
    with app_ctx.test_request_context('/'):
        from flask import session
        first = dental_clinic._get_or_create_csrf_token()
        second = dental_clinic._get_or_create_csrf_token()
        assert first and isinstance(first, str)
        assert first == second
        assert session['csrf_token'] == first


def test_new_csrf_token_is_random(app_ctx):
    a = dental_clinic._new_csrf_token()
    b = dental_clinic._new_csrf_token()
    assert a != b and len(a) >= 20


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def test_unsafe_without_token_is_rejected(client):
    # csrf=False => the auto-pass client does NOT attach a token.
    resp = client.post('/api/appointments', json={'patient_id': 1}, csrf=False)
    assert resp.status_code == 403
    assert resp.get_json().get('reason') == 'csrf'


def test_unsafe_with_matching_token_passes_csrf(client):
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'known-token'
    # Bad patient id still returns a non-403 (CSRF passed, handler ran).
    resp = client.post('/api/appointments', json={'patient_id': 999999},
                       headers={'X-CSRFToken': 'known-token'}, csrf=False)
    assert resp.status_code != 403


def test_get_is_never_blocked(client):
    resp = client.get('/api/appointments', csrf=False)
    assert resp.status_code != 403


def test_kill_switch_disables_enforcement(client, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_CSRF_ENABLED', False)
    resp = client.post('/api/appointments', json={'patient_id': 999999}, csrf=False)
    assert resp.status_code != 403


def test_x_clinic_token_header_exempts(client):
    resp = client.post('/api/appointments', json={'patient_id': 999999},
                       headers={'X-Clinic-Token': 'whatever'}, csrf=False)
    assert resp.status_code != 403  # exempt: handler ran (mobile/sync path)


def test_authorization_header_exempts(client):
    resp = client.post('/api/appointments', json={'patient_id': 999999},
                       headers={'Authorization': 'Bearer x'}, csrf=False)
    assert resp.status_code != 403


def test_query_arg_clinic_token_does_not_exempt(client):
    resp = client.post('/api/appointments?clinic_token=whatever',
                       json={'patient_id': 999999}, csrf=False)
    assert resp.status_code == 403
    assert resp.get_json().get('reason') == 'csrf'


def test_index_html_contains_csrf_meta_and_interceptor(client):
    import sqlite3
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute('UPDATE users SET must_change_password = 0')
    conn.commit()
    conn.close()
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'admin'
    resp = client.get('/')
    html = resp.get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert 'X-CSRFToken' in html  # the fetch interceptor is present


def test_login_without_csrf_field_is_rejected(client):
    resp = client.post('/login', data={'username': 'admin', 'password': 'admin'},
                       csrf=False)
    assert resp.status_code == 400
    assert b'reload' in resp.data.lower() or b'security' in resp.data.lower()


def test_login_with_csrf_field_succeeds_and_rotates_token(client):
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'pre-login-token'
    resp = client.post('/login',
                       data={'username': 'admin', 'password': 'admin',
                             'csrf_token': 'pre-login-token'},
                       csrf=False, follow_redirects=False)
    assert resp.status_code in (301, 302)  # redirect on success
    with client.session_transaction() as sess:
        assert sess.get('uid')
        assert sess.get('csrf_token') and sess['csrf_token'] != 'pre-login-token'


def test_login_page_get_contains_csrf_field(client):
    resp = client.get('/login')
    assert b'name="csrf_token"' in resp.data
