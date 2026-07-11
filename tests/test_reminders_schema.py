"""reminders_log table is created by init_database() and enforces the
appointment_id FK the dispatch loop's idempotency check relies on."""
import pytest

import dental_clinic


@pytest.fixture()
def db(tmp_path, monkeypatch):
    test_db = tmp_path / 'reminders_schema_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    return str(test_db)


def test_reminders_log_table_exists_with_expected_columns(db):
    # init_database() writes via get_db_connection(), which is SQLCipher-
    # encrypted in desktop mode -- a plain sqlite3.connect() can't read it
    # back, so this must go through the same connection helper (matches
    # tests/test_permissions.py's established convention).
    conn = dental_clinic.get_db_connection()
    cols = {row[1] for row in conn.execute('PRAGMA table_info(reminders_log)')}
    conn.close()
    assert cols == {'id', 'appointment_id', 'channel', 'status', 'error_detail', 'sent_at'}


def test_reminders_log_insert_roundtrip(db):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '0599')"
    )
    pid = cur.lastrowid
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type) "
        "VALUES (?, '2026-08-01 10:00:00', 'Checkup')",
        (pid,),
    )
    aid = cur.lastrowid
    cur.execute(
        "INSERT INTO reminders_log (appointment_id, channel, status) VALUES (?, 'email', 'sent')",
        (aid,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT appointment_id, channel, status FROM reminders_log WHERE appointment_id = ?", (aid,)
    ).fetchone()
    conn.close()
    assert row == (aid, 'email', 'sent')
