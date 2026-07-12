# Per-Dentist Scheduling (Design Spec)

**Date:** 2026-07-12
**Status:** Approved design — ready for implementation plan.
**Sequencing:** the other deferred half of "1 and 2 per dentist" (per-dentist
profit reporting was #2, shipped in
`docs/superpowers/specs/2026-07-12-per-dentist-reporting-design.md`; this is
#1). That spec's non-goals section explicitly named this as future work:
"Per-dentist appointment/scheduling views — a separate, larger, not-yet-
started future spec."

## Context

`dentist_id` (nullable) already exists on `appointments`, populated the same
way as `patient_followups`/`billing`: desktop auto-fills from
`session.get('uid')` when that user `is_dentist=1`, else NULL; mobile has no
per-staff login (device/clinic-token only) so always manual-picks via
`GET /api/dentists` (`dental_clinic.py:2633`, active dentists only).

The existing appointment-overlap conflict check
(`dental_clinic.py:3885-3907`, inside the `POST /api/appointments` route) is
clinic-wide: any two appointments overlapping in time conflict, regardless of
which dentist (or no dentist) is assigned to either one. There is no
reschedule/edit endpoint for appointments — only a status-only
`PUT /api/appointments/<id>/status` (`:3945`) and a full `DELETE` (`:3963`) —
so the create route's conflict check is the only place this logic lives.

The desktop Appointments tab's monthly calendar
(`renderAppointmentsCalendar`, `templates.py:6711`) shows every appointment
for the month with no dentist grouping, filter, or visible dentist name.
`dentistsCache` (active dentists, `id`/`display_name`) and each appointment's
`dentist_id` already ship to the browser today (`templates.py:5428`,
`dental_clinic.py:3820`'s `SELECT a.*`) — no new API is needed to filter
client-side.

## Goal

Two independent fixes under one feature: (1) stop the overlap check from
blocking two *different* dentists booked in the same slot, and (2) let the
desktop calendar show one dentist's schedule at a time.

## Decisions (2026-07-12, all user-approved during brainstorming)

1. **Both dentist-aware conflicts and a calendar view filter**, not just one.
   A real multi-dentist clinic needs both: dentists can genuinely double-book
   the *room* schedule without double-booking each other, and front desk
   needs to see one dentist's day in isolation.

2. **View mechanism: a filter dropdown**, not swimlane columns or
   color-coding. Smallest change — same monthly grid
   (`renderAppointmentsCalendar`), same render call, just a pre-filter on
   `appointmentsCache` before grouping by day. Dropdown options: "All"
   (default), each active dentist from `dentistsCache`, and "Unassigned".

3. **Conflict scoping rule:** a new appointment for `dentist_id = X` conflicts
   with an existing appointment only if that existing appointment's
   `dentist_id` also equals `X`, **or if either side's `dentist_id` is
   NULL**. Two named, *different* dentists at the same time never conflict.
   An unassigned booking is treated as clinic-wide risk (safest default —
   nobody knows for sure it won't collide) and conflicts against everything,
   including other unassigned bookings.

4. **No new appointment-edit endpoint.** The conflict-scoping fix only
   touches the existing `POST /api/appointments` create route's overlap
   query. Status changes and deletes don't re-check overlap today and this
   spec doesn't add that.

## Implementation shape

**Conflict query** (`dental_clinic.py:3885-3895`), conceptually — add a
dentist-scoping clause to the existing time-overlap WHERE:

```sql
WHERE a.status IN ('scheduled', 'confirmed')
  AND datetime(?) < datetime(a.appointment_date, '+' || a.duration || ' minutes')
  AND datetime(?, '+' || ? || ' minutes') > datetime(a.appointment_date)
  AND (? IS NULL OR a.dentist_id IS NULL OR a.dentist_id = ?)
```
(`?` bound twice to the new appointment's resolved `dentist_id`.) When the
new appointment's own `dentist_id` is NULL, the added clause's first
`? IS NULL` branch makes it match every existing appointment regardless of
their `dentist_id` — preserving "unassigned vs. everything."

**Calendar filter** (`templates.py`, near `renderAppointmentsCalendar`): a
`<select id="calendar-dentist-filter">` above `#appointments-calendar`,
populated from `dentistsCache` (already loaded) plus `All`/`Unassigned`
options. `renderAppointmentsCalendar` (or its caller) filters
`appointmentsCache` by the selected value (`null`/`undefined` dentist_id →
"Unassigned" bucket) before the existing month-grouping logic runs. Re-render
on both month navigation and filter change, same pattern already used for
month navigation (`changeCalendarMonth`, `:6828`).

## Non-goals

- Mobile calendar/scheduling UI — no such filtered view exists on mobile
  today; out of scope (mobile already manually picks `dentist_id` at booking
  time via its own picker, unaffected by this spec).
- Swimlane/column calendar layout or color-coding by dentist (Decision 2) —
  filter dropdown only.
- A reschedule/edit endpoint, or re-checking conflicts on status change —
  neither exists today and this spec doesn't add them (Decision 4).
- Per-dentist working hours/availability rules — out of scope, this is
  conflict-avoidance on existing bookings only, not a scheduling-rules
  engine.

## Testing

- Backend: same-dentist time overlap → 409 (existing behavior, must still
  hold); different-dentist time overlap → 201, no conflict (the fix); new
  appointment unassigned + existing has a dentist, overlapping → 409;
  existing unassigned + new has a dentist, overlapping → 409; both
  unassigned, overlapping → 409; non-overlapping times never conflict
  regardless of dentist (regression baseline).
- Frontend: presence test for the filter `<select>` markup and its filtering
  function in `templates.py`, matching this session's established
  UI-presence-test style (no Playwright, no mobile UI to extend).
