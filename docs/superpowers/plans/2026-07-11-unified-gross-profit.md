# Unified Clinic Gross Profit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One correct, consistent gross-profit figure computed the same way everywhere it's shown: desktop API (`/api/reports/summary`, `/api/reports/weekly`), desktop UI, and mobile's offline fallback.

**Architecture:** Fix the SQL in both desktop report endpoints to unify billing + follow-up-sheet charges into one formula (Task 1-2). Collapse the desktop UI's two redundant stat-cards into one (Task 3). Fix mobile's offline fallback, which turns out to query the wrong local table entirely (Task 4 — see Global Constraints). No new tables, no new dependencies.

**Tech Stack:** Flask/SQLite (desktop), Dart/sqflite (mobile offline fallback).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md`, all Decisions.
- **Formula (Decision 2):** `gross_profit = (Σ followup.price + Σ billing.subtotal) − (Σ followup.discount + Σ billing.discount) − Σ followup.lab_expense − general_expenses`. Charge-based, not cash-collected-based.
- **Second finding, not in the spec — discovered while implementing Task 1 (a test failure surfaced it, not a code review):** a lab-requiring follow-up auto-mirrors its `lab_expense` into the `expenses` table as a real payable (`source_type='followup'`, `dental_clinic.py:3376-3392` — pre-existing, unrelated feature). `general_expenses` in the formula above is **not** the same as the existing `expenses_total` field — it must exclude `source_type='followup'` rows, or the same lab cost gets subtracted twice (once via the direct `lab_expense` column, once via its mirrored `expenses` row). The existing `expenses`/`expenses_paid`/`expenses_postponed` response fields (used for their own display cards) are untouched — this exclusion applies ONLY inside the profit calculation. Applies identically to Task 4's mobile fix (local `expenses` table has the same `source_type` column, synced down from desktop).
- **Cost scope (Decision 1):** discounts + lab_expense + general expenses only. No inventory consumable cost, no new billing cost field.
- **API contract (Decision 4):** both `clinic_gross_profit` and `profit` JSON keys stay, both return the identical unified value. Never remove either key — `profit` is required by mobile's `WeeklyReport`/`MonthlyReport` Dart models (`report_service.dart:13,24,36,45,52,60`).
- **Desktop UI (Decision 5):** delete the "Profit" stat-card (`templates.py:2762`, `id="report-profit"`) and its `setText('report-profit', ...)` call (`templates.py:6831`); keep "Clinic Gross Profit" (`templates.py:2757`) as the one visible figure.
- **New finding, not in the spec — resolved during planning (Decision 6's open question):** mobile's local `visits` table (queried by `_localWeeklyReport`/`_localMonthlyReport`) is **not** what it looks like. There are two entirely separate concepts sharing confusing names:
  - Server-side `visits` table (`dental_clinic.py:890-907`) is a near-empty clinical log (`dentist_name`/`diagnosis`/`chief_complaint`/etc) — **no money fields at all**. This is what `/api/sync/export`'s bulk `"visits"` key actually contains (`SELECT * FROM visits`, via `SYNC_TABLES`, `dental_clinic.py:545-559`).
  - Mobile's local `followups` table (`database_service.dart:238-260`, synced from server `patient_followups` via the `'followups': 'patient_followups'` table-name mapping, `database_service.dart:39`) is the **actual local mirror of the money ledger** — `price`/`discount`/`lab_expense`/`payment`/`clinic_profit` columns, all present, already precomputed. Confirmed by `patient_service.dart:100-113`'s `updateVisit()`, which PUTs to `/api/patients/<id>/followups/<id>` — the real follow-up-sheet endpoint.
  - **Conclusion: `_localWeeklyReport`/`_localMonthlyReport` query the wrong local table** (`visits`, which is empty of money data in practice) instead of `followups` (which has everything needed, including a precomputed `clinic_profit` column matching the server exactly). This is a **pre-existing bug**, not something this feature introduces — fixed as part of Task 4 since it's the same code being touched, but it's worth stating plainly: today, mobile's offline profit/revenue numbers are effectively computed from empty data.
  - Mobile's local `billing_records` table (`database_service.dart:314-329`) already has `subtotal`/`discount`/`paid_amount`/`payment_date` — no gap there.
- Full existing test suite (935+ tests as of 2026-07-11) must stay green throughout. `flutter analyze` clean, `flutter test` green throughout.

---

### Task 1: Fix `/api/reports/summary`'s profit formula

**Files:**
- Modify: `dental_clinic.py:4260-4310` (the `reports_summary()` route body).
- Test: `tests/test_reports_gross_profit.py` (new)

**Interfaces:**
- Produces: `/api/reports/summary` response `clinic_gross_profit` and `profit` keys, both equal to the unified formula.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reports_gross_profit.py`:

