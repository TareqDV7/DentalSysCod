"""Pure logic for the appointment-reminder dispatch loop: which
appointments are due, idempotency (has a reminder already been sent for
this appointment+channel), and message-template rendering. No Flask, no
threading, no network I/O — cursor-level functions only (mirrors
inventory.py/patient_dedupe.py/permissions.py)."""
import string
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def find_due_appointments(cursor, now_utc: datetime, lead_hours: float, clinic_tz_name: str) -> list[dict]:
    """Appointments whose (clinic-local) appointment_date, converted to an
    absolute instant, falls within [now_utc, now_utc + lead_hours]. Only
    'scheduled' appointments are considered (cancelled/completed are not)."""
    tz = ZoneInfo(clinic_tz_name or 'UTC')
    window_end = now_utc + timedelta(hours=lead_hours)

    rows = cursor.execute('''
        SELECT a.id, a.patient_id, a.appointment_date, a.treatment_type,
               p.first_name, p.last_name, p.phone, p.email
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        WHERE a.status = 'scheduled'
    ''').fetchall()

    due = []
    for row in rows:
        naive_local = datetime.strptime(row['appointment_date'], '%Y-%m-%d %H:%M:%S')
        instant = naive_local.replace(tzinfo=tz).astimezone(timezone.utc)
        if now_utc <= instant <= window_end:
            due.append({
                'id': row['id'],
                'patient_id': row['patient_id'],
                'patient_name': f"{row['first_name']} {row['last_name']}".strip(),
                'patient_phone': row['phone'],
                'patient_email': row['email'],
                'appointment_date': naive_local,
                'treatment_type': row['treatment_type'],
            })
    return due


def already_sent(cursor, appointment_id: int, channel: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM reminders_log WHERE appointment_id = ? AND channel = ? AND status = 'sent'",
        (appointment_id, channel),
    ).fetchone()
    return row is not None


def log_reminder(cursor, appointment_id: int, channel: str, status: str, error_detail: str | None = None) -> None:
    cursor.execute(
        "INSERT INTO reminders_log (appointment_id, channel, status, error_detail) VALUES (?, ?, ?, ?)",
        (appointment_id, channel, status, error_detail),
    )


class _SafeDict(dict):
    """Leaves an unknown `{placeholder}` in a clinic-edited template
    untouched instead of raising — a typo'd placeholder must not crash
    the dispatch loop or drop the whole reminder message."""
    def __missing__(self, key):
        return '{' + key + '}'


def render_template(template: str, patient_name: str, appointment_date: datetime) -> str:
    values = _SafeDict(
        patient_name=patient_name,
        date=appointment_date.strftime('%Y-%m-%d'),
        time=appointment_date.strftime('%H:%M'),
    )
    return string.Formatter().vformat(template, (), values)
