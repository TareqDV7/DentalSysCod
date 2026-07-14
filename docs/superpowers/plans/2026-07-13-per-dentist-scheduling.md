# Per-Dentist Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the appointment overlap check from blocking two different dentists booked in the same slot, and let the desktop Appointments calendar show one dentist's schedule at a time.

**Architecture:** Two independent, additive changes. Backend: add a dentist-scoping clause to the existing conflict-check query inside `POST /api/appointments` (no new endpoint, no schema change — `dentist_id` already exists on `appointments`). Frontend: a filter `<select>` above the existing monthly calendar grid that pre-filters `appointmentsCache` before `renderAppointmentsCalendar`'s day-grouping logic runs (no new API call — `dentistsCache` and per-appointment `dentist_id` already ship to the browser).

**Tech Stack:** Flask + sqlite3 (`dental_clinic.py`), vanilla JS in a Python-string HTML template (`templates.py`), pytest + Flask test client.

## Global Constraints

- Conflict scoping rule (spec Decision 3): a new appointment for `dentist_id = X` conflicts with an existing appointment only if that appointment's `dentist_id` also equals `X`, **or if either side's `dentist_id` is NULL**. Two different named dentists at the same time never conflict. Unassigned is clinic-wide risk and conflicts against everything, including other unassigned bookings.
- No new appointment-edit/reschedule endpoint (spec Decision 4) — only the `POST /api/appointments` create route's overlap query changes. Status-change and delete routes are untouched.
- Calendar view mechanism is a filter dropdown only (spec Decision 2) — no swimlanes, no color-coding, no mobile UI change.
- Every step below was written against the CURRENT state of `dental_clinic.py` / `templates.py` (re-verified 2026-07-13, after the per-dentist-reporting commits landed) — line numbers are accurate as of this plan's authoring, not copied from the design spec.

---

### Task 1: Dentist-scoped appointment conflict check

**Files:**
- Modify: `dental_clinic.py:3885-3895` (conflict query inside `POST /api/appointments`, in `appointments()`)
- Create: `tests/test_dentist_scoped_conflicts.py`

**Interfaces:**
- Consumes: the route's existing local `dentist_id` variable (already resolved by the time this query runs — an `int` or `None`, set at `dental_clinic.py:3873-3883` from either the request body or the session's dentist auto-fill).
- Produces: nothing new consumed by later tasks — this task is self-contained.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dentist_scoped_conflicts.py`:

```python
"""Dentist-scoped overlap check for POST /api/appointments.

Two DIFFERENT named dentists may be booked in the same slot (they're
different people, not double-booking each other). An unassigned booking
(dentist_id NULL) is clinic-wide risk and conflicts against everything,
including other unassigned bookings, per
docs/superpowers/specs/2026-07-12-per-dentist-scheduling-design.md
Decision 3.
"""
import dental_clinic
import permissions
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'dentist_scoped_conflicts_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(name='A'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, 'B', '0500'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _dentist(username):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 1)',
        (username, 'x', username),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _book(client, pid, dentist_id=None, when='2026-09-01T10:00', duration=30):
    body = {'patient_id': pid, 'appointment_date': when, 'duration': duration}
    if dentist_id is not None:
        body['dentist_id'] = dentist_id
    return client.post('/api/appointments', json=body)