```python
"""Unified clinic gross profit: billing revenue was previously invisible to
clinic_gross_profit (follow-up-sheet-only), and profit omitted lab_expense
entirely -- the two numbers disagreed. Both /api/reports/summary and
/api/reports/weekly must now return one correct, identical figure via both
the clinic_gross_profit and profit keys (profit key kept for API back-compat
with mobile's Dart models -- see plan Global Constraints)."""
import dental_clinic


DATE_RANGE = ('2020-01-01', '2099-12-31')  # wide enough to include "now" at any test-run time


def _patient(name='Gross', last='Profit', phone='0599'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _lab_procedure_id():
    # lab_expense is only persisted for procedures catalogued as
    # lab-requiring (dental_clinic.py's followups POST route zeroes it
    # otherwise via `if not requires_lab: lab_expense = 0`) -- an existing
    # business rule unrelated to this fix. Any test that wants a non-zero
    # lab_expense must go through a procedure_id pointing at such a row.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM treatment_procedures WHERE name = 'Lab Work Test'")
    row = cur.fetchone()
    if row:
        pid = row[0]
    else:
        cur.execute("INSERT INTO treatment_procedures (name, requires_lab) VALUES ('Lab Work Test', 1)")
        pid = cur.lastrowid
        conn.commit()
    conn.close()
    return pid


def _followup(client, pid, *, price, discount=0, lab_expense=0, payment=0, date='15/06/2026'):
    payload = {
        'followup_date': date, 'treatment_procedure': 'Filling',
        'price': price, 'discount': discount, 'lab_expense': lab_expense, 'payment': payment,
    }
    if lab_expense:
        payload['procedure_id'] = _lab_procedure_id()
    r = client.post(f'/api/patients/{pid}/followups', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def _billing(client, pid, *, subtotal, discount=0, paid_amount=0):
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': subtotal, 'discount': discount, 'paid_amount': paid_amount,
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def test_summary_gross_profit_includes_billing_revenue(client):
    # Before this fix, billing charges were invisible to clinic_gross_profit
    # entirely -- this is the exact bug the unification closes.
    pid = _patient()
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)

    r = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}')
    payload = r.get_json()
    # 500 - 50 discount - 0 lab_expense - 0 general expenses = 450
    assert payload['clinic_gross_profit'] == 450, payload
    assert payload['profit'] == 450, payload


def test_summary_gross_profit_combines_followup_and_billing(client):
    pid = _patient()
    _followup(client, pid, price=300, discount=20, lab_expense=30, payment=250)
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)

    r = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}')
    payload = r.get_json()
    # followup: 300 - 20 - 30 = 250. billing: 500 - 50 = 450. total = 700.
    assert payload['clinic_gross_profit'] == 700, payload
    assert payload['profit'] == 700, payload


def test_summary_profit_and_clinic_gross_profit_always_match(client):
    # The two keys must never disagree again -- that divergence was the bug.
    pid = _patient()
    _followup(client, pid, price=100, lab_expense=10, payment=100)
    _billing(client, pid, subtotal=200, paid_amount=200)

    r = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}')
    payload = r.get_json()
    assert payload['clinic_gross_profit'] == payload['profit'], payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reports_gross_profit.py -v`
Expected: FAIL — `client` fixture doesn't exist yet in this new file (need to add it), then once added, FAIL on the assertion values (old formula gives `clinic_gross_profit=0` for billing-only test since billing isn't counted, and `profit != clinic_gross_profit` in the combined test).

Add the fixture at the top of the same file, right after the imports and before `DATE_RANGE`:

```python
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'gross_profit_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client
```

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, replace the `reports_summary()` route's revenue/profit block (currently at lines 4267-4308) with:

