"""Pure logic for the reminder dispatch loop: which appointments are due,
whether a reminder was already sent (idempotency), and message rendering.
No Flask, no threading, no network — cursor-level functions only, mirrors
the style of inventory.py/patient_dedupe.py/permissions.py."""
from datetime import datetime, timedelta, timezone

import pytest

import dental_clinic
import reminder_dispatch


@pytest.fixture()
def db(tmp_path, monkeypatch):
    test_db = tmp_path / 'dispatch_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    # init_database() writes via get_db_connection(), which is SQLCipher-
    # encrypted in desktop mode -- a plain sqlite3.connect() can't read it
    # back, so reads must go through the same connection helper (matches
    # tests/test_permissions.py's established convention).
    conn = dental_clinic.get_db_connection(with_row_factory=True)
    yield conn
    conn.close()


def _patient(conn, phone='0599000000', email='p@example.com'):
    cur = conn.execute(
        "INSERT INTO patients (first_name, last_name, phone, email) VALUES ('Sam', 'Lee', ?, ?)",
        (phone, email),
    )
    return cur.lastrowid


def _appt(conn, patient_id, appointment_date, treatment_type='Checkup', status='scheduled'):
    cur = conn.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type, status) "
        "VALUES (?, ?, ?, ?)",
        (patient_id, appointment_date, treatment_type, status),
    )
    return cur.lastrowid


# now_utc is fixed at 2026-08-01 10:00:00 UTC for every test.
NOW_UTC = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_finds_appointment_within_lead_window_utc_clinic(db):
    pid = _patient(db)
    # Clinic tz = UTC, appointment in 2 hours, lead_hours=24 -> due now.
    _appt(db, pid, '2026-08-01 12:00:00')
    due = reminder_dispatch.find_due_appointments(db, NOW_UTC, lead_hours=24, clinic_tz_name='UTC')
    assert len(due) == 1
    assert due[0]['patient_name'] == 'Sam Lee'


def test_excludes_appointment_outside_lead_window(db):
    pid = _patient(db)
    _appt(db, pid, '2026-08-05 12:00:00')  # 4 days out
    due = reminder_dispatch.find_due_appointments(db, NOW_UTC, lead_hours=24, clinic_tz_name='UTC')
    assert due == []


def test_excludes_past_appointment(db):
    pid = _patient(db)
    _appt(db, pid, '2026-07-30 12:00:00')  # already happened
    due = reminder_dispatch.find_due_appointments(db, NOW_UTC, lead_hours=24, clinic_tz_name='UTC')
    assert due == []


def test_excludes_cancelled_appointment(db):
    pid = _patient(db)
    _appt(db, pid, '2026-08-01 12:00:00', status='cancelled')
    due = reminder_dispatch.find_due_appointments(db, NOW_UTC, lead_hours=24, clinic_tz_name='UTC')
    assert due == []


def test_clinic_timezone_shifts_the_window(db):
    # Clinic in Asia/Dubai (UTC+4): an appointment at 12:00 Dubai-local time is
    # 08:00 UTC -- 2 hours before NOW_UTC (10:00 UTC), so it's already past,
    # not due, even though the raw string '12:00' looks 2h in the future.
    pid = _patient(db)
    _appt(db, pid, '2026-08-01 12:00:00')
    due = reminder_dispatch.find_due_appointments(
        db, NOW_UTC, lead_hours=24, clinic_tz_name='Asia/Dubai'
    )
    assert due == []


def test_already_sent_true_after_log_reminder(db):
    pid = _patient(db)
    aid = _appt(db, pid, '2026-08-01 12:00:00')
    assert reminder_dispatch.already_sent(db, aid, 'email') is False
    reminder_dispatch.log_reminder(db, aid, 'email', 'sent')
    db.commit()
    assert reminder_dispatch.already_sent(db, aid, 'email') is True
    # A different channel is independently tracked.
    assert reminder_dispatch.already_sent(db, aid, 'sms') is False


def test_already_sent_false_after_only_a_failed_attempt(db):
    pid = _patient(db)
    aid = _appt(db, pid, '2026-08-01 12:00:00')
    reminder_dispatch.log_reminder(db, aid, 'email', 'failed', error_detail='SMTP auth error')
    db.commit()
    assert reminder_dispatch.already_sent(db, aid, 'email') is False


def test_render_template_substitutes_placeholders():
    when = datetime(2026, 8, 1, 14, 30)
    msg = reminder_dispatch.render_template(
        'Hi {patient_name}, your appointment is on {date} at {time}.', 'Sam Lee', when
    )
    assert msg == 'Hi Sam Lee, your appointment is on 2026-08-01 at 14:30.'


def test_render_template_tolerates_missing_placeholder():
    # Template with a typo'd/unknown placeholder must not crash the loop.
    msg = reminder_dispatch.render_template('Hi {patient_name}, see you {oops}!', 'Sam', datetime(2026, 8, 1, 9, 0))
    assert msg == 'Hi Sam, see you {oops}!'
