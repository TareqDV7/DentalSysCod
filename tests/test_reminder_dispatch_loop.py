"""_reminder_dispatch_one_clinic: the per-clinic unit of work the
background loop calls repeatedly. Tested directly (no threading, no
sleep) — sends are mocked so no real network call happens."""
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import dental_clinic
import reminder_crypto


@pytest.fixture()
def clinic_db(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', Fernet.generate_key().decode())
    # _reminder_dispatch_one_clinic always opens its clinic DB with a plain
    # sqlite3.connect() (see Global Constraints -- cloud-side per-clinic DBs
    # are plaintext by design). init_database() itself writes through
    # get_db_connection(), which SQLCipher-encrypts unless CLOUD_MODE is on
    # -- patch CLOUD_MODE here so the fixture's DB is actually plaintext,
    # matching what the code under test expects to read (test_cloud_mode.py
    # uses this same monkeypatch.setattr pattern, not an env var, since
    # dental_clinic.CLOUD_MODE is evaluated once at import time).
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    test_db = tmp_path / 'clinic_1.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    yield conn, str(test_db)
    conn.close()


def _enable_reminders(conn, **overrides):
    cur = conn.cursor()
    settings = {
        'reminders_enabled': '1',
        'reminder_lead_hours': '24',
        'reminder_message_template': 'Hi {patient_name}, appt on {date} {time}.',
        'clinic_timezone': 'UTC',
        'reminder_smtp_host': 'smtp.example.com',
        'reminder_smtp_port': '587',
        'reminder_smtp_user': 'clinic@example.com',
        'reminder_smtp_password_enc': reminder_crypto.encrypt('secret'),
    }
    settings.update(overrides)
    for k, v in settings.items():
        dental_clinic.write_app_setting(cur, k, v)
    conn.commit()


def test_sends_email_and_logs_it(clinic_db):
    conn, path = clinic_db
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, email) VALUES ('Sam', 'Lee', 'sam@example.com')")
    pid = cur.lastrowid
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type, status) "
        "VALUES (?, '2026-08-01 11:00:00', 'Checkup', 'scheduled')", (pid,)
    )
    aid = cur.lastrowid
    conn.commit()
    _enable_reminders(conn)

    with patch('reminder_channels.send_email') as mock_send:
        dental_clinic._reminder_dispatch_one_clinic(path, datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc))

    mock_send.assert_called_once()
    sent_to = mock_send.call_args[0][0]
    assert sent_to == 'sam@example.com'
    row = conn.execute("SELECT status FROM reminders_log WHERE appointment_id = ? AND channel = 'email'", (aid,)).fetchone()
    assert row[0] == 'sent'


def test_skips_disabled_clinic_without_querying_appointments(clinic_db):
    conn, path = clinic_db
    # reminders_enabled left at default '0'.
    with patch('reminder_channels.send_email') as mock_send:
        dental_clinic._reminder_dispatch_one_clinic(path, datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc))
    mock_send.assert_not_called()


def test_does_not_resend_after_success(clinic_db):
    conn, path = clinic_db
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, email) VALUES ('Sam', 'Lee', 'sam@example.com')")
    pid = cur.lastrowid
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type, status) "
        "VALUES (?, '2026-08-01 11:00:00', 'Checkup', 'scheduled')", (pid,)
    )
    conn.commit()
    _enable_reminders(conn)
    now = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

    with patch('reminder_channels.send_email') as mock_send:
        dental_clinic._reminder_dispatch_one_clinic(path, now)
        dental_clinic._reminder_dispatch_one_clinic(path, now)

    mock_send.assert_called_once()


def test_bad_patient_email_logs_failed_and_continues(clinic_db):
    conn, path = clinic_db
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, email) VALUES ('Sam', 'Lee', 'not-an-email')")
    pid = cur.lastrowid
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type, status) "
        "VALUES (?, '2026-08-01 11:00:00', 'Checkup', 'scheduled')", (pid,)
    )
    aid = cur.lastrowid
    conn.commit()
    _enable_reminders(conn)

    import reminder_channels
    with patch('reminder_channels.send_email', side_effect=reminder_channels.ReminderSendError('bad address')):
        dental_clinic._reminder_dispatch_one_clinic(path, datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc))

    row = conn.execute("SELECT status, error_detail FROM reminders_log WHERE appointment_id = ?", (aid,)).fetchone()
    assert row[0] == 'failed'
    assert 'bad address' in row[1]


def test_sends_sms_when_configured_and_logs_it(clinic_db):
    conn, path = clinic_db
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('Sam', 'Lee', '+15559876543')")
    pid = cur.lastrowid
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type, status) "
        "VALUES (?, '2026-08-01 11:00:00', 'Checkup', 'scheduled')", (pid,)
    )
    aid = cur.lastrowid
    conn.commit()
    _enable_reminders(
        conn,
        reminder_sms_provider='twilio',
        reminder_sms_api_key_enc=reminder_crypto.encrypt('ACxxxx'),
        reminder_sms_api_secret_enc=reminder_crypto.encrypt('authtoken'),
        reminder_sms_from_number='+15551234567',
    )

    with patch('reminder_channels.send_sms') as mock_send:
        dental_clinic._reminder_dispatch_one_clinic(path, datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc))

    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == '+15559876543'
    row = conn.execute("SELECT status FROM reminders_log WHERE appointment_id = ? AND channel = 'sms'", (aid,)).fetchone()
    assert row[0] == 'sent'


def test_sms_not_sent_when_secret_missing_even_if_key_present(clinic_db):
    # Regression guard for the fix in _reminder_dispatch_one_clinic: a
    # missing api_secret must skip SMS entirely, never fall back to the
    # API key as the secret.
    conn, path = clinic_db
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('Sam', 'Lee', '+15559876543')")
    pid = cur.lastrowid
    cur.execute(
        "INSERT INTO appointments (patient_id, appointment_date, treatment_type, status) "
        "VALUES (?, '2026-08-01 11:00:00', 'Checkup', 'scheduled')", (pid,)
    )
    conn.commit()
    _enable_reminders(
        conn,
        reminder_sms_provider='twilio',
        reminder_sms_api_key_enc=reminder_crypto.encrypt('ACxxxx'),
        reminder_sms_from_number='+15551234567',
        # reminder_sms_api_secret_enc intentionally omitted
    )

    with patch('reminder_channels.send_sms') as mock_send:
        dental_clinic._reminder_dispatch_one_clinic(path, datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc))

    mock_send.assert_not_called()
