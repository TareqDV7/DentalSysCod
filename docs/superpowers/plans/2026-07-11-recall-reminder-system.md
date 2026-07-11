# Appointment Recall/Reminder System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send an SMS and/or email reminder ahead of a patient's scheduled appointment, dispatched from the always-on cloud node so it works even when the clinic's desktop app is closed.

**Architecture:** Two new pure-logic modules (`reminder_dispatch.py` for due-query/idempotency/templating, `reminder_channels.py` for the email/SMS senders, `reminder_crypto.py` for credential-field encryption) plumbed into `dental_clinic.py` via a new `reminder_dispatch_loop()` background thread (mirrors the existing `_backup_loop` pattern, started only under `CLINIC_CLOUD_MODE=1`) and a new `/api/reminders/settings` endpoint (mirrors the existing `/api/branding` GET/PUT pattern). Settings are stored as `app_settings` key/value rows — the same mechanism branding and license settings already use, no new settings table. A new `reminders_log` table gives idempotency and a staff-visible history.

**Tech Stack:** Flask, SQLite, stdlib `smtplib`/`urllib.request` (no new HTTP library), `cryptography` (already a dependency, `Fernet` for the two credential fields), stdlib `zoneinfo` for clinic-local appointment-time math (needs the `tzdata` package added — see Global Constraints).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-11-recall-reminder-system-design.md`, all Decisions.
- **New requirement discovered during planning, not in the spec:** `appointment_date` is stored as naive **clinic-local** wall-clock time (confirmed at `dental_clinic.py:3772` — it's written straight from the client's submitted string, no UTC conversion anywhere in the codebase). The cloud node's own clock is UTC (`_naive_utc_now()`, `dental_clinic.py:668`). Comparing them directly would be wrong by the clinic's UTC offset. Fix: a new `clinic_timezone` app_setting (IANA name, e.g. `"Asia/Dubai"`, default `"UTC"` if unset — never guess a clinic's timezone) used only by the dispatch loop to convert `appointment_date` to an absolute instant before comparing against `lead_hours`. This needs the `tzdata` PyPI package added to `requirements.txt` (Python's `zoneinfo` has no bundled IANA database on some minimal Linux base images — cheap, pure-data package, cloud-side only).
- Reuses the existing `settings.manage` permission key (no new permission key) for `/api/reminders/settings` PUT — matches how `/api/branding` PUT and `/api/clinic-settings` POST are already gated (`dental_clinic.py:2314-2315`).
- Reuses `read_app_setting`/`write_app_setting` (`dental_clinic.py:682-696`) for all reminder settings — no new settings table.
- The background thread must use a **plain `sqlite3.connect(_clinic_db_path(clinic_id))`**, never the request-bound `_set_request_db_path`/`get_db_connection()` proxy (`dental_clinic.py:269, 612-651`) — that proxy is per-Flask-request state and unsafe to share with a persistent background thread running concurrently with real requests. Cloud-side DBs are plaintext (documented, PR #23) so a plain connection is correct, not a workaround.
- No demo-key/silent fallback for the Fernet encryption key — mirrors the existing `serial_generator.py` / `encryption_key.py` convention in this codebase of failing loudly rather than falling back to a guessable default.
- Full existing test suite (897 tests as of 2026-07-11, see memory `project_security_hardening_2`) must stay green throughout.

---

### Task 1: `reminders_log` table + `clinic_timezone` default constant

**Files:**
- Modify: `dental_clinic.py` — add `CREATE TABLE IF NOT EXISTS reminders_log` inside `init_database()`, immediately after the `appointments` table (currently ends at line 872, right before the blank line and `visits` table at line 874-875).
- Test: `tests/test_reminders_schema.py` (new)

**Interfaces:**
- Produces: `reminders_log` table (columns: `id`, `appointment_id`, `channel`, `status`, `error_detail`, `sent_at`).
- Consumed by: Task 3 (`reminder_dispatch.py`'s idempotency/log functions).

- [ ] **Step 1: Write the failing test**

Create `tests/test_reminders_schema.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminders_schema.py -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: reminders_log`

- [ ] **Step 3: Add the table to `init_database()`**

In `dental_clinic.py`, immediately after the `appointments` table's closing `''')` (line 872), insert:

```python

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            error_detail TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        )
    ''')
```

Also add a module-level default near `_naive_utc_now()` (after line 671):

```python
DEFAULT_CLINIC_TIMEZONE = 'UTC'  # used only if the clinic hasn't set clinic_timezone yet
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reminders_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_reminders_schema.py
git commit -m "feat(reminders): add reminders_log table"
```

---

### Task 2: `reminder_crypto.py` — credential-field encryption

**Files:**
- Create: `reminder_crypto.py`
- Test: `tests/test_reminder_crypto.py` (new)

**Interfaces:**
- Produces: `reminder_crypto.encrypt(plaintext: str) -> str`, `reminder_crypto.decrypt(ciphertext: str) -> str`, both reading the key from `CLINIC_CLOUD_REMINDER_KEY` env var at call time (no caching — mirrors `encryption_key.get_or_create_key`'s "read fresh" style, and lets tests monkeypatch the env var per-test without import-order issues). Raises `RuntimeError` if the env var is unset or not a valid Fernet key.
- Consumed by: Task 5 (settings endpoint, encrypting on write) and Task 6 (dispatch loop, decrypting on read).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminder_crypto.py`:

