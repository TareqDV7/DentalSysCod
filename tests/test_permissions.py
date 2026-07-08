"""Staff permission storage and the auto-grant-all migration for pre-existing
users (the single 'admin' account that predates RBAC)."""
import sqlite3

import pytest

import dental_clinic
import permissions


@pytest.fixture()
def db(tmp_path, monkeypatch):
    test_db = tmp_path / 'perm_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    return str(test_db)


def test_existing_admin_auto_granted_all_permissions(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    granted = permissions.get_permissions(cur, uid)
    conn.close()
    assert granted == set(permissions.PERMISSION_KEYS)


def test_set_permission_revokes_and_grants(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    permissions.set_permission(cur, uid, 'billing.edit', False)
    conn.commit()
    granted = permissions.get_permissions(cur, uid)
    assert 'billing.edit' not in granted
    permissions.set_permission(cur, uid, 'billing.edit', True)
    conn.commit()
    granted = permissions.get_permissions(cur, uid)
    assert 'billing.edit' in granted
    conn.close()


def test_set_permission_rejects_unknown_key(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    with pytest.raises(ValueError):
        permissions.set_permission(cur, uid, 'not.a.real.key', True)
    conn.close()


def test_migration_does_not_regrant_after_explicit_revoke(db):
    # Re-running the migration (as happens on every init_database() call, e.g.
    # every app start) must not silently re-grant a permission an Owner
    # deliberately revoked from themselves or another account.
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    permissions.set_permission(cur, uid, 'data_tools.use', False)
    conn.commit()
    conn.close()

    dental_clinic.init_database()  # re-run migration

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    granted = permissions.get_permissions(cur, uid)
    conn.close()
    assert 'data_tools.use' not in granted


def test_new_user_with_no_permission_rows_gets_none_by_default(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
        ('frontdesk', dental_clinic.hash_password('x'), 'Front Desk'))
    new_uid = cur.lastrowid
    conn.commit()
    # A brand-new user (created after the app already exists) must NOT be
    # auto-granted anything — only the pre-existing migrated admin gets
    # grant-all. New accounts start with zero permissions until an Owner
    # explicitly grants some via the Manage Staff UI (Task 4/5).
    granted = permissions.get_permissions(cur, new_uid)
    conn.close()
    assert granted == set()


def test_audit_log_captures_actor_from_session(tmp_path, monkeypatch):
    # Test that audit_logs captures the acting staff member from session.
    test_db = tmp_path / 'audit_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()

    app = dental_clinic.app
    app.config['TESTING'] = True

    # Create a test patient
    conn = sqlite3.connect(str(test_db))
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                ('Test', 'Patient', '0500'))
    patient_id = cur.lastrowid
    conn.commit()
    conn.close()

    with app.test_client() as client:
        # Set session uid=1 and uname='admin' (the pre-created admin from init)
        with client.session_transaction() as sess:
            sess['uid'] = 1
            sess['uname'] = 'admin'

        # POST to /api/billing which calls append_audit_log with entity_type='billing'
        client.post('/api/billing', json={
            'patient_id': patient_id,
            'subtotal': 100.0,
            'discount': 0,
            'paid_amount': 0
        })

    # Query the audit log to verify actor fields are populated
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT actor_user_id, actor_username FROM audit_logs WHERE entity_type = 'billing' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row['actor_user_id'] == 1
    assert row['actor_username'] == 'admin'


def test_session_user_without_permission_gets_403(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
        ('frontdesk', dental_clinic.hash_password('x'), 'Front Desk'))
    uid = cur.lastrowid
    conn.commit()
    conn.close()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['uid'] = uid
            sess['uname'] = 'frontdesk'
        r = client.post('/api/expenses', json={
            'category': 'Test', 'amount': 10, 'expense_date': '01/01/2026',
            'payment_status': 'paid'})
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'permission_denied'


def test_session_user_with_permission_succeeds(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
        ('frontdesk', dental_clinic.hash_password('x'), 'Front Desk'))
    uid = cur.lastrowid
    permissions.set_permission(cur, uid, 'expenses.edit', True)
    conn.commit()
    conn.close()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['uid'] = uid
            sess['uname'] = 'frontdesk'
        r = client.post('/api/expenses', json={
            'category': 'Test', 'amount': 10, 'expense_date': '01/01/2026',
            'payment_status': 'paid'})
    assert r.status_code == 200


def test_device_token_request_bypasses_permission_gate(db):
    # Mobile's device-token path must be completely unaffected by RBAC — it
    # never carries a session, so the gate must not apply to it at all.
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as client:
        r = client.get('/api/patients', headers={'X-Device-Token': 'irrelevant-in-this-test'})
    # No session at all and no permission gate applied — falls through to
    # whatever the route's own logic does (200, or 401 from device-token
    # validation elsewhere — NOT 403 permission_denied).
    assert r.status_code != 403 or r.get_json().get('reason') != 'permission_denied'
