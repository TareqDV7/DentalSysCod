"""First-run forced password change (must_change_password).

The seeded admin starts on the well-known 'admin'/'admin' default. On first login
the portal must force a one-time password change before the SPA loads — but only
at the HTML portal entry points, never on the open offline-first data/sync API.
"""
import sqlite3

import pytest

import dental_clinic


def _init_db(tmp_path, monkeypatch, admin_password=None):
    db = tmp_path / 'fpc.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    if admin_password is None:
        monkeypatch.delenv('CLINIC_ADMIN_PASSWORD', raising=False)
    else:
        monkeypatch.setenv('CLINIC_ADMIN_PASSWORD', admin_password)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    return db


def _flag(db):
    return dental_clinic.get_db_connection().execute(
        "SELECT must_change_password FROM users WHERE username='admin'").fetchone()[0]


def _login(client, uid=1):
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = 'admin'


def test_default_admin_is_flagged_for_change(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    assert _flag(db) == 1


def test_env_password_is_not_flagged(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password='s3cret-pw')
    assert _flag(db) == 0


def test_portal_redirects_to_change_when_flagged(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.get('/')
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/change-password')


def test_change_page_renders_for_flagged_user(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.get('/change-password')
        assert r.status_code == 200
        assert b'Secure your account' in r.data


def test_successful_change_clears_flag_and_unlocks_portal(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.post('/change-password', data={
            'current_password': 'admin',
            'new_password': 'newpass1',
            'confirm_password': 'newpass1',
        })
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/')
        assert _flag(db) == 0
        # Portal now loads instead of redirecting.
        assert c.get('/').status_code == 200


def test_mismatched_confirm_rejected(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.post('/change-password', data={
            'current_password': 'admin',
            'new_password': 'newpass1',
            'confirm_password': 'different',
        })
        assert r.status_code == 400
        assert _flag(db) == 1  # still flagged


def test_same_password_rejected(tmp_path, monkeypatch):
    db = _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.post('/change-password', data={
            'current_password': 'admin',
            'new_password': 'admin',
            'confirm_password': 'admin',
        })
        assert r.status_code == 400
        assert _flag(db) == 1


def test_wrong_current_rejected(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        r = c.post('/change-password', data={
            'current_password': 'WRONG',
            'new_password': 'newpass1',
            'confirm_password': 'newpass1',
        })
        assert r.status_code == 400


def test_open_api_not_blocked_for_flagged_session(tmp_path, monkeypatch):
    # The offline-first data API must keep working even while a flagged browser
    # session exists — real mobile callers carry no session 'uid', and even a
    # flagged staff session must not get the API gated.
    _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        _login(c)
        assert c.get('/api/patients').status_code == 200


def test_change_page_requires_login(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch, admin_password=None)
    with dental_clinic.app.test_client() as c:
        r = c.get('/change-password')
        assert r.status_code == 302
        assert '/login' in r.headers['Location']