```python
"""Encrypt/decrypt for the two credential fields (SMTP password, SMS API
key) that would otherwise sit as plaintext columns on the cloud node's
unencrypted per-clinic databases (see design spec Decision 4)."""
import pytest
from cryptography.fernet import Fernet

import reminder_crypto


@pytest.fixture()
def key(monkeypatch):
    k = Fernet.generate_key().decode()
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', k)
    return k


def test_encrypt_then_decrypt_roundtrips(key):
    ciphertext = reminder_crypto.encrypt('hunter2')
    assert ciphertext != 'hunter2'
    assert reminder_crypto.decrypt(ciphertext) == 'hunter2'


def test_encrypt_raises_without_key(monkeypatch):
    monkeypatch.delenv('CLINIC_CLOUD_REMINDER_KEY', raising=False)
    with pytest.raises(RuntimeError):
        reminder_crypto.encrypt('hunter2')


def test_decrypt_raises_with_wrong_key(key):
    ciphertext = reminder_crypto.encrypt('hunter2')
    import os
    os.environ['CLINIC_CLOUD_REMINDER_KEY'] = Fernet.generate_key().decode()
    with pytest.raises(RuntimeError):
        reminder_crypto.decrypt(ciphertext)


def test_encrypt_raises_on_malformed_key(monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', 'not-a-valid-fernet-key')
    with pytest.raises(RuntimeError):
        reminder_crypto.encrypt('hunter2')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminder_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reminder_crypto'`

- [ ] **Step 3: Write the implementation**

Create `reminder_crypto.py`:

```python
"""Application-layer encryption for the two reminder credential fields
(SMTP password, SMS API key). Cloud-side databases are plaintext by
explicit prior scope decision (encryption-at-rest PR #23 covered the
desktop DB only) — these two fields are live third-party account
credentials, not clinic patient data, so they get their own narrow
encryption rather than reopening that scope decision.

No demo-key fallback: a missing or malformed CLINIC_CLOUD_REMINDER_KEY
fails loudly, matching this codebase's existing convention (serial_generator.py,
encryption_key.py) of never silently falling back to a guessable default.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    raw = os.environ.get('CLINIC_CLOUD_REMINDER_KEY', '').strip()
    if not raw:
        raise RuntimeError(
            'CLINIC_CLOUD_REMINDER_KEY is not set. Generate one with '
            '`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` '
            'and set it as an env var on the cloud node.'
        )
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'CLINIC_CLOUD_REMINDER_KEY is not a valid Fernet key: {exc}') from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise RuntimeError('Could not decrypt reminder credential — wrong key or corrupted value') from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reminder_crypto.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add reminder_crypto.py tests/test_reminder_crypto.py
git commit -m "feat(reminders): add credential-field encryption helper"
```

---

### Task 3: `reminder_dispatch.py` — due-query, idempotency, templating

**Files:**
- Create: `reminder_dispatch.py`
- Test: `tests/test_reminder_dispatch.py` (new)

**Interfaces:**
- Produces:
  - `find_due_appointments(cursor, now_utc: datetime, lead_hours: float, clinic_tz_name: str) -> list[dict]` — each dict has `id`, `patient_id`, `patient_name`, `patient_phone`, `patient_email`, `appointment_date`, `treatment_type`.
  - `already_sent(cursor, appointment_id: int, channel: str) -> bool`
  - `log_reminder(cursor, appointment_id: int, channel: str, status: str, error_detail: str | None = None) -> None`
  - `render_template(template: str, patient_name: str, appointment_date: datetime) -> str` — substitutes `{patient_name}`, `{date}` (`%Y-%m-%d`), `{time}` (`%H:%M`).
