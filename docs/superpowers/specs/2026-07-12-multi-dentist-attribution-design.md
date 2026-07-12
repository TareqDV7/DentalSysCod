# Multi-Dentist Attribution (Design Spec)

**Date:** 2026-07-12
**Status:** Approved design — ready for implementation plan.
**Sequencing:** fifth and last of 5 planned sub-projects (security → testing →
recall/reminder system → unified gross profit → **multi-dentist support**). All
prior four are DONE — see memory `project_security_hardening_2`.

## Context

Zero existing dentist/doctor attribution exists anywhere in the schema today —
no `dentist_id`/`doctor_id`/`assigned_to` column on `appointments`,
`patient_followups`, `visits`, or `billing`. The only "doctor" concept is a
single clinic-wide branding setting (`doctor_name`/`doctor_name_ar` in
`app_settings`, used for Post Studio marketing templates — not clinical
attribution).

`users`/`user_permissions` (from the RBAC project, PR #22) already support
multiple staff accounts with custom permissions, but have no field
distinguishing a dentist from front-desk staff. RBAC was explicitly built with
this in mind (see memory `project_security_hardening_round`'s RBAC plan: "the
upcoming multi-dentist sub-project will also need a multi-staff-account
concept — building it once here avoids reworking auth twice").

Mobile has **no per-staff-user login at all** — it authenticates via a
clinic-wide device/pairing token (`X-Device-Token`/`X-Clinic-Token`,
confirmed in `clinic_api.dart` and the RBAC spec's own note that "RBAC only
restricts session-authenticated (desktop) requests... mobile/device and
clinic-token requests never reach this gate"). There is no "current user" on
a phone to default anything from.

## Goal

Tag which dentist did each appointment/follow-up/billing entry, so the data
exists and is trustworthy for later reporting. This slice is data-tagging
only — no per-dentist scheduling, no per-dentist reports UI yet.

## Decisions (2026-07-12, all user-approved during brainstorming)

1. **Full "multi-dentist" vision decomposed into two sub-projects; this spec
   covers attribution only.** Per-dentist scheduling/calendars (each dentist
   has their own working hours, appointment slots, booking picks a dentist)
   is a separate, larger, future spec — it touches the whole appointments
   UI, conflict-checking, and holidays logic, and isn't needed to start
   getting attribution data flowing.

2. **Single `dentist_id` FK column, added directly to each of the three
   tables** (`appointments`, `patient_followups`, `billing`) — not a generic
   polymorphic `dentist_assignments(entity_type, entity_id, dentist_id)`
   table. Matches this codebase's existing style (e.g. `procedure_id` already
   sits directly on `patient_followups`, not in a separate association
   table) and avoids a join on every read. Nullable — existing records stay
   unattributed, no backfill migration.

3. **`is_dentist` flag on `users`**, not "any staff account can be picked."
   A front-desk account showing up as an assignable dentist would be
   semantically wrong. Settable from the existing Manage Staff (RBAC) screen.

4. **Attribution mechanism differs by platform, out of necessity, not
   inconsistency:**
   - **Desktop:** auto-fills `dentist_id` from the session's logged-in user
     (`session.get('uid')`) when a record is created, shown as an editable
     dropdown (only `is_dentist=1` users listed) — a session-authenticated
     user's own entries default to themselves, but front-desk staff can
     still book/log on a dentist's behalf by changing the dropdown.
   - **Mobile:** always a manual picker, defaulting to unassigned/`null`
     until picked — there is no logged-in user to default from (Context
     above). This is a real, permanent asymmetry, not a gap to close later.

5. **Scope: appointments + follow-ups + billing**, all three, in this slice
   (not follow-ups-only). Billing gets tagged too even though a shared-clinic
   invoice isn't always cleanly "one dentist's money" — the field is still
   useful for attribution/audit purposes, and adding it now avoids a second
   schema-touch later if per-dentist billing reporting is ever wanted.

6. **No reporting UI in this slice.** The gross-profit/dashboard/reports
   endpoints (`dental_clinic.py`'s `reports_summary`/`reports_weekly`, just
   unified in the prior sub-project) are **not** touched here — a per-dentist
   breakdown is a natural future extension once this tag exists and has been
   in use long enough to be trustworthy, but is explicitly out of scope now
   to keep this slice small and focused.

## Data model

```sql
-- users: new column
ALTER TABLE users ADD COLUMN is_dentist INTEGER DEFAULT 0;

-- appointments, patient_followups, billing: same new column on each
ALTER TABLE appointments ADD COLUMN dentist_id INTEGER REFERENCES users(id);
ALTER TABLE patient_followups ADD COLUMN dentist_id INTEGER REFERENCES users(id);
ALTER TABLE billing ADD COLUMN dentist_id INTEGER REFERENCES users(id);
```

Mobile local mirrors (`appointments`, `followups`, `billing_records`) get the
identical `dentist_id` column, synced bidirectionally the same way every
other field on these tables already is (no new sync mechanism — this is an
additive column on existing synced tables).

## Attribution logic

- **Desktop POST routes** (`/api/appointments`, `/api/patients/<id>/followups`,
  `/api/billing`): if `dentist_id` isn't explicitly provided in the request
  body, default to `session.get('uid')`. Validate that a provided
  `dentist_id` actually refers to a `users` row with `is_dentist=1` (reject
  otherwise — same validation posture as `procedure_id`'s existing
  active-row check).
- **Desktop PUT/edit routes**: `dentist_id` is editable like any other field.
- **Mobile create/edit**: `dentist_id` is a plain field on the form, no
  smart default, submitted like `procedure_id`/other fields already are.

## UI

- **Manage Staff (existing RBAC screen)**: add an "Is dentist" checkbox per
  account, alongside the existing permission checkboxes.
- **Appointment form, follow-up entry form, billing form** (both desktop and
  mobile): a dentist dropdown/picker, listing only `is_dentist=1` users.
  Desktop pre-selects the session user; mobile starts unselected.
- No changes to patient-facing surfaces (invoices, Post Studio, etc.) — this
  is internal attribution only.

## Testing

- Desktop: POST auto-fills from session; PUT allows override; dropdown
  rejects a `dentist_id` that isn't an `is_dentist=1` active user; existing
  records (nullable field) still round-trip through GET without error.
- Mobile: local schema migration adds the column cleanly; sync round-trips
  `dentist_id` in both directions; no default-from-session test (there is
  none to test — always manual there).

## Non-goals (explicitly out of scope for this spec)

- Per-dentist scheduling/calendars, working hours, appointment-slot ownership
  (Decision 1 — separate future spec, the other half of the roadmap item's
  original full vision).
- Per-dentist revenue/profit reporting UI or report-endpoint changes
  (Decision 6 — future extension once the tag is in use and trustworthy).
- Backfilling `dentist_id` on existing historical records (nullable field,
  old data simply stays unattributed).
- Any change to mobile's authentication model to introduce a per-staff login
  (Decision 4 — mobile's clinic-wide device/token auth is unchanged; the
  manual-picker requirement is a permanent consequence of that, not a gap).
