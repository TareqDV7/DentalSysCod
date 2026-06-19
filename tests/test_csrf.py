import secrets

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
