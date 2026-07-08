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