```python
    # Revenue = payments collected across BOTH ledgers (follow-up sheet + billing)
    # so reports, the dashboard, and the mobile app all agree.
    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}', params)
    revenue = float(cursor.fetchone()[0] or 0)
    bclause, bparams = build_date_clause('COALESCE(payment_date, created_at)', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(paid_amount), 0) FROM billing WHERE 1 = 1{bclause}', bparams)
    revenue += float(cursor.fetchone()[0] or 0)

    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(COALESCE(lab_expense, 0)), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}', params)
    lab_expenses = cursor.fetchone()[0]

    clause, params = build_date_clause('expense_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "paid" AND 1=1{clause}', params)
    expenses_paid = cursor.fetchone()[0]

    clause, params = build_date_clause('expense_date', start_date, end_date)
    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "postponed" AND 1=1{clause}', params)
    expenses_postponed = cursor.fetchone()[0]

    expenses_total = float(expenses_paid or 0) + float(expenses_postponed or 0)

    # Unified gross profit (see docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md):
    # charge-based (price/subtotal, not payment), across BOTH ledgers, minus
    # discounts, lab expense, and general clinic expenses. Charge-based rather
    # than cash-collected because an unpaid balance shouldn't make completed,
    # billed work look unprofitable.
    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'''
        SELECT COALESCE(SUM(COALESCE(price, 0) - COALESCE(discount, 0)), 0)
        FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}
    ''', params)
    followup_net_charge = float(cursor.fetchone()[0] or 0)

    bclause, bparams = build_date_clause('COALESCE(payment_date, created_at)', start_date, end_date)
    cursor.execute(f'''
        SELECT COALESCE(SUM(COALESCE(subtotal, 0) - COALESCE(discount, 0)), 0)
        FROM billing WHERE 1 = 1{bclause}
    ''', bparams)
    billing_net_charge = float(cursor.fetchone()[0] or 0)

    # Every lab-requiring follow-up auto-mirrors its lab_expense into the
    # `expenses` table (source_type='followup', see the followups POST route)
    # so it shows up as a real payable. expenses_total above (used for the
    # 'expenses'/'expenses_paid'/'expenses_postponed' display fields) MUST
    # keep including those rows unchanged. But gross profit already subtracts
    # lab_expenses directly from patient_followups -- counting the mirrored
    # expense row too would double-subtract the same cost. Exclude
    # source_type='followup' from ONLY the general-expenses term used here.
    clause, params = build_date_clause('expense_date', start_date, end_date)
    cursor.execute(f'''
        SELECT COALESCE(SUM(amount), 0) FROM expenses
        WHERE payment_status IN ('paid', 'postponed')
        AND COALESCE(source_type, '') != 'followup'{clause}
    ''', params)
    general_expenses_for_profit = float(cursor.fetchone()[0] or 0)

    clinic_gross_profit = followup_net_charge + billing_net_charge - float(lab_expenses or 0) - general_expenses_for_profit

    clause, params = build_date_clause('start_date', start_date, end_date)
    cursor.execute(f'SELECT COUNT(*) FROM treatment_plans WHERE 1=1{clause}', params)
    plans_count = cursor.fetchone()[0]

    conn.close()
    return jsonify({
        'appointments': appointments_count,
        'visits': visits_count,
        'revenue': float(revenue or 0),
        'lab_expenses': float(lab_expenses or 0),
        'clinic_gross_profit': float(clinic_gross_profit or 0),
        'expenses': expenses_total,
        'expenses_paid': float(expenses_paid or 0),
        'expenses_postponed': float(expenses_postponed or 0),
        'profit': float(clinic_gross_profit or 0),
        'treatment_plans': plans_count
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reports_gross_profit.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_reports_gross_profit.py
git commit -m "fix(reports): unify clinic_gross_profit across billing and follow-up sheet"
```

---

### Task 2: Fix `/api/reports/weekly`'s profit formula

**Files:**
- Modify: `dental_clinic.py:4312-4405ish` (the `reports_weekly()` route body — re-read the current file first, Task 1 shifted line numbers below it in the same file).
- Test: extend `tests/test_reports_gross_profit.py`

**Interfaces:**
- Same as Task 1, for the `/api/reports/weekly` endpoint.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reports_gross_profit.py`:

`/api/reports/weekly` takes a fixed 7-day window from `week_start`, not an
arbitrary range like `/api/reports/summary` — the 2020..2099 wide-range trick
doesn't apply here. Billing rows always date themselves via `created_at` (the
POST endpoint accepts no explicit date), so to reliably land a billing row
inside a known week, compute `week_start` as the Monday of the *current* real
week (`datetime.date.today()`), not a fixed historical date — otherwise the
test would pass on zero in-window data both before and after the fix, proving
nothing.

```python
import datetime


