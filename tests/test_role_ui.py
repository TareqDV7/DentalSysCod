"""Task 15: role-aware staff management UI.

Backend coverage: `new_password` on PUT /api/staff/<id> — the admin-issued
local password reset (no email involved, the zero-internet path). Sets
password_hash + must_change_password=1 and clears the lockout counters;
rejects passwords under 4 characters without touching the row; composes
cleanly with other fields (e.g. role) in the same PUT.

Frontend coverage: static markup/function-presence checks mirroring
tests/test_calendar_dentist_filter_ui.py's style (no Playwright) for the
Manage Staff email/role columns + reset-password button, the recovery-code
modal, the profile email/verify controls, and the calendar-dentist-filter
hide-for-role='dentist' wiring inside applyPermissionGating().
"""
import subprocess
import sys
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

import dental_clinic
from templates import HTML_TEMPLATE

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'role_ui_test.db'
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


# --- PUT /api/staff/<id> {new_password} --------------------------------------

def test_reset_password_updates_hash_new_authenticates_old_does_not(client):
    staff_id = _create_staff(client, 'dr1', password='oldpass1')
    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{staff_id}', json={'new_password': 'newpass1'})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = _user_row('dr1')
    assert check_password_hash(row['password_hash'], 'newpass1') is True
    assert check_password_hash(row['password_hash'], 'oldpass1') is False


def test_reset_password_sets_must_change_password_and_clears_lockout(client):
    staff_id = _create_staff(client, 'dr2', password='oldpass1')
    conn = dental_clinic.get_db_connection()
    conn.execute(
        "UPDATE users SET must_change_password = 0, failed_login_count = 3, "
        "locked_until = '2099-01-01T00:00:00' WHERE id = ?", (staff_id,))
    conn.commit()
    conn.close()

    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{staff_id}', json={'new_password': 'newpass1'})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = _user_row('dr2')
    assert row['must_change_password'] == 1
    assert row['failed_login_count'] == 0
    assert row['locked_until'] is None


def test_reset_password_too_short_returns_400_and_row_unchanged(client):
    staff_id = _create_staff(client, 'dr3', password='oldpass1')
    _login_as(client, 'admin')
    before = _user_row('dr3')['password_hash']
    r = client.put(f'/api/staff/{staff_id}', json={'new_password': 'abc'})
    assert r.status_code == 400
    after = _user_row('dr3')['password_hash']
    assert before == after


def test_reset_password_combined_with_role_change_both_apply(client):
    staff_id = _create_staff(client, 'dr4', password='oldpass1')
    _login_as(client, 'admin')
    r = client.put(f'/api/staff/{staff_id}', json={'role': 'dentist', 'new_password': 'newpass1'})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = _user_row('dr4')
    assert row['role'] == 'dentist'
    assert row['is_dentist'] == 1
    assert check_password_hash(row['password_hash'], 'newpass1') is True


# --- Static markup/function presence (Part B/C UI) ----------------------------

def test_staff_add_email_field_present():
    assert 'id="staff-add-email"' in HTML_TEMPLATE


def test_staff_add_role_select_present():
    assert 'id="staff-add-role"' in HTML_TEMPLATE


def test_update_staff_role_function_present():
    assert 'function updateStaffRole(' in HTML_TEMPLATE


def test_reset_staff_password_function_present():
    assert 'function resetStaffPassword(' in HTML_TEMPLATE


def test_recovery_code_modal_present():
    assert 'id="recovery-code-modal"' in HTML_TEMPLATE


def test_generate_recovery_code_function_present():
    assert 'function generateRecoveryCode(' in HTML_TEMPLATE


def test_acct_email_field_present():
    assert 'id="acct-email"' in HTML_TEMPLATE


def test_save_account_email_function_present():
    assert 'function saveAccountEmail(' in HTML_TEMPLATE


def test_verify_account_email_function_present():
    assert 'function verifyAccountEmail(' in HTML_TEMPLATE


def test_apply_permission_gating_hides_calendar_dentist_filter():
    # Slice the function body out (up to the next top-level function
    # declaration) rather than a substring check against the whole file --
    # 'calendar-dentist-filter' legitimately appears elsewhere (the select's
    # own definition, populateCalendarDentistFilter, etc).
    start = HTML_TEMPLATE.index('function applyPermissionGating()')
    end = HTML_TEMPLATE.index('async function applyAuthMe()')
    assert start < end
    body = HTML_TEMPLATE[start:end]
    assert 'calendar-dentist-filter' in body
    assert "currentUserRole === 'dentist'" in body


# --- Import sanity -------------------------------------------------------------

def test_dental_clinic_imports_cleanly():
    proc = subprocess.run(
        [sys.executable, '-c', 'import dental_clinic'],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr


def test_templates_imports_cleanly():
    proc = subprocess.run(
        [sys.executable, '-c', 'import templates'],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