- Consumed by: Task 6 (`reminder_dispatch_loop()`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminder_dispatch.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminder_dispatch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reminder_dispatch'`

- [ ] **Step 3: Write the implementation**

Create `reminder_dispatch.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reminder_dispatch.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add reminder_dispatch.py tests/test_reminder_dispatch.py
git commit -m "feat(reminders): add due-query, idempotency, and template rendering"
```

---

### Task 4: `reminder_channels.py` — email + SMS senders

**Files:**
- Create: `reminder_channels.py`
- Test: `tests/test_reminder_channels.py` (new)

**Interfaces:**
- Produces: `ReminderSendError(Exception)`, `send_email(to: str, subject: str, body: str, smtp_cfg: dict) -> None`, `send_sms(to: str, body: str, sms_cfg: dict) -> None`. `smtp_cfg` keys: `host, port, user, password`. `sms_cfg` keys: `provider, api_key, api_secret, from_number` (Twilio: `api_key`=Account SID, `api_secret`=Auth Token).
- Consumed by: Task 6 (`reminder_dispatch_loop()`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminder_channels.py`:

```python
"""Email (stdlib smtplib) and SMS (Twilio REST, stdlib urllib) senders.
No real network calls — smtplib.SMTP and urllib.request.urlopen are mocked."""
import smtplib
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import reminder_channels


SMTP_CFG = {'host': 'smtp.example.com', 'port': 587, 'user': 'clinic@example.com', 'password': 'secret'}
SMS_CFG = {'provider': 'twilio', 'api_key': 'ACxxxx', 'api_secret': 'authtoken', 'from_number': '+15551234567'}


def test_send_email_success():
    mock_smtp = MagicMock()
    with patch('smtplib.SMTP', return_value=mock_smtp) as ctor:
        mock_smtp.__enter__.return_value = mock_smtp
        reminder_channels.send_email('patient@example.com', 'Reminder', 'See you soon', SMTP_CFG)
    ctor.assert_called_once_with('smtp.example.com', 587, timeout=15)
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with('clinic@example.com', 'secret')
    mock_smtp.send_message.assert_called_once()


def test_send_email_raises_reminder_send_error_on_smtp_failure():
    with patch('smtplib.SMTP', side_effect=smtplib.SMTPException('auth failed')):
        with pytest.raises(reminder_channels.ReminderSendError):
            reminder_channels.send_email('patient@example.com', 'Reminder', 'body', SMTP_CFG)


def test_send_sms_success():
    fake_resp = MagicMock()
    fake_resp.status = 201
    fake_resp.read.return_value = b'{"sid": "SMxxxx"}'
    fake_resp.__enter__.return_value = fake_resp
    with patch('urllib.request.urlopen', return_value=fake_resp) as urlopen:
        reminder_channels.send_sms('+15559876543', 'See you soon', SMS_CFG)
    assert urlopen.called
    req = urlopen.call_args[0][0]
    assert 'ACxxxx' in req.full_url


def test_send_sms_raises_reminder_send_error_on_http_error():
    err = urllib.error.HTTPError('url', 401, 'Unauthorized', {}, None)
    with patch('urllib.request.urlopen', side_effect=err):
        with pytest.raises(reminder_channels.ReminderSendError):
            reminder_channels.send_sms('+15559876543', 'body', SMS_CFG)


def test_send_sms_raises_on_unknown_provider():
    with pytest.raises(reminder_channels.ReminderSendError):
        reminder_channels.send_sms('+15559876543', 'body', {**SMS_CFG, 'provider': 'unknown_co'})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminder_channels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reminder_channels'`

- [ ] **Step 3: Write the implementation**

Create `reminder_channels.py`:

```python
"""Email and SMS senders for appointment reminders. stdlib only
(smtplib + urllib.request) — no new third-party HTTP/SMS SDK dependency,
matching this codebase's existing stdlib-first convention for outbound
HTTP (see dental_clinic.py's _cloud_http_request)."""
import base64
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage


class ReminderSendError(Exception):
    """Raised on any failure to deliver a reminder — the dispatch loop
    catches this, logs a 'failed' row, and moves on to the next reminder."""


def send_email(to: str, subject: str, body: str, smtp_cfg: dict) -> None:
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = smtp_cfg['user']
    msg['To'] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(smtp_cfg['host'], smtp_cfg['port'], timeout=15) as server:
            server.starttls()
            server.login(smtp_cfg['user'], smtp_cfg['password'])
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise ReminderSendError(f'email send failed: {exc}') from exc


def _send_sms_twilio(to: str, body: str, sms_cfg: dict) -> None:
    account_sid = sms_cfg['api_key']
    auth_token = sms_cfg['api_secret']
    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    payload = urllib.parse.urlencode({
        'To': to,
        'From': sms_cfg['from_number'],
        'Body': body,
    }).encode('utf-8')
    basic_auth = base64.b64encode(f'{account_sid}:{auth_token}'.encode('utf-8')).decode('ascii')
    req = urllib.request.Request(
        url, data=payload,
        headers={
            'Authorization': f'Basic {basic_auth}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 300:
                raise ReminderSendError(f'Twilio returned status {resp.status}')
    except urllib.error.HTTPError as exc:
        raise ReminderSendError(f'Twilio HTTP error {exc.code}: {exc.reason}') from exc
    except urllib.error.URLError as exc:
        raise ReminderSendError(f'Twilio connection failed: {exc.reason}') from exc


_SMS_PROVIDERS = {
    'twilio': _send_sms_twilio,
}


def send_sms(to: str, body: str, sms_cfg: dict) -> None:
    provider = sms_cfg.get('provider')
    sender = _SMS_PROVIDERS.get(provider)
    if sender is None:
        raise ReminderSendError(f'unknown SMS provider: {provider!r}')
    sender(to, body, sms_cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reminder_channels.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add reminder_channels.py tests/test_reminder_channels.py
git commit -m "feat(reminders): add email and SMS (Twilio) senders"
```

---

### Task 5: `/api/reminders/settings` GET/PUT endpoint

**Files:**
- Modify: `dental_clinic.py`:
  - Add route after the `branding()` function (after line 5420, before the `_MAX_POST_PHOTOS` block).
  - Add `'/api/reminders/settings'` to `_AUTH_REQUIRED_EXACT` (line 2199).
  - Add a permission rule to `_PERMISSION_RULES` (after the `/api/branding` line, 2314): `(frozenset({'PUT'}), r'^/api/reminders/settings$', 'settings.manage'),`
- Test: `tests/test_reminder_settings_api.py` (new)

**Interfaces:**
- Consumes: `reminder_crypto.encrypt`/`decrypt` (Task 2).
- Produces: `GET/PUT /api/reminders/settings` — same shape as `/api/branding` (`dental_clinic.py:5395-5420`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminder_settings_api.py`:

```python
"""GET/PUT /api/reminders/settings — mirrors the existing /api/branding
endpoint's shape and auth posture. SMTP password / SMS API key are
encrypted before being written and never echoed back in plaintext on GET."""
import os

import pytest
from cryptography.fernet import Fernet

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', Fernet.generate_key().decode())
    test_db = tmp_path / 'reminder_settings_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        with c.session_transaction() as sess:
            sess['uid'] = 1
            sess['username'] = 'admin'
        yield c


def test_get_returns_defaults_on_fresh_db(client):
    resp = client.get('/api/reminders/settings')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is False
    assert data['lead_hours'] == 24
    assert data['smtp_password_set'] is False
    assert data['sms_api_key_set'] is False
    assert 'smtp_password' not in data
    assert 'sms_api_key' not in data


def test_put_then_get_roundtrips_non_secret_fields(client):
    resp = client.put('/api/reminders/settings', json={
        'enabled': True,
        'lead_hours': 12,
        'message_template': 'Hi {patient_name}, see you {date} {time}.',
        'clinic_timezone': 'Asia/Dubai',
        'smtp_host': 'smtp.example.com',
        'smtp_port': 587,
        'smtp_user': 'clinic@example.com',
        'smtp_password': 'hunter2',
        'sms_provider': 'twilio',
        'sms_api_key': 'ACxxxx',
        'sms_api_secret': 'authtoken',
        'sms_from_number': '+15551234567',
    })
    assert resp.status_code == 200

    data = client.get('/api/reminders/settings').get_json()
    assert data['enabled'] is True
    assert data['lead_hours'] == 12
    assert data['smtp_host'] == 'smtp.example.com'
    assert data['smtp_password_set'] is True
    assert data['sms_api_key_set'] is True
    assert data['sms_api_secret_set'] is True
    assert 'smtp_password' not in data
    assert 'sms_api_key' not in data
    assert 'sms_api_secret' not in data


def test_put_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_CLOUD_REMINDER_KEY', Fernet.generate_key().decode())
    test_db = tmp_path / 'reminder_settings_nologin.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        resp = c.put('/api/reminders/settings', json={'enabled': True})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminder_settings_api.py -v`
Expected: FAIL — `404 NOT FOUND` (route doesn't exist yet)

- [ ] **Step 3: Add the route**

In `dental_clinic.py`, immediately after the `branding()` function's closing `return jsonify({'success': True})` (line 5420), insert:

```python


@app.route('/api/reminders/settings', methods=['GET', 'PUT'])
def reminder_settings():
    import reminder_crypto
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'GET':
        smtp_password_enc = read_app_setting(cursor, 'reminder_smtp_password_enc', '')
        sms_api_key_enc = read_app_setting(cursor, 'reminder_sms_api_key_enc', '')
        sms_api_secret_enc = read_app_setting(cursor, 'reminder_sms_api_secret_enc', '')
        out = {
            'enabled': read_app_setting(cursor, 'reminders_enabled', '0') == '1',
            'lead_hours': int(read_app_setting(cursor, 'reminder_lead_hours', '24')),
            'message_template': read_app_setting(
                cursor, 'reminder_message_template',
                'Hi {patient_name}, this is a reminder of your appointment on {date} at {time}.'
            ),
            'clinic_timezone': read_app_setting(cursor, 'clinic_timezone', DEFAULT_CLINIC_TIMEZONE),
            'smtp_host': read_app_setting(cursor, 'reminder_smtp_host', ''),
            'smtp_port': int(read_app_setting(cursor, 'reminder_smtp_port', '587')),
            'smtp_user': read_app_setting(cursor, 'reminder_smtp_user', ''),
            'smtp_password_set': bool(smtp_password_enc),
            'sms_provider': read_app_setting(cursor, 'reminder_sms_provider', 'twilio'),
            'sms_from_number': read_app_setting(cursor, 'reminder_sms_from_number', ''),
            'sms_api_key_set': bool(sms_api_key_enc),
            'sms_api_secret_set': bool(sms_api_secret_enc),
        }
        conn.close()
        return jsonify(out)

    data = request.get_json(silent=True) or {}
    plain_fields = (
        ('enabled', 'reminders_enabled', lambda v: '1' if v else '0'),
        ('lead_hours', 'reminder_lead_hours', str),
        ('message_template', 'reminder_message_template', str),
        ('clinic_timezone', 'clinic_timezone', str),
        ('smtp_host', 'reminder_smtp_host', str),
        ('smtp_port', 'reminder_smtp_port', str),
        ('smtp_user', 'reminder_smtp_user', str),
        ('sms_provider', 'reminder_sms_provider', str),
        ('sms_from_number', 'reminder_sms_from_number', str),
    )
    for key, setting_key, coerce in plain_fields:
        if key in data and data[key] is not None:
            write_app_setting(cursor, setting_key, coerce(data[key]))

    if data.get('smtp_password'):
        write_app_setting(cursor, 'reminder_smtp_password_enc', reminder_crypto.encrypt(str(data['smtp_password'])))
    if data.get('sms_api_key'):
        write_app_setting(cursor, 'reminder_sms_api_key_enc', reminder_crypto.encrypt(str(data['sms_api_key'])))
    if data.get('sms_api_secret'):
        write_app_setting(cursor, 'reminder_sms_api_secret_enc', reminder_crypto.encrypt(str(data['sms_api_secret'])))

    conn.commit()
    conn.close()
    return jsonify({'success': True})
```

Then:
- In `_AUTH_REQUIRED_EXACT` (line 2199), change `'/api/branding', '/api/posts'}` to `'/api/branding', '/api/posts', '/api/reminders/settings'}`.
- In `_PERMISSION_RULES` (after line 2314's `/api/branding` entry), insert:
  ```python
      (frozenset({'PUT'}), r'^/api/reminders/settings$', 'settings.manage'),
  ```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reminder_settings_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_reminder_settings_api.py
git commit -m "feat(reminders): add /api/reminders/settings endpoint"
```

---

### Task 6: `reminder_dispatch_loop()` background thread

**Files:**
- Modify: `dental_clinic.py`:
  - Add `reminder_dispatch_loop()` function after `_backup_loop()` (after line 7934).
  - Add `REMINDER_INTERVAL_MINUTES` env-driven constant next to `CLOUD_SYNC_INTERVAL_MINUTES` (after line 7941).
  - Add the thread-start block in the startup section, next to the other `CLOUD_MODE`-aware threads (after the `bt_sync_on` block, before `print("\n✅ System ready!")`, i.e. after the code shown at the end of the earlier read — insert right before the final `print` block).
- Test: `tests/test_reminder_dispatch_loop.py` (new)

**Interfaces:**
- Consumes: `reminder_dispatch.find_due_appointments/already_sent/log_reminder/render_template` (Task 3), `reminder_channels.send_email/send_sms/ReminderSendError` (Task 4), `reminder_crypto.decrypt` (Task 2), `_clinic_db_path` (`dental_clinic.py:269`), `MASTER_DB_PATH` (`dental_clinic.py:240`).
- Produces: `_reminder_dispatch_one_clinic(clinic_db_path: str, now_utc: datetime) -> None` (the per-clinic unit, directly testable without threading) and `reminder_dispatch_loop()` (the `while True` wrapper, not directly tested — mirrors `_backup_loop`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminder_dispatch_loop.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminder_dispatch_loop.py -v`
Expected: FAIL — `AttributeError: module 'dental_clinic' has no attribute '_reminder_dispatch_one_clinic'`

- [ ] **Step 3: Write the implementation**

In `dental_clinic.py`, immediately after `_backup_loop()` (after line 7934), insert:

```python


def _reminder_dispatch_one_clinic(clinic_db_path, now_utc):
    """One clinic's worth of reminder dispatch. Uses a plain sqlite3
    connection (never the request-bound get_db_connection() proxy — this
    runs from a background thread, not inside a Flask request). Cloud-side
    per-clinic DBs are plaintext (documented, PR #23), so a plain
    connection is correct here, not a workaround."""
    import reminder_channels
    import reminder_crypto
    import reminder_dispatch

    conn = sqlite3.connect(clinic_db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        if read_app_setting(cur, 'reminders_enabled', '0') != '1':
            return

        lead_hours = float(read_app_setting(cur, 'reminder_lead_hours', '24'))
        clinic_tz = read_app_setting(cur, 'clinic_timezone', DEFAULT_CLINIC_TIMEZONE)
        template = read_app_setting(
            cur, 'reminder_message_template',
            'Hi {patient_name}, this is a reminder of your appointment on {date} at {time}.'
        )

        smtp_password_enc = read_app_setting(cur, 'reminder_smtp_password_enc', '')
        smtp_cfg = None
        if smtp_password_enc and read_app_setting(cur, 'reminder_smtp_host', ''):
            smtp_cfg = {
                'host': read_app_setting(cur, 'reminder_smtp_host', ''),
                'port': int(read_app_setting(cur, 'reminder_smtp_port', '587')),
                'user': read_app_setting(cur, 'reminder_smtp_user', ''),
                'password': reminder_crypto.decrypt(smtp_password_enc),
            }

        sms_api_key_enc = read_app_setting(cur, 'reminder_sms_api_key_enc', '')
        sms_api_secret_enc = read_app_setting(cur, 'reminder_sms_api_secret_enc', '')
        sms_cfg = None
        # Require key + secret + from_number all present. A missing secret
        # must never fall back to re-using the API key as the secret (that
        # would silently send Twilio a wrong credential pair instead of
        # just not sending SMS) -- treat "secret not set yet" as "SMS not
        # configured", same as a missing key or from_number.
        if sms_api_key_enc and sms_api_secret_enc and read_app_setting(cur, 'reminder_sms_from_number', ''):
            sms_cfg = {
                'provider': read_app_setting(cur, 'reminder_sms_provider', 'twilio'),
                'api_key': reminder_crypto.decrypt(sms_api_key_enc),
                'api_secret': reminder_crypto.decrypt(sms_api_secret_enc),
                'from_number': read_app_setting(cur, 'reminder_sms_from_number', ''),
            }

        if smtp_cfg is None and sms_cfg is None:
            return

        due = reminder_dispatch.find_due_appointments(cur, now_utc, lead_hours, clinic_tz)
        for appt in due:
            message = reminder_dispatch.render_template(template, appt['patient_name'], appt['appointment_date'])

            if smtp_cfg and appt['patient_email'] and not reminder_dispatch.already_sent(cur, appt['id'], 'email'):
                try:
                    reminder_channels.send_email(appt['patient_email'], 'Appointment reminder', message, smtp_cfg)
                    reminder_dispatch.log_reminder(cur, appt['id'], 'email', 'sent')
                except reminder_channels.ReminderSendError as exc:
                    reminder_dispatch.log_reminder(cur, appt['id'], 'email', 'failed', str(exc))

            if sms_cfg and appt['patient_phone'] and not reminder_dispatch.already_sent(cur, appt['id'], 'sms'):
                try:
                    reminder_channels.send_sms(appt['patient_phone'], message, sms_cfg)
                    reminder_dispatch.log_reminder(cur, appt['id'], 'sms', 'sent')
                except reminder_channels.ReminderSendError as exc:
                    reminder_dispatch.log_reminder(cur, appt['id'], 'sms', 'failed', str(exc))

        conn.commit()
    finally:
        conn.close()


def reminder_dispatch_loop():
    """Background worker (cloud node only): every REMINDER_INTERVAL_MINUTES,
    dispatch due reminders for every active clinic. Mirrors _backup_loop's
    shape. A single clinic's failure (locked DB, bad creds) is caught and
    logged so it never stops the others in the same cycle."""
    import time

    time.sleep(8)
    while True:
        try:
            master = sqlite3.connect(MASTER_DB_PATH)
            clinic_ids = [row[0] for row in master.execute('SELECT id FROM clinics WHERE active = 1')]
            master.close()
        except sqlite3.Error as exc:
            print(f'⚠️ reminder loop: could not read clinics list: {exc}')
            clinic_ids = []

        now_utc = datetime.now(timezone.utc)
        for clinic_id in clinic_ids:
            try:
                _reminder_dispatch_one_clinic(_clinic_db_path(clinic_id), now_utc)
            except Exception as exc:  # noqa: BLE001 - one clinic's failure must not stop the others
                print(f'⚠️ reminder loop: clinic {clinic_id} failed: {exc}')

        time.sleep(max(1.0, REMINDER_INTERVAL_MINUTES) * 60)
```

Next to `CLOUD_SYNC_INTERVAL_MINUTES` (after line 7941), insert:

```python

try:
    REMINDER_INTERVAL_MINUTES = max(1.0, float(os.environ.get('CLINIC_REMINDER_INTERVAL_MINUTES', '10')))
except ValueError:
    REMINDER_INTERVAL_MINUTES = 10.0
```

In the startup thread-wiring block (the code shown ending with the `bt_sync_on` / `bt_sync_server` thread start, right before `print("\n✅ System ready!")`), insert:

```python

    # Reminder dispatch — cloud node only (see design spec Decision 2): the
    # desktop process never runs this, only the multi-tenant cloud process
    # (CLINIC_CLOUD_MODE=1) does, since it's the only always-on component.
    if CLOUD_MODE:
        threading.Thread(target=reminder_dispatch_loop, daemon=True).start()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reminder_dispatch_loop.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_reminder_dispatch_loop.py
git commit -m "feat(reminders): add cloud-node reminder dispatch loop"
```

---

### Task 7: Settings UI panel (Reminders)

**Files:**
- Modify: `templates.py`:
  - HTML: add a "Reminders" panel after the closing `</div>` of `branding-card` (after line 3158), before the `License` section (line 3160).
  - JS: add `loadReminderSettings()`/`reminderSettingsSave()` after `brandingSave()` (after line 3161 in JS terms — actually after line 6861), and call `loadReminderSettings()` from `loadSupportSection()` (line 6820-6827, add alongside `loadBranding()`).
  - i18n: add EN keys after `ps_branding_saved` (line 4104) and AR keys after the AR equivalent (line 4637).
- Test: `tests/test_reminder_settings_ui.py` (new)

**Interfaces:**
- Consumes: `GET/PUT /api/reminders/settings` (Task 5).

- [ ] **Step 1: Write the failing test**

Create `tests/test_reminder_settings_ui.py`:

```python
"""The Reminders settings panel exists in the Settings tab HTML and its
JS functions are wired up (loaded on Settings tab open, saved via button).
Mirrors tests/test_post_studio_ui.py's presence-check style — no browser,
just string checks against the served HTML/JS."""
from templates import HTML_TEMPLATE


def test_reminders_panel_markup_present():
    assert 'id="reminders-card"' in HTML_TEMPLATE
    assert 'id="reminder-lead-hours"' in HTML_TEMPLATE
    assert 'onclick="reminderSettingsSave()"' in HTML_TEMPLATE


def test_reminders_js_functions_present():
    assert 'async function loadReminderSettings()' in HTML_TEMPLATE
    assert 'async function reminderSettingsSave()' in HTML_TEMPLATE
    assert 'loadReminderSettings();' in HTML_TEMPLATE  # wired into loadSupportSection
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reminder_settings_ui.py -v`
Expected: FAIL — assertion errors (markup not present yet)

- [ ] **Step 3: Add the HTML panel**

In `templates.py`, immediately after the `branding-card` div's closing `</div>` (after line 3158), insert:

```html

                <h3 class="settings-group" data-en="Appointment Reminders" data-ar="تذكيرات المواعيد">Appointment Reminders</h3>
                <div class="section-card" id="reminders-card" style="max-width:560px;margin-bottom:18px;">
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="reminders-enabled">
                            <span data-i18n="reminders_enabled_label">Send appointment reminders</span>
                        </label>
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_lead_hours">Hours before appointment</label>
                        <input type="number" id="reminder-lead-hours" min="1" max="168" value="24">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_timezone">Clinic timezone (IANA name)</label>
                        <input type="text" id="reminder-clinic-timezone" placeholder="Asia/Dubai">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_template">Message template</label>
                        <textarea id="reminder-message-template" rows="2" placeholder="Hi {patient_name}, this is a reminder of your appointment on {date} at {time}."></textarea>
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_smtp_host">SMTP host</label>
                        <input type="text" id="reminder-smtp-host" autocomplete="off" placeholder="smtp.example.com">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_smtp_port">SMTP port</label>
                        <input type="number" id="reminder-smtp-port" value="587">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_smtp_user">SMTP username</label>
                        <input type="text" id="reminder-smtp-user" autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_smtp_password">SMTP password <span id="reminder-smtp-password-status" class="muted"></span></label>
                        <input type="password" id="reminder-smtp-password" autocomplete="off" placeholder="•••••••• (leave blank to keep)">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_sms_provider">SMS provider</label>
                        <select id="reminder-sms-provider">
                            <option value="twilio">Twilio</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_sms_from">SMS sender number</label>
                        <input type="text" id="reminder-sms-from-number" autocomplete="off" placeholder="+15551234567">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_sms_key">SMS API key <span id="reminder-sms-key-status" class="muted"></span></label>
                        <input type="password" id="reminder-sms-api-key" autocomplete="off" placeholder="•••••••• (leave blank to keep)">
                    </div>
                    <div class="form-group">
                        <label data-i18n="reminders_sms_secret">SMS API secret</label>
                        <input type="password" id="reminder-sms-api-secret" autocomplete="off" placeholder="•••••••• (leave blank to keep)">
                    </div>
                    <button class="btn btn-primary" type="button" onclick="reminderSettingsSave()" data-i18n="reminders_save">Save reminder settings</button>
                </div>
```

- [ ] **Step 4: Add the JS**

In `templates.py`, immediately after `brandingSave()`'s closing `}` (after line 6861), insert:

```javascript

        async function loadReminderSettings() {
            try {
                const data = await fetch('/api/reminders/settings').then(function(r) { return r.json(); });
                const set = function(id, val) { const el = document.getElementById(id); if (el) el.value = val; };
                const enabledEl = document.getElementById('reminders-enabled');
                if (enabledEl) enabledEl.checked = !!data.enabled;
                set('reminder-lead-hours', data.lead_hours);
                set('reminder-clinic-timezone', data.clinic_timezone || '');
                set('reminder-message-template', data.message_template || '');
                set('reminder-smtp-host', data.smtp_host || '');
                set('reminder-smtp-port', data.smtp_port);
                set('reminder-smtp-user', data.smtp_user || '');
                set('reminder-sms-provider', data.sms_provider || 'twilio');
                set('reminder-sms-from-number', data.sms_from_number || '');
                const smtpStatus = document.getElementById('reminder-smtp-password-status');
                if (smtpStatus) smtpStatus.textContent = data.smtp_password_set ? t('reminders_set', '(set)') : '';
                const smsStatus = document.getElementById('reminder-sms-key-status');
                if (smsStatus) smsStatus.textContent = data.sms_api_key_set ? t('reminders_set', '(set)') : '';
            } catch (_) {}
        }

        async function reminderSettingsSave() {
            const val = function(id) { const el = document.getElementById(id); return el ? el.value : ''; };
            const payload = {
                enabled: !!(document.getElementById('reminders-enabled') || {}).checked,
                lead_hours: parseInt(val('reminder-lead-hours'), 10) || 24,
                clinic_timezone: val('reminder-clinic-timezone').trim(),
                message_template: val('reminder-message-template'),
                smtp_host: val('reminder-smtp-host').trim(),
                smtp_port: parseInt(val('reminder-smtp-port'), 10) || 587,
                smtp_user: val('reminder-smtp-user').trim(),
                sms_provider: val('reminder-sms-provider'),
                sms_from_number: val('reminder-sms-from-number').trim(),
            };
            const smtpPassword = val('reminder-smtp-password');
            if (smtpPassword) payload.smtp_password = smtpPassword;
            const smsKey = val('reminder-sms-api-key');
            if (smsKey) payload.sms_api_key = smsKey;
            const smsSecret = val('reminder-sms-api-secret');
            if (smsSecret) payload.sms_api_secret = smsSecret;
            try {
                const res = await fetch('/api/reminders/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!res.ok) throw new Error(res.status);
                document.getElementById('reminder-smtp-password').value = '';
                document.getElementById('reminder-sms-api-key').value = '';
                document.getElementById('reminder-sms-api-secret').value = '';
                showToast(t('reminders_saved', 'Reminder settings saved'), 'success');
                loadReminderSettings();
            } catch (err) {
                showToast(t('reminders_save_failed', 'Could not save reminder settings: ') + err, 'error');
            }
        }
```

Then in `loadSupportSection()` (line 6820-6827), change:

```javascript
        async function loadSupportSection() {
            await loadCloudSyncSettings();
            loadBluetoothSyncSettings();
            bindBluetoothSyncControls();
            loadLicenseCard();
            loadBranding();
            loadStaffAccounts();
        }
```

to:

```javascript
        async function loadSupportSection() {
            await loadCloudSyncSettings();
            loadBluetoothSyncSettings();
            bindBluetoothSyncControls();
            loadLicenseCard();
            loadBranding();
            loadReminderSettings();
            loadStaffAccounts();
        }
```

- [ ] **Step 5: Add i18n strings**

After the EN `ps_branding_saved: 'Branding saved',` line (4104), insert:

```javascript
                reminders_enabled_label: 'Send appointment reminders',
                reminders_lead_hours: 'Hours before appointment',
                reminders_timezone: 'Clinic timezone (IANA name)',
                reminders_template: 'Message template',
                reminders_smtp_host: 'SMTP host',
                reminders_smtp_port: 'SMTP port',
                reminders_smtp_user: 'SMTP username',
                reminders_smtp_password: 'SMTP password',
                reminders_sms_provider: 'SMS provider',
                reminders_sms_from: 'SMS sender number',
                reminders_sms_key: 'SMS API key',
                reminders_sms_secret: 'SMS API secret',
                reminders_save: 'Save reminder settings',
                reminders_set: '(set)',
                reminders_saved: 'Reminder settings saved',
                reminders_save_failed: 'Could not save reminder settings: ',
```

After the AR `ps_branding_saved: 'تم حفظ العلامة التجارية',` line (4637), insert:

```javascript
                reminders_enabled_label: 'إرسال تذكيرات المواعيد',
                reminders_lead_hours: 'عدد الساعات قبل الموعد',
                reminders_timezone: 'المنطقة الزمنية للعيادة (اسم IANA)',
                reminders_template: 'نص الرسالة',
                reminders_smtp_host: 'خادم SMTP',
                reminders_smtp_port: 'منفذ SMTP',
                reminders_smtp_user: 'اسم مستخدم SMTP',
                reminders_smtp_password: 'كلمة مرور SMTP',
                reminders_sms_provider: 'مزود الرسائل النصية',
                reminders_sms_from: 'رقم مرسل الرسائل النصية',
                reminders_sms_key: 'مفتاح API للرسائل النصية',
                reminders_sms_secret: 'سر API للرسائل النصية',
                reminders_save: 'حفظ إعدادات التذكير',
                reminders_set: '(محفوظ)',
                reminders_saved: 'تم حفظ إعدادات التذكير',
                reminders_save_failed: 'تعذر حفظ إعدادات التذكير: ',
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_reminder_settings_ui.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_reminder_settings_ui.py
git commit -m "feat(reminders): add Reminders settings panel to Settings tab"
```

---

### Task 8: Full regression gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (897 pre-existing + 31 new from Tasks 1-7 = 928), zero failures/errors.

- [ ] **Step 2: Run node/e2e suites unaffected**

Run: `node --test tests/js/` (this feature touches no JS post-studio modules — expected unchanged pass count, sanity check only).

- [ ] **Step 3: Add `tzdata` to requirements.txt**

Open `requirements.txt`, add a line after `cryptography>=42.0`:

```
tzdata>=2024.1
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(reminders): add tzdata dependency for cloud-side zoneinfo"
```

- [ ] **Step 5: Update memory**

Not a code step — after this plan is fully executed, update the `project_security_hardening_2` memory file (roadmap item 2 of 5) to record the recall/reminder sub-project as DONE, and note the `CLINIC_CLOUD_REMINDER_KEY` env var as a new cloud-node deployment requirement (needs documenting in the cloud deploy runbook / `cloud/docker-compose.yml` env section — flag this as a follow-up if a deploy runbook file exists; this plan does not touch deployment config).
