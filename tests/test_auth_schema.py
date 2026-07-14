"""Schema for email auth + role model (spec 2026-07-14)."""
import pytest

import dental_clinic


@pytest.fixture()
def db(tmp_path, monkeypatch):
    test_db = tmp_path / 'auth_schema_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    return str(test_db)


def test_users_new_columns(db):
    conn = dental_clinic.get_db_connection()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    conn.close()
    assert {'email', 'email_verified', 'role', 'failed_login_count', 'locked_until'} <= cols


def test_auth_tables_exist(db):
    conn = dental_clinic.get_db_connection()
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert 'auth_codes' in names and 'admin_recovery' in names


def test_email_unique_index(db):
    conn = dental_clinic.get_db_connection()
    idx = {r[1] for r in conn.execute("PRAGMA index_list(users)")}
    conn.close()
    assert 'idx_users_email' in idx


def test_email_unique_index_rejects_duplicate_emails(db):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, email) VALUES ('u1', 'x', 'a@example.com')")
    conn.commit()
    with pytest.raises(Exception):
        cur.execute(
            "INSERT INTO users (username, password_hash, email) VALUES ('u2', 'x', 'a@example.com')")
        conn.commit()
    conn.close()


def test_email_unique_index_allows_multiple_blank_emails(db):
    # Partial index only covers non-null/non-empty emails -- rows without an
    # email yet (e.g. legacy staff) must not collide with each other.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (username, password_hash) VALUES ('u1', 'x')")
    cur.execute("INSERT INTO users (username, password_hash) VALUES ('u2', 'x')")
    conn.commit()
    conn.close()


def test_role_migration(db):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (username, password_hash, is_dentist) VALUES ('d1', 'x', 1)")
    d1 = cur.lastrowid
    cur.execute("INSERT INTO users (username, password_hash, is_dentist) VALUES ('mgr', 'x', 1)")
    mgr = cur.lastrowid
    cur.execute(
        "INSERT INTO user_permissions (user_id, permission_key, granted) VALUES (?, 'staff.manage', 1)",
        (mgr,))
    cur.execute("INSERT INTO users (username, password_hash) VALUES ('desk', 'x')")
    desk = cur.lastrowid
    cur.execute("UPDATE users SET role = NULL")
    dental_clinic.migrate_user_roles(cur)
    conn.commit()
    roles = dict(cur.execute("SELECT id, role FROM users WHERE id IN (?,?,?)", (d1, mgr, desk)))
    assert roles[d1] == 'dentist'
    assert roles[mgr] == 'admin'      # staff.manage beats is_dentist
    assert roles[desk] == 'staff'
    # idempotent: second run changes nothing
    dental_clinic.migrate_user_roles(cur)
    conn.commit()
    assert roles == dict(cur.execute("SELECT id, role FROM users WHERE id IN (?,?,?)", (d1, mgr, desk)))
    conn.close()


def test_role_migration_does_not_touch_already_set_roles(db):
    # A manual demotion (or any pre-set role) must stick across re-runs of
    # migrate_user_roles -- it only fills in NULL/empty roles.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, is_dentist, role) VALUES ('d1', 'x', 1, 'staff')")
    d1 = cur.lastrowid
    conn.commit()
    dental_clinic.migrate_user_roles(cur)
    conn.commit()
    role = cur.execute("SELECT role FROM users WHERE id = ?", (d1,)).fetchone()[0]
    conn.close()
    assert role == 'staff'


def test_seeded_admin_gets_admin_role_on_init(db):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    role = cur.execute("SELECT role FROM users WHERE username = 'admin'").fetchone()[0]
    conn.close()
    assert role == 'admin'