def _monday_of_this_week():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def test_weekly_gross_profit_includes_billing_revenue(client):
    monday = _monday_of_this_week()
    pid = _patient()
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)  # created_at = now, falls in this week

    r = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}')
    payload = r.get_json()
    assert payload['clinic_gross_profit'] == 450, payload
    assert payload['profit'] == 450, payload


def test_weekly_gross_profit_combines_followup_and_billing(client):
    monday = _monday_of_this_week()
    followup_date = monday + datetime.timedelta(days=2)  # Wednesday of this week
    pid = _patient()
    _followup(client, pid, price=300, discount=20, lab_expense=30, payment=250,
              date=followup_date.strftime('%d/%m/%Y'))
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)

    r = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}')
    payload = r.get_json()
    # followup: 300 - 20 - 30 = 250. billing: 500 - 50 = 450. total = 700.
    assert payload['clinic_gross_profit'] == 700, payload
    assert payload['profit'] == 700, payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reports_gross_profit.py -v -k weekly`
Expected: FAIL — `clinic_gross_profit != profit` on the old formula (weekly's old `clinic_gross_profit` excludes billing, old `profit` excludes lab_expense).

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, re-read the file to find the current `reports_weekly()` function (search for `def reports_weekly`). Replace its revenue/lab_expenses/clinic_gross_profit/expenses block (originally at lines 4346-4363, may have shifted after Task 1's edit above it in the file) with the week-scoped equivalent of Task 1's fix:

```python
    cursor.execute('SELECT COALESCE(SUM(payment), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    revenue = float(cursor.fetchone()[0] or 0)
    cursor.execute('SELECT COALESCE(SUM(paid_amount), 0) FROM billing WHERE date(COALESCE(payment_date, created_at)) BETWEEN ? AND ?', (start_str, end_str))
    revenue += float(cursor.fetchone()[0] or 0)

    cursor.execute('SELECT COALESCE(SUM(COALESCE(lab_expense, 0)), 0) FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?', (start_str, end_str))
    lab_expenses = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "paid" AND date(expense_date) BETWEEN ? AND ?', (start_str, end_str))
    expenses_paid = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE payment_status = "postponed" AND date(expense_date) BETWEEN ? AND ?', (start_str, end_str))
    expenses_postponed = cursor.fetchone()[0]

    expenses_total = float(expenses_paid or 0) + float(expenses_postponed or 0)

    # Unified gross profit -- see Task 1's identical comment/rationale.
    cursor.execute('''
        SELECT COALESCE(SUM(COALESCE(price, 0) - COALESCE(discount, 0)), 0)
        FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?
    ''', (start_str, end_str))
    followup_net_charge = float(cursor.fetchone()[0] or 0)

    cursor.execute('''
        SELECT COALESCE(SUM(COALESCE(subtotal, 0) - COALESCE(discount, 0)), 0)
        FROM billing WHERE date(COALESCE(payment_date, created_at)) BETWEEN ? AND ?
    ''', (start_str, end_str))
    billing_net_charge = float(cursor.fetchone()[0] or 0)

    # See Task 1's identical comment: excludes the auto-mirrored lab_expense
    # rows (source_type='followup') already counted via `lab_expenses` above,
    # so the same cost isn't subtracted twice. expenses_total (the display
    # fields) is untouched.
    cursor.execute('''
        SELECT COALESCE(SUM(amount), 0) FROM expenses
        WHERE payment_status IN ('paid', 'postponed')
        AND COALESCE(source_type, '') != 'followup'
        AND date(expense_date) BETWEEN ? AND ?
    ''', (start_str, end_str))
    general_expenses_for_profit = float(cursor.fetchone()[0] or 0)

    clinic_gross_profit = followup_net_charge + billing_net_charge - float(lab_expenses or 0) - general_expenses_for_profit
```

And in that same function's final `jsonify({...})` block, change:
```python
        'clinic_gross_profit': float(clinic_gross_profit or 0),
```
(unchanged — `clinic_gross_profit` is now the local variable computed above) and change:
```python
        'profit': float(revenue or 0) - expenses_total,
```
to:
```python
        'profit': float(clinic_gross_profit or 0),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reports_gross_profit.py -v`
Expected: PASS (5 passed total across both tasks' tests in this file)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_reports_gross_profit.py
git commit -m "fix(reports): unify weekly clinic_gross_profit the same way as summary"
```

---

### Task 3: Desktop UI — collapse the two profit stat-cards into one

**Files:**
- Modify: `templates.py:2762` (delete the "Profit" stat-card div), `templates.py:6831` (delete its `setText` call).
- Test: `tests/test_reports_ui.py` (new)

**Interfaces:**
- Consumes: nothing new (pure HTML/JS deletion).

- [ ] **Step 1: Write the failing test**

Create `tests/test_reports_ui.py`:

```python
"""The Reports tab must show only ONE profit figure -- 'Clinic Gross Profit'
-- not two redundant stat-cards (the old 'Profit' card showed a DIFFERENT,
inconsistent number before the unification in dental_clinic.py)."""
from templates import HTML_TEMPLATE


def test_only_one_profit_stat_card_present():
    assert 'id="report-clinic-gross-profit"' in HTML_TEMPLATE
    assert 'id="report-profit"' not in HTML_TEMPLATE


def test_profit_js_setText_call_removed():
    assert "setText('report-profit'" not in HTML_TEMPLATE
    assert "setText('report-clinic-gross-profit'" in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reports_ui.py -v`
Expected: FAIL — both `id="report-profit"` and the `setText('report-profit'` call are still present.

- [ ] **Step 3: Delete the stat-card and its JS**

In `templates.py`, delete this line entirely (currently line 2762):
```html
                    <div class="stat-card"><h3 id="report-profit">₪ 0</h3><p data-i18n="profit">Profit</p></div>
```

And delete this line entirely (currently line 6831, inside `renderReportStats`):
```javascript
            setText('report-profit', money(data.profit));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reports_ui.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_reports_ui.py
git commit -m "fix(reports): remove redundant Profit stat-card, keep Clinic Gross Profit"
```

---

### Task 4: Mobile offline fallback — query the right local table

**Design note (found during planning):** this mobile codebase has **zero existing
tests that touch `DatabaseService`/sqflite** (checked every file under
`clinic_mobile_app/test/` — all are pure-logic tests on models/services with no
real database, e.g. `followup_balance_test.dart` tests `Followup.runningBalances()`,
a static pure function, with plain in-memory record lists). `DatabaseService` is
also a hard singleton (`DatabaseService._()` private constructor,
`DatabaseService.instance` the only accessor, `_db` cached as a private static —
`database_service.dart:16-23`) with no constructor-injection point for a test
database. Introducing real sqflite-backed test infrastructure would be a much
bigger, separate lift than this bug fix, and would break from this codebase's
established pure-logic-only testing convention. Instead: extract the arithmetic
into a pure, static, directly-testable function (matching the `Followup.
runningBalances()` pattern exactly), fix the SQL queries inline (untested at the
query level, same as every other line in this file today — verified instead via
`dart analyze` + the manual check in Task 5), and leave `DatabaseService` itself
untouched.

**Files:**
- Modify: `clinic_mobile_app/lib/services/report_service.dart` (`_localWeeklyReport`, `_localMonthlyReport`, plus a new pure static method).
- Test: `clinic_mobile_app/test/report_service_profit_test.dart` (new — flat `test/` dir, matching this codebase's existing layout; no `test/services/` subdirectory exists).

**Interfaces:**
- Produces: `ReportService.computeProfit({required double followupNetCharge, required double billingNetCharge, required double labExpense, required double expenses}) -> double` (pure, static — the one source of truth for the formula, used by both `_localWeeklyReport` and `_localMonthlyReport`).
- Consumes (unchanged, SQL-level, untested per the note above): local `followups` table (`database_service.dart:238-260` — `price`/`discount`/`lab_expense`/`followup_date`), local `billing_records` table (`database_service.dart:314-329` — `subtotal`/`discount`/`payment_date`), local `expenses` table (`database_service.dart:333-345` — `amount`/`status`/`expense_date`).

- [ ] **Step 1: Write the failing test**

Create `clinic_mobile_app/test/report_service_profit_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/report_service.dart';

// Pure-function test for the formula ReportService.computeProfit() uses --
// matches the desktop formula in dental_clinic.py's reports_summary()/
// reports_weekly() (see docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md):
// gross_profit = (followup net charge + billing net charge) - lab_expense - expenses.
void main() {
  group('ReportService.computeProfit', () {
    test('follow-up charge minus lab expense, no billing or general expenses', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 250, // 300 price - 50 discount, computed by the caller
        billingNetCharge: 0,
        labExpense: 30,
        expenses: 0,
      );
      expect(profit, 220);
    });

    test('combines follow-up and billing net charges', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 250,
        billingNetCharge: 450,
        labExpense: 0,
        expenses: 0,
      );
      expect(profit, 700);
    });

    test('subtracts general expenses on top of lab expense', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 300,
        billingNetCharge: 0,
        labExpense: 0,
        expenses: 120,
      );
      expect(profit, 180);
    });

    test('can go negative when costs exceed charges', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 50,
        billingNetCharge: 0,
        labExpense: 30,
        expenses: 100,
      );
      expect(profit, -80);
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clinic_mobile_app && flutter test test/report_service_profit_test.dart`
Expected: FAIL — `ReportService.computeProfit` doesn't exist yet.

- [ ] **Step 3: Fix the implementation**

In `clinic_mobile_app/lib/services/report_service.dart`, add this static method to the `ReportService` class (anywhere inside the class body, e.g. right after the constructor at line 68):

```dart
  /// Unified gross-profit formula -- see
  /// docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md.
  /// Charge-based (net-of-discount price/subtotal, not cash-collected),
  /// across both the follow-up sheet and billing, minus lab expense and
  /// general clinic expenses. Pure and static so it can be tested without a
  /// database, and so the desktop and offline-fallback formulas can never
  /// silently drift apart again.
  static double computeProfit({
    required double followupNetCharge,
    required double billingNetCharge,
    required double labExpense,
    required double expenses,
  }) =>
      followupNetCharge + billingNetCharge - labExpense - expenses;
```

Then replace `_localWeeklyReport` (lines 103-133) with:

```dart
  Future<WeeklyReport> _localWeeklyReport(DateTime weekStart) async {
    final db = await _db.database;
    final start = weekStart.toIso8601String().substring(0, 10);
    final end = weekStart
        .add(const Duration(days: 6))
        .toIso8601String()
        .substring(0, 10);

    final followupRows = await db.rawQuery(
        'SELECT COUNT(*) as cnt, '
        'COALESCE(SUM(COALESCE(price,0) - COALESCE(discount,0)),0) as net_charge, '
        'COALESCE(SUM(lab_expense),0) as lab '
        'FROM followups WHERE followup_date >= ? AND followup_date <= ?',
        [start, end]);
    final billingRows = await db.rawQuery(
        'SELECT COALESCE(SUM(COALESCE(subtotal,0) - COALESCE(discount,0)),0) as net_charge '
        'FROM billing_records WHERE payment_date >= ? AND payment_date <= ?',
        [start, end]);
    // Lab-requiring follow-ups auto-mirror their lab_expense into `expenses`
    // (source_type='followup', synced down from the desktop's identical
    // mechanism) so it shows up as a real payable. That's already counted
    // via followupRows' `lab` sum above -- excluding source_type='followup'
    // here avoids subtracting the same cost twice.
    final expRows = await db.rawQuery(
        'SELECT COALESCE(SUM(amount),0) as total FROM expenses '
        "WHERE expense_date >= ? AND expense_date <= ? AND status IN ('paid','postponed') "
        "AND (source_type IS NULL OR source_type != 'followup')",
        [start, end]);

    final visits = (followupRows.first['cnt'] as int?) ?? 0;
    final followupNetCharge = _d(followupRows.first['net_charge']);
    final billingNetCharge = _d(billingRows.first['net_charge']);
    final labExp = _d(followupRows.first['lab']);
    final expenses = _d(expRows.first['total']);
    final profit = computeProfit(
      followupNetCharge: followupNetCharge,
      billingNetCharge: billingNetCharge,
      labExpense: labExp,
      expenses: expenses,
    );

    return WeeklyReport(
      weekStart: start,
      weekEnd: end,
      visits: visits,
      revenue: followupNetCharge + billingNetCharge,
      expenses: expenses,
      labExpenses: labExp,
      profit: profit,
    );
  }
```

And replace `_localMonthlyReport` (lines 135-158) with:

```dart
  Future<MonthlyReport> _localMonthlyReport(int year, int month) async {
    final db = await _db.database;
    final prefix =
        '${year.toString().padLeft(4, '0')}-${month.toString().padLeft(2, '0')}';

    final followupRows = await db.rawQuery(
        'SELECT COUNT(*) as cnt, '
        'COALESCE(SUM(COALESCE(price,0) - COALESCE(discount,0)),0) as net_charge, '
        'COALESCE(SUM(lab_expense),0) as lab '
        'FROM followups WHERE followup_date LIKE ?',
        ['$prefix%']);
    final billingRows = await db.rawQuery(
        'SELECT COALESCE(SUM(COALESCE(subtotal,0) - COALESCE(discount,0)),0) as net_charge '
        'FROM billing_records WHERE payment_date LIKE ?',
        ['$prefix%']);
    // See _localWeeklyReport's identical comment: excludes the auto-mirrored
    // lab_expense rows already counted via followupRows' `lab` sum above.
    final expRows = await db.rawQuery(
        'SELECT COALESCE(SUM(amount),0) as total FROM expenses '
        "WHERE expense_date LIKE ? AND status IN ('paid','postponed') "
        "AND (source_type IS NULL OR source_type != 'followup')",
        ['$prefix%']);

    final visits = (followupRows.first['cnt'] as int?) ?? 0;
    final followupNetCharge = _d(followupRows.first['net_charge']);
    final billingNetCharge = _d(billingRows.first['net_charge']);
    final labExp = _d(followupRows.first['lab']);
    final expenses = _d(expRows.first['total']);
    final profit = computeProfit(
      followupNetCharge: followupNetCharge,
      billingNetCharge: billingNetCharge,
      labExpense: labExp,
      expenses: expenses,
    );

    return MonthlyReport(
      month: prefix,
      visits: visits,
      revenue: followupNetCharge + billingNetCharge,
      expenses: expenses,
      profit: profit,
    );
  }
```

Note: `MonthlyReport` has no `labExpenses` field (only `WeeklyReport` does, per the class definitions at lines 4-62) — the monthly version above correctly omits it, matching the existing class shape. Both methods now read `followups`/`billing_records` instead of `visits` — this is the fix for the wrong-table bug described above; it isn't separately unit-tested (no DB test infra exists), but is covered by `dart analyze` (Step 5) and the manual check in Task 5.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clinic_mobile_app && flutter test test/report_service_profit_test.dart`
Expected: PASS (4 passed)

- [ ] **Step 5: Run dart analyze**

Run: `cd clinic_mobile_app && dart analyze lib/services/report_service.dart`
Expected: no new warnings/errors.

- [ ] **Step 6: Commit**

```bash
git add clinic_mobile_app/lib/services/report_service.dart clinic_mobile_app/test/report_service_profit_test.dart
git commit -m "$(cat <<'EOF'
fix(mobile): offline report fallback reads the wrong local table

_localWeeklyReport/_localMonthlyReport queried the local `visits` table,
which mirrors a near-empty clinical log with no money fields -- the real
local mirror of patient_followups is the `followups` table (confirmed via
patient_service.dart's updateVisit(), which PUTs to /api/patients/<id>/
followups/<id>). In practice this meant offline profit/revenue was
computed from empty data. Also folds in billing_records, which the
offline path never touched at all, unifying with the desktop formula.
Extracted the shared formula into a pure, static, tested
ReportService.computeProfit() -- this codebase has no sqflite-backed test
infrastructure, so the DB-querying lines aren't separately unit tested.
EOF
)"
```

---

### Task 5: Full regression gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full Python suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (935 pre-existing + 7 new from Tasks 1-3 = 942), zero failures/errors.

- [ ] **Step 2: Run Flutter analyze + test**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: no issues found.

Run: `cd clinic_mobile_app && flutter test`
Expected: all pre-existing tests pass + 4 new from Task 4.

- [ ] **Step 3: Manual visual check**

Open the desktop Reports tab (any period with data) and confirm exactly one profit figure is shown ("Clinic Gross Profit"), not two.

- [ ] **Step 4: Manual mobile offline check**

The Task 4 fix (querying `followups`/`billing_records` instead of `visits`) has no automated DB-level test (see Task 4's design note). With the mobile app's internet connection disabled (airplane mode or a dev flag that forces the offline path), open the Reports screen and confirm the weekly/monthly profit figure is non-zero when there's real synced follow-up or billing data for that period — before this fix it would show 0 (or a stale/wrong number derived from the empty `visits` table) regardless of actual data.