def test_same_dentist_overlap_still_blocked(client):
    dr = _dentist('dr_a')
    first = _book(client, _patient('One'), dentist_id=dr, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=dr, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_different_dentists_overlap_allowed(client):
    dr_a = _dentist('dr_a')
    dr_b = _dentist('dr_b')
    first = _book(client, _patient('One'), dentist_id=dr_a, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=dr_b, when='2026-09-01T10:15')
    assert second.status_code == 200, second.get_json()


def test_unassigned_new_conflicts_with_assigned_existing(client):
    dr_a = _dentist('dr_a')
    first = _book(client, _patient('One'), dentist_id=dr_a, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=None, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_assigned_new_conflicts_with_unassigned_existing(client):
    first = _book(client, _patient('One'), dentist_id=None, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    dr_a = _dentist('dr_a')
    second = _book(client, _patient('Two'), dentist_id=dr_a, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_both_unassigned_overlap_blocked(client):
    first = _book(client, _patient('One'), dentist_id=None, when='2026-09-01T10:00')
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=None, when='2026-09-01T10:15')
    assert second.status_code == 409, second.get_json()


def test_different_dentists_non_overlapping_times_never_conflict(client):
    dr_a = _dentist('dr_a')
    dr_b = _dentist('dr_b')
    first = _book(client, _patient('One'), dentist_id=dr_a, when='2026-09-01T10:00', duration=30)
    assert first.status_code == 200, first.get_json()
    second = _book(client, _patient('Two'), dentist_id=dr_b, when='2026-09-01T11:00', duration=30)
    assert second.status_code == 200, second.get_json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy python -m pytest tests/test_dentist_scoped_conflicts.py -v`

Expected: `test_same_dentist_overlap_still_blocked` and `test_both_unassigned_overlap_blocked` and the two mixed-unassigned tests PASS already (today's clinic-wide check happens to satisfy them by accident, since it blocks ALL overlaps). `test_different_dentists_overlap_allowed` and `test_different_dentists_non_overlapping_times_never_conflict` — the overlapping one (`test_different_dentists_overlap_allowed`) FAILS with `assert 409 == 200` (today's check wrongly blocks different dentists). This confirms the test suite actually exercises the bug.

- [ ] **Step 3: Add the dentist-scoping clause to the conflict query**

In `dental_clinic.py`, replace lines 3885-3895:

```python
        cursor.execute('''
            SELECT a.id, a.appointment_date, a.duration,
                   p.first_name || ' ' || p.last_name as patient_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            WHERE a.status IN ('scheduled', 'confirmed')
              AND datetime(?) < datetime(a.appointment_date, '+' || a.duration || ' minutes')
              AND datetime(?, '+' || ? || ' minutes') > datetime(a.appointment_date)
            ORDER BY a.appointment_date ASC
            LIMIT 1
        ''', (appointment_date, appointment_date, duration))
```

with:

```python
        cursor.execute('''
            SELECT a.id, a.appointment_date, a.duration,
                   p.first_name || ' ' || p.last_name as patient_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            WHERE a.status IN ('scheduled', 'confirmed')
              AND datetime(?) < datetime(a.appointment_date, '+' || a.duration || ' minutes')
              AND datetime(?, '+' || ? || ' minutes') > datetime(a.appointment_date)
              AND (? IS NULL OR a.dentist_id IS NULL OR a.dentist_id = ?)
            ORDER BY a.appointment_date ASC
            LIMIT 1
        ''', (appointment_date, appointment_date, duration, dentist_id, dentist_id))
```

(Only the `WHERE` clause gains one line, and the parameter tuple gains `dentist_id` twice. `dentist_id` is already in scope — it's the same local variable used later at line ~3913-3916 to INSERT the new appointment row.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk proxy python -m pytest tests/test_dentist_scoped_conflicts.py -v`

Expected: all 6 tests PASS.

- [ ] **Step 5: Run the pre-existing conflict regression test**

Run: `rtk proxy python -m pytest tests/test_appointment_conflict.py -v`

Expected: all 4 tests (parametrized `scheduled`/`confirmed`/`cancelled`/`completed`) still PASS unchanged — these bookings never set `dentist_id`, so both sides are NULL and the new clause's `a.dentist_id IS NULL` branch preserves the old clinic-wide behavior for unassigned-only bookings.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_dentist_scoped_conflicts.py
git commit -m "fix(appointments): scope overlap conflict check to dentist_id"
```

---

### Task 2: Calendar dentist filter dropdown

**Files:**
- Modify: `templates.py:2440-2447` (calendar-controls markup, inside `appointments-calendar-view`)
- Modify: `templates.py:6711-6733` (`renderAppointmentsCalendar` — add pre-filter before the day-grouping loop)
- Modify: `templates.py:6659-6672` (`loadAppointments` — populate the filter's options after fetching)
- Test: `tests/test_calendar_dentist_filter_ui.py`

**Interfaces:**
- Consumes: `dentistsCache` (`{id, display_name}[]`, already populated by `loadDentists()`, `templates.py:5427`), `appointmentsCache` (`{..., dentist_id}[]`, populated by `loadAppointments()`, `templates.py:6669`).
- Produces: `populateCalendarDentistFilter()` (new function) and a `<select id="calendar-dentist-filter">` element — nothing later depends on these; this task is self-contained.

Filter value convention: `""` = All (default), `"unassigned"` = appointments with no `dentist_id`, otherwise the string form of a dentist's numeric `id`.

- [ ] **Step 1: Write the failing presence tests**

Create `tests/test_calendar_dentist_filter_ui.py`:

```python
"""Calendar dentist filter: presence-check style, matching
tests/test_per_dentist_reporting_ui.py. No Playwright, no mobile UI --
mobile has no calendar view to extend (see the design spec's non-goals)."""
from templates import HTML_TEMPLATE


def test_calendar_dentist_filter_select_present():
    assert 'id="calendar-dentist-filter"' in HTML_TEMPLATE


def test_populate_calendar_dentist_filter_function_present():
    assert 'function populateCalendarDentistFilter(' in HTML_TEMPLATE


def test_render_appointments_calendar_reads_filter_value():
    assert "getElementById('calendar-dentist-filter')" in HTML_TEMPLATE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy python -m pytest tests/test_calendar_dentist_filter_ui.py -v`

Expected: all 3 FAIL — none of these strings exist in `HTML_TEMPLATE` yet.

- [ ] **Step 3: Add the filter dropdown markup**

In `templates.py`, replace lines 2440-2447:

```html
                            <div class="calendar-controls">
                                <div class="toolbar-row" style="margin-top:0;">
                                    <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(-1)" data-i18n="previous_month">Previous Month</button>
                                    <button class="btn btn-warning" type="button" onclick="goToCurrentCalendarMonth()" data-i18n="current_month">Current Month</button>
                                    <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(1)" data-i18n="next_month">Next Month</button>
                                </div>
                                <div id="calendar-month-label" class="calendar-month-title"></div>
                            </div>
```

with:

```html
                            <div class="calendar-controls">
                                <div class="toolbar-row" style="margin-top:0;">
                                    <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(-1)" data-i18n="previous_month">Previous Month</button>
                                    <button class="btn btn-warning" type="button" onclick="goToCurrentCalendarMonth()" data-i18n="current_month">Current Month</button>
                                    <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(1)" data-i18n="next_month">Next Month</button>
                                    <select id="calendar-dentist-filter" class="form-control" style="max-width:220px;" onchange="renderAppointmentsCalendar(appointmentsCache)"></select>
                                </div>
                                <div id="calendar-month-label" class="calendar-month-title"></div>
                            </div>
```

- [ ] **Step 4: Add the `populateCalendarDentistFilter` function**

In `templates.py`, immediately after the existing `populateDentistSelect` function (after line 5442, i.e. right after its closing `}`), insert:

```javascript

        function populateCalendarDentistFilter() {
            const sel = document.getElementById('calendar-dentist-filter');
            if (!sel) return;
            const previous = sel.value;
            const opts = [`<option value="">${t('all_dentists', 'All dentists')}</option>`];
            dentistsCache.forEach(d => {
                const name = String(d.display_name || '').trim();
                if (name) opts.push(`<option value="${d.id}">${escapeHtml(name)}</option>`);
            });
            opts.push(`<option value="unassigned">${t('unassigned', 'Unassigned')}</option>`);
            sel.innerHTML = opts.join('');
            if ([...sel.options].some(o => o.value === previous)) sel.value = previous;
        }
```

- [ ] **Step 5: Filter `appointmentsCache` before day-grouping in `renderAppointmentsCalendar`**

In `templates.py`, inside `renderAppointmentsCalendar` (starts line 6711), replace this block (current lines 6724-6733):

```javascript
            const grouped = {};
            appointments.forEach(apt => {
                const d = parseAppointmentDate(getAppointmentDateValue(apt));
                if (!d) return;
                if (d.getFullYear() === year && d.getMonth() === month) {
                    const key = d.getDate();
                    grouped[key] = grouped[key] || [];
                    grouped[key].push(apt);
                }
            });
```

with:

```javascript
            const filterSelect = document.getElementById('calendar-dentist-filter');
            const filterValue = filterSelect ? filterSelect.value : '';
            const filtered = !filterValue ? appointments : appointments.filter(apt => {
                if (filterValue === 'unassigned') return apt.dentist_id == null;
                return String(apt.dentist_id) === filterValue;
            });

            const grouped = {};
            filtered.forEach(apt => {
                const d = parseAppointmentDate(getAppointmentDateValue(apt));
                if (!d) return;
                if (d.getFullYear() === year && d.getMonth() === month) {
                    const key = d.getDate();
                    grouped[key] = grouped[key] || [];
                    grouped[key].push(apt);
                }
            });
```

- [ ] **Step 6: Populate the filter when appointments load**

In `templates.py`, inside `loadAppointments` (starts line 6659), find this line (current line 6671):

```javascript
                renderAppointmentsCalendar(appointmentsCache);
```

Replace it with:

```javascript
                populateCalendarDentistFilter();
                renderAppointmentsCalendar(appointmentsCache);
```

- [ ] **Step 7: Run the presence tests to verify they pass**

Run: `rtk proxy python -m pytest tests/test_calendar_dentist_filter_ui.py -v`

Expected: all 3 PASS.

- [ ] **Step 8: Manual smoke check (desktop only, not automatable here)**

Start the app locally, open Appointments → Calendar, create appointments for two different dentists and one unassigned in the same month, confirm the new "All dentists / <names> / Unassigned" dropdown filters the grid correctly and "All dentists" restores the full view. Not part of the automated gate — flag as a user-side follow-up like the reporting sub-project's Reports-tab visual check.

- [ ] **Step 9: Commit**

```bash
git add templates.py tests/test_calendar_dentist_filter_ui.py
git commit -m "feat(appointments): add per-dentist filter to the calendar view"
```

---

### Task 3: Full regression gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite with a trustworthy exit code**

Do NOT pipe through `tail` — piping masks the real exit code (learned earlier this session: `cmd | tail -30` reports `tail`'s exit status, not the command under test's). Redirect to a file instead:

```bash
rtk proxy python -m pytest tests/ -q > "$CLAUDE_JOB_DIR/tmp/pytest_full.txt" 2>&1; echo "EXITCODE:$?" >> "$CLAUDE_JOB_DIR/tmp/pytest_full.txt"
```

- [ ] **Step 2: Verify the result**

Read the tail of `$CLAUDE_JOB_DIR/tmp/pytest_full.txt`. Expected: `EXITCODE:0`, no `FAILED` lines anywhere in the file (`grep -c FAILED` returns 0). Baseline before this plan was ~970 collected tests across 109 files; this plan adds 9 more (6 in Task 1, 3 in Task 2) — an exact final count isn't load-bearing, only zero failures and exit code 0 are.

- [ ] **Step 3: If green, this sub-project is done**

Both halves of "1 and 2 per dentist" (per-dentist profit reporting, shipped earlier, and per-dentist scheduling, this plan) are now complete. No further commit needed for this step — Tasks 1 and 2 already committed their own work.
