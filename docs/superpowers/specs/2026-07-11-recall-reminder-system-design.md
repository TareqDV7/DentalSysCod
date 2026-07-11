# Appointment Recall/Reminder System (Design Spec)

**Date:** 2026-07-11
**Status:** Approved design — ready for implementation plan.
**Sequencing:** second of 5 planned sub-projects (security → **recall/reminder system** → unified clinic gross profit → multi-dentist support). Security and testing (coverage gap-fill) are both DONE — see memory `project_security_hardening_2`.

## Context

No SMS/email/notification infrastructure exists anywhere in the codebase today
(confirmed by search — `patients` has `phone`/`email` columns, `appointments`
has `appointment_date`/`treatment_type`/`status`, and nothing sends anything
to either). This is a greenfield feature.

The desktop app is not always running — it's opened by the dentist during
business hours, not a 24/7 server. But `dental_clinic.py` doubles as the
**cloud node** app when `CLINIC_CLOUD_MODE=1` (multi-tenant: one master
registry `cloud_master.db` + one SQLite file per clinic, synced from each
clinic's desktop app via the existing `cloud_sync_worker`). That cloud
process already runs several always-on background threads (`_backup_loop`,
`cloud_sync_worker`, `license_recheck_worker`) — the same pattern is reused
here so reminders fire reliably regardless of whether any clinic's desktop
app happens to be open.

Cloud-side databases (`cloud_master.db` + per-clinic DBs) are **plaintext by
explicit prior decision** — the encryption-at-rest work (PR #23) scoped
SQLCipher to the desktop DB only, deliberately excluding the multi-tenant
cloud registry. This matters because reminder credentials (SMTP password,
SMS provider API key) would otherwise sit as plain columns on the cloud host.

## Goal

Send an SMS and/or email reminder ahead of a patient's scheduled appointment
(any `treatment_type`, including follow-ups) — reduces no-shows. Each clinic
configures its own delivery: whether reminders are on, how far ahead to send,
and its own SMTP account + SMS provider key. Dispatch happens from the cloud
node so it works even when the clinic's desktop app is closed.

## Decisions (2026-07-11)

1. **Trigger = scheduled appointment, not a periodic recall interval.**
   Reminds a patient of an appointment they already have booked (including
   follow-ups), a fixed number of hours ahead. Not "come back for a checkup
   every 6 months" — that's a different feature, not requested here, and can
   be added later as a second trigger type if wanted without disturbing this
   design (same `reminders_log`/dispatch shape, different due-query).

2. **Dispatch from the cloud node**, as a new background thread
   (`reminder_dispatch_loop()`) started only under `CLINIC_CLOUD_MODE=1`,
   mirroring `_backup_loop`. Runs every ~10 minutes, iterates every clinic's
   synced DB, checks its due appointments, sends, logs. Rejected: desktop-only
   loop (misses reminders whenever the app is closed — the common case).
   Rejected: a brand-new separate Docker service for this (`cloud/backup.py`
   is its own container specifically because a *data* bug there must never be
   able to take the live DB down with it; a reminder-send bug has no such
   blast radius — a background thread inside the existing cloud process is
   simpler to deploy and enough).

3. **Bring-your-own credentials, per clinic.** Each clinic supplies its own
   SMTP login and (optionally) an SMS provider API key in Settings, synced to
   the cloud like other settings. No shared platform sender, no per-message
   cost borne by the vendor, works for any clinic in any country. Trade-off
   accepted: a small one-time setup step per clinic (standard SMTP fields —
   host/port/user/password — which every email provider documents).

4. **SMTP password + SMS API key are encrypted at the application layer**
   before being written to the (plaintext) cloud DB — Fernet symmetric
   encryption, one cloud-wide key read from an env var
   (`CLINIC_CLOUD_REMINDER_KEY`), analogous in spirit to the desktop's DPAPI
   key but scoped to just these two credential fields rather than the whole
   DB. Chosen over leaving them plaintext (unlike the rest of cloud data,
   these are live third-party account credentials, not clinic patient data —
   worth the small added complexity). Chosen over extending full-DB
   encryption to the cloud tier (that was an explicit, already-shipped scope
   decision in PR #23; revisiting it is out of scope here).

5. **Email via stdlib `smtplib`** (no new dependency). **SMS via a small
   provider-adapter interface**, shipping with one implementation first
   (Twilio — most universally available, best documented) so additional
   providers can be added later without touching the dispatch loop.

6. **Idempotency via a `reminders_log` table**, keyed on
   `(appointment_id, channel)`. A *sent* reminder is never resent. A *failed*
   attempt (bad creds, provider error) is retried on the next loop cycle,
   not spammed per-cycle — the log only records `sent`/`failed` outcomes, and
   the due-query simply excludes appointments that already have a `sent` row
   for that channel.

## Data model

New table, created per clinic DB (both desktop schema and cloud per-clinic
schema — same `init_database()` migration path already used for every other
table):

```sql
CREATE TABLE IF NOT EXISTS reminders_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER NOT NULL,
    channel TEXT NOT NULL,           -- 'email' | 'sms'
    status TEXT NOT NULL,            -- 'sent' | 'failed'
    error_detail TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments (id)
);
```

Reminder configuration lives on the existing clinic-settings row (same table
branding/theme settings already live on — no new table needed):
`reminders_enabled`, `reminder_lead_hours`, `reminder_message_template`,
`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password_enc`, `sms_provider`,
`sms_api_key_enc`, `sms_from_number`.

## Dispatch loop

`reminder_dispatch_loop()` in `dental_clinic.py`, started next to the other
daemon threads only when `CLOUD_MODE` is on:

```
every ~10 minutes:
    for each clinic DB (skip early if reminders_enabled is false):
        due = appointments where now <= appointment_date <= now + lead_hours
              and status = 'scheduled'
              and no reminders_log row (appointment_id, channel) with status='sent'
        for each due appointment, for each enabled channel (email/sms):
            render message_template with {patient_name, date, time}
            try: send via channel adapter; log status='sent'
            except: log status='failed', error_detail=str(exc)
```

Cheap by construction: clinics with reminders off are skipped before any
appointment query runs; the `reminders_log` join keeps the due-query small
(indexed on `appointment_id`).

"Enabled channels" = whichever credentials are actually filled in — filling
SMTP fields enables email, filling an SMS API key enables SMS. No separate
per-channel toggle on top of that; leaving a credential blank is how a
clinic opts a channel out.

## Senders (pluggable interface)

```python
def send_email(to: str, subject: str, body: str, smtp_cfg: dict) -> None: ...
def send_sms(to: str, body: str, sms_cfg: dict) -> None: ...
```

`send_email` uses `smtplib.SMTP`/`SMTP_SSL` per `smtp_cfg['port']`. `send_sms`
starts with a Twilio adapter (`sms_cfg['provider'] == 'twilio'`); the
interface is provider-keyed so a second provider is a new adapter function,
not a dispatch-loop change. Both raise on failure — the loop catches and
logs, never crashes.

## Staff-facing UI

New "Reminders" panel in Settings, following the existing Branding-panel
pattern (desktop portal, EN/AR): on/off toggle, lead-hours field, SMTP
fields, SMS provider + API key fields, an editable message template with
`{patient_name}`/`{date}`/`{time}` placeholders, and a short history list
(last N rows from `reminders_log`, sent/failed) reusing existing table/list
UI conventions already in the app.

## Error handling

- Missing/malformed patient phone or email → skip that channel for that
  patient, log `failed`, continue with the rest of the batch (one bad record
  never blocks others — same principle `backup.py`/`run_once` already
  follows for corrupt DBs).
- SMTP/SMS auth failure → logged, retried next cycle (see idempotency rule
  above) — not treated as a hard stop for the whole clinic's batch.
- Loop-level exception (e.g. a clinic DB is mid-sync/locked) → caught per
  clinic, logged, other clinics in the same cycle unaffected.

## Testing

Unit tests only, no real network calls (mock `smtplib.SMTP` and the Twilio
client), matching this repo's existing style (`tmp_path` SQLite, no
external I/O):
- Due-query correctness (lead-hours boundary, already-sent exclusion,
  disabled-clinic skip).
- Idempotency (a `sent` row blocks resend; a `failed` row does not).
- Template rendering (placeholder substitution, missing-field tolerance).
- Sender failure paths (bad creds → `failed` logged, loop continues).
- Encrypt/decrypt round-trip for `smtp_password_enc`/`sms_api_key_enc`.

## Non-goals (explicitly out of scope for this spec)

- Periodic "come back in N months" recall (different trigger — could reuse
  this same `reminders_log`/dispatch shape later as a second trigger type).
- WhatsApp or other channels beyond SMS/email.
- Multi-clinic/multi-dentist consolidation (roadmap item 5, its own future
  spec) — this design works within today's one-clinic-per-DB model
  unchanged; a clinic with multiple doctors already works today since
  appointments aren't doctor-locked.
- A platform-provided shared sender / usage billing tier (rejected in favor
  of bring-your-own credentials, see Decision 3).
