"""Task 14: login page tiles + forgot-password + recovery-code UI.

The rewritten LOGIN_TEMPLATE renders a Windows-style tile grid of active
users (<=12) with a fallback to the classic identifier+password form, plus
always-present forgot-password and recovery-code panels wired to the
pre-existing /api/login/forgot, /api/login/reset and /api/login/recover
routes (Tasks 5-10). This file checks both the static template markup and
the dynamic tile-list behavior against a seeded DB.
"""
import dental_clinic
import permissions
import pytest

from templates import LOGIN_TEMPLATE


# ---------------------------------------------------------------------------
# Static string assertions (mirrors tests/test_calendar_dentist_filter_ui.py)
# ---------------------------------------------------------------------------

def test_login_tiles_container_present():
    assert 'id="login-tiles"' in LOGIN_TEMPLATE


def test_forgot_password_panel_present():
    assert 'id="forgot-password-panel"' in LOGIN_TEMPLATE


def test_recovery_panel_present():
    assert 'id="recovery-panel"' in LOGIN_TEMPLATE


def test_classic_login_form_present():
    assert 'id="classic-login-form"' in LOGIN_TEMPLATE
    assert 'method="POST" action="/login"' in LOGIN_TEMPLATE


def test_show_classic_login_control_present():
    assert 'id="show-classic-login"' in LOGIN_TEMPLATE


def test_forgot_and_recovery_fetch_targets_present():
    assert "'/api/login/forgot'" in LOGIN_TEMPLATE
    assert "'/api/login/reset'" in LOGIN_TEMPLATE
    assert "'/api/login/recover'" in LOGIN_TEMPLATE


def test_recovery_result_and_warning_markup_present():
    assert 'id="recovery-result"' in LOGIN_TEMPLATE
    assert 'id="recovery-new-code"' in LOGIN_TEMPLATE
    assert 'will not be shown again' in LOGIN_TEMPLATE


def test_hidden_csrf_and_next_fields_preserved():
    assert 'name="csrf_token"' in LOGIN_TEMPLATE
    assert 'name="next"' in LOGIN_TEMPLATE


# ---------------------------------------------------------------------------
# Dynamic tests against a seeded DB
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'login_tiles_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _user(username, role='staff', display_name=None, is_active=1):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist, role, is_active) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (username, dental_clinic.hash_password('x'), display_name or '',
         1 if role == 'dentist' else 0, role, is_active))
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def test_tiles_present_for_small_user_count(client):
    # Seeded admin + 3 more users = 4 total, well under the 12-tile cap.
    _user('drsmith', role='dentist', display_name='Dr. Smith')
    _user('frontdesk', role='staff', display_name='Front Desk')
    _user('office2', role='staff')  # blank display_name -> falls back to username

    r = client.get('/login')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="login-tiles"' in html
    assert 'data-username="admin"' in html
    assert 'data-username="drsmith"' in html
    assert 'data-username="frontdesk"' in html
    assert 'data-username="office2"' in html


def test_no_tiles_when_over_twelve_users(client):
    # 1 seeded admin + 12 new users = 13 active users, over the cap.
    for i in range(12):
        _user(f'user{i}')

    r = client.get('/login')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="login-tiles"' not in html
    # Classic form must still be usable as the fallback.
    assert 'id="classic-login-form"' in html


def test_forgot_and_recovery_markup_present_regardless_of_tile_count(client):
    for i in range(12):
        _user(f'bulk{i}')

    r = client.get('/login')
    html = r.get_data(as_text=True)
    assert 'id="forgot-password-panel"' in html
    assert 'id="recovery-panel"' in html


def test_inactive_user_excluded_from_tiles(client):
    _user('activeuser', role='staff', display_name='Active User')
    _user('goneuser', role='staff', display_name='Gone User', is_active=0)

    r = client.get('/login')
    html = r.get_data(as_text=True)
    assert 'data-username="activeuser"' in html
    assert 'data-username="goneuser"' not in html


def test_tile_role_badges_mapped(client):
    _user('drjones', role='dentist', display_name='Dr. Jones')
    _user('adminb', role='admin', display_name='Admin Two')

    r = client.get('/login')
    html = r.get_data(as_text=True)
    assert 'data-role="dentist"' in html
    assert 'data-role="admin"' in html
