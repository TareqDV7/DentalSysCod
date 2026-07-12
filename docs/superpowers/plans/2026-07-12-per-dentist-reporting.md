# Per-Dentist Profit Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-dentist revenue/margin breakdown to the existing Reports tab, for whatever date range is already selected.

**Architecture:** A new `dentist_breakdown` array field added to both `/api/reports/summary` and `/api/reports/weekly` (same date-range params each already accepts), computed by grouping `patient_followups`/`billing` by `dentist_id` and merging in Python. A new table in the Reports tab UI renders it, reusing the existing render hook.

**Tech Stack:** Flask/SQLite, vanilla JS (matches the existing Reports tab).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-12-per-dentist-reporting-design.md`, all Decisions.
- **Formula (Decision 4):** per dentist, `revenue = followup_net_charge + billing_net_charge` (net-of-discount), `gross_margin = revenue - lab_expense` (their own follow-ups' lab cost only). No general-expense allocation.
- **Unassigned bucket (Decision 2):** `dentist_id IS NULL` rows get their own row, `dentist_name = 'Unassigned'`, always sorted last regardless of alphabetical order.
- **Refinement found during planning, not in the spec:** dentist names for the breakdown must be looked up from `users` **without** filtering by `is_dentist = 1`. A `dentist_id` on a historical `patient_followups`/`billing` row was valid *at the time that row was created* (the POST routes validate `is_dentist=1` then) — if that user is later un-flagged as a dentist (or deactivated), their historical work must still show under their real name, not silently fall into "Unassigned". Filtering the name lookup by `is_dentist=1` would misattribute real historical work.
- Desktop only — no mobile Reports-tab UI exists to extend (spec non-goals).
- dental_clinic.py and templates.py have both been edited many times today by earlier sub-projects — every task re-reads the current file and anchors on function/variable names, not line numbers.
- Full existing test suite (964+ tests as of 2026-07-12) must stay green throughout.

---

### Task 1: `dentist_breakdown` on `/api/reports/summary`

**Files:**
- Modify: `dental_clinic.py` — the `reports_summary()` route.
- Test: `tests/test_per_dentist_reporting.py` (new)

**Interfaces:**
- Produces: `/api/reports/summary` response gains `'dentist_breakdown': [{'dentist_id', 'dentist_name', 'revenue', 'lab_expense', 'gross_margin'}, ...]`, sorted by `dentist_name` with the `dentist_id is None` ("Unassigned") row always last.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_per_dentist_reporting.py`:

```python
"""Per-dentist revenue/margin breakdown on /api/reports/summary and
/api/reports/weekly -- see docs/superpowers/specs/2026-07-12-per-dentist-reporting-design.md.
No general-expense allocation: gross_margin = revenue - the dentist's own
lab_expense only."""
import dental_clinic
import permissions
import pytest


DATE_RANGE = ('2020-01-01', '2099-12-31')  # wide enough to include "now" at any test-run time


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'per_dentist_reporting_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient():
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _dentist(username, display_name):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 1)',
        (username, 'x', display_name),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _lab_procedure_id():
    # Mirrors tests/test_reports_gross_profit.py: lab_expense is only
    # persisted for procedures catalogued as lab-requiring.
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


def _followup(client, pid, dentist_id=None, *, price, discount=0, lab_expense=0, payment=0, date='15/06/2026'):
    payload = {
        'followup_date': date, 'treatment_procedure': 'Filling',
        'price': price, 'discount': discount, 'lab_expense': lab_expense, 'payment': payment,
    }
    if lab_expense:
        payload['procedure_id'] = _lab_procedure_id()
    if dentist_id is not None:
        payload['dentist_id'] = dentist_id
    r = client.post(f'/api/patients/{pid}/followups', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def _billing(client, pid, dentist_id=None, *, subtotal, discount=0, paid_amount=0):
    payload = {'patient_id': pid, 'subtotal': subtotal, 'discount': discount, 'paid_amount': paid_amount}
    if dentist_id is not None:
        payload['dentist_id'] = dentist_id
    r = client.post('/api/billing', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def test_summary_breakdown_has_one_row_per_dentist(client):
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    zed = _dentist('zed', 'Dr. Zed')
    _followup(client, pid, amy, price=300, discount=20, lab_expense=30, payment=250)
    _billing(client, pid, zed, subtotal=200, paid_amount=200)

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[amy]['dentist_name'] == 'Dr. Amy'
    assert breakdown[amy]['revenue'] == 280      # 300 - 20
    assert breakdown[amy]['lab_expense'] == 30
    assert breakdown[amy]['gross_margin'] == 250  # 280 - 30
    assert breakdown[zed]['dentist_name'] == 'Dr. Zed'
    assert breakdown[zed]['revenue'] == 200
    assert breakdown[zed]['gross_margin'] == 200


def test_summary_breakdown_combines_followup_and_billing_for_same_dentist(client):
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    _followup(client, pid, amy, price=100, payment=100)
    _billing(client, pid, amy, subtotal=200, paid_amount=200)

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[amy]['revenue'] == 300  # 100 + 200


def test_summary_breakdown_has_unassigned_bucket_sorted_last(client):
    pid = _patient()
    zed = _dentist('zed', 'Dr. Zed')  # alphabetically after "Unassigned" would sort... but Unassigned must be last regardless
    _followup(client, pid, zed, price=100, payment=100)
    _followup(client, pid, None, price=50, payment=50)  # no dentist_id -> unassigned (no session either)

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    names = [row['dentist_name'] for row in payload['dentist_breakdown']]
    assert names[-1] == 'Unassigned'
    unassigned = next(row for row in payload['dentist_breakdown'] if row['dentist_id'] is None)
    assert unassigned['revenue'] == 50


def test_summary_breakdown_shows_real_name_for_un_flagged_former_dentist(client):
    # Refinement found during planning: a dentist_id valid at creation time
    # must still show under their real name even if later un-flagged.
    pid = _patient()
    former = _dentist('former', 'Dr. Former')
    _followup(client, pid, former, price=100, payment=100)

    conn = dental_clinic.get_db_connection()
    conn.execute('UPDATE users SET is_dentist = 0 WHERE id = ?', (former,))
    conn.commit()
    conn.close()

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[former]['dentist_name'] == 'Dr. Former'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_per_dentist_reporting.py -k summary -v`
Expected: FAIL — `KeyError: 'dentist_breakdown'` (field doesn't exist yet).

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, find `def reports_summary():`. Immediately before `clause, params = build_date_clause('start_date', start_date, end_date)` (the `treatment_plans` count query, near the end of the function), insert:

```python
    # Per-dentist breakdown (see docs/superpowers/specs/2026-07-12-per-dentist-reporting-design.md):
    # revenue = net-of-discount charge, gross_margin = revenue - their own
    # lab_expense. No general-expense allocation -- overhead isn't any one
    # dentist's cost.
    clause, params = build_date_clause('followup_date', start_date, end_date)
    cursor.execute(f'''
        SELECT dentist_id,
               COALESCE(SUM(COALESCE(price, 0) - COALESCE(discount, 0)), 0),
               COALESCE(SUM(lab_expense), 0)
        FROM patient_followups WHERE COALESCE(is_deleted, 0) = 0{clause}
        GROUP BY dentist_id
    ''', params)
    followup_by_dentist = {row[0]: (float(row[1]), float(row[2])) for row in cursor.fetchall()}

    bclause, bparams = build_date_clause('COALESCE(payment_date, created_at)', start_date, end_date)
    cursor.execute(f'''
        SELECT dentist_id, COALESCE(SUM(COALESCE(subtotal, 0) - COALESCE(discount, 0)), 0)
        FROM billing WHERE 1 = 1{bclause}
        GROUP BY dentist_id
    ''', bparams)
    billing_by_dentist = {row[0]: float(row[1]) for row in cursor.fetchall()}

    # No is_dentist filter here: a dentist_id on a historical row was valid
    # when that row was created, even if the user is later un-flagged --
    # their real name must still show, not silently fall into "Unassigned".
    cursor.execute('SELECT id, display_name FROM users')
    dentist_names = {row[0]: row[1] for row in cursor.fetchall()}

    all_dentist_ids = set(followup_by_dentist) | set(billing_by_dentist)
    dentist_breakdown = []
    for did in all_dentist_ids:
        f_charge, f_lab = followup_by_dentist.get(did, (0.0, 0.0))
        b_charge = billing_by_dentist.get(did, 0.0)
        revenue = f_charge + b_charge
        lab_expense = f_lab
        dentist_breakdown.append({
            'dentist_id': did,
            'dentist_name': dentist_names.get(did, 'Unassigned') if did is not None else 'Unassigned',
            'revenue': revenue,
            'lab_expense': lab_expense,
            'gross_margin': revenue - lab_expense,
        })
    dentist_breakdown.sort(key=lambda d: (d['dentist_id'] is None, d['dentist_name']))

    clause, params = build_date_clause('start_date', start_date, end_date)
```

Then add `'dentist_breakdown': dentist_breakdown,` to the final `jsonify({...})` block, right after `'clinic_gross_profit': float(clinic_gross_profit or 0),`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_per_dentist_reporting.py -k summary -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_per_dentist_reporting.py
git commit -m "feat(per-dentist-reporting): add dentist_breakdown to /api/reports/summary"
```

---

### Task 2: `dentist_breakdown` on `/api/reports/weekly`

**Files:**
- Modify: `dental_clinic.py` — the `reports_weekly()` route.
- Test: extend `tests/test_per_dentist_reporting.py`

**Interfaces:**
- Same as Task 1, for `/api/reports/weekly`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_per_dentist_reporting.py`:

```python
import datetime


def _monday_of_this_week():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def test_weekly_breakdown_has_one_row_per_dentist(client):
    monday = _monday_of_this_week()
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    _billing(client, pid, amy, subtotal=200, paid_amount=200)  # created_at = now, falls in this week

    payload = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[amy]['revenue'] == 200
    assert breakdown[amy]['gross_margin'] == 200


def test_weekly_breakdown_combines_followup_and_billing(client):
    monday = _monday_of_this_week()
    followup_date = monday + datetime.timedelta(days=2)
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    _followup(client, pid, amy, price=300, discount=20, lab_expense=30, payment=250,
              date=followup_date.strftime('%d/%m/%Y'))
    _billing(client, pid, amy, subtotal=200, paid_amount=200)

    payload = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    # followup: 300-20=280, minus lab 30 -> margin 250. billing: 200, margin 200. combined revenue 480, margin 450.
    assert breakdown[amy]['revenue'] == 480
    assert breakdown[amy]['gross_margin'] == 450


def test_weekly_breakdown_unassigned_sorted_last(client):
    monday = _monday_of_this_week()
    followup_date = monday + datetime.timedelta(days=1)
    pid = _patient()
    zed = _dentist('zed', 'Dr. Zed')
    _followup(client, pid, zed, price=100, payment=100, date=followup_date.strftime('%d/%m/%Y'))
    _followup(client, pid, None, price=50, payment=50, date=followup_date.strftime('%d/%m/%Y'))

    payload = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()
    names = [row['dentist_name'] for row in payload['dentist_breakdown']]
    assert names[-1] == 'Unassigned'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_per_dentist_reporting.py -k weekly -v`
Expected: FAIL — `KeyError: 'dentist_breakdown'`.

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, find `def reports_weekly():`. Immediately before `cursor.execute('SELECT COUNT(*) FROM treatment_plans WHERE date(start_date) BETWEEN ? AND ?', (start_str, end_str))`, insert:

```python
    # Per-dentist breakdown -- see reports_summary()'s identical comment/rationale.
    cursor.execute('''
        SELECT dentist_id,
               COALESCE(SUM(COALESCE(price, 0) - COALESCE(discount, 0)), 0),
               COALESCE(SUM(lab_expense), 0)
        FROM patient_followups
        WHERE COALESCE(is_deleted, 0) = 0 AND date(followup_date) BETWEEN ? AND ?
        GROUP BY dentist_id
    ''', (start_str, end_str))
    followup_by_dentist = {row[0]: (float(row[1]), float(row[2])) for row in cursor.fetchall()}

    cursor.execute('''
        SELECT dentist_id, COALESCE(SUM(COALESCE(subtotal, 0) - COALESCE(discount, 0)), 0)
        FROM billing WHERE date(COALESCE(payment_date, created_at)) BETWEEN ? AND ?
        GROUP BY dentist_id
    ''', (start_str, end_str))
    billing_by_dentist = {row[0]: float(row[1]) for row in cursor.fetchall()}

    cursor.execute('SELECT id, display_name FROM users')
    dentist_names = {row[0]: row[1] for row in cursor.fetchall()}

    all_dentist_ids = set(followup_by_dentist) | set(billing_by_dentist)
    dentist_breakdown = []
    for did in all_dentist_ids:
        f_charge, f_lab = followup_by_dentist.get(did, (0.0, 0.0))
        b_charge = billing_by_dentist.get(did, 0.0)
        revenue = f_charge + b_charge
        lab_expense = f_lab
        dentist_breakdown.append({
            'dentist_id': did,
            'dentist_name': dentist_names.get(did, 'Unassigned') if did is not None else 'Unassigned',
            'revenue': revenue,
            'lab_expense': lab_expense,
            'gross_margin': revenue - lab_expense,
        })
    dentist_breakdown.sort(key=lambda d: (d['dentist_id'] is None, d['dentist_name']))

    cursor.execute('SELECT COUNT(*) FROM treatment_plans WHERE date(start_date) BETWEEN ? AND ?', (start_str, end_str))
```

Then add `'dentist_breakdown': dentist_breakdown,` to the final `jsonify({...})` block, right after `'clinic_gross_profit': float(clinic_gross_profit or 0),`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_per_dentist_reporting.py -v`
Expected: PASS (7 passed total across Tasks 1-2)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_per_dentist_reporting.py
git commit -m "feat(per-dentist-reporting): add dentist_breakdown to /api/reports/weekly"
```

---

### Task 3: Reports tab UI — per-dentist breakdown table

**Files:**
- Modify: `templates.py` — the Reports tab HTML (Finance stat-grid area) and `renderReportStats()`.
- Test: `tests/test_per_dentist_reporting_ui.py` (new)

**Interfaces:**
- Consumes: `dentist_breakdown` field from Task 1/2's API responses.

- [ ] **Step 1: Write the failing test**

Create `tests/test_per_dentist_reporting_ui.py`:

```python
"""Reports tab shows a per-dentist breakdown table below the existing
Finance stat-grid. Presence-check style, matching tests/test_reports_ui.py."""
from templates import HTML_TEMPLATE


def test_dentist_breakdown_table_present():
    assert 'id="report-dentist-breakdown-body"' in HTML_TEMPLATE


def test_render_report_stats_paints_dentist_breakdown():
    assert 'dentist_breakdown' in HTML_TEMPLATE
    assert 'function renderReportStats(data)' in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_per_dentist_reporting_ui.py -v`
Expected: FAIL — neither string exists yet.

- [ ] **Step 3: Add the table markup**

In `templates.py`, find the Finance stats-grid's closing `</div>` (search for `<div class="stat-card"><h3 id="report-expenses">₪ 0</h3><p data-i18n="expenses">Expenses</p></div>` — the last stat-card in that grid, immediately followed by `</div>`). Insert this new block right after that `</div>`:

```html
                <h3 style="margin-top:20px;" data-i18n="dentist_breakdown_title">By Dentist</h3>
                <div class="table-container">
                    <table>
                        <thead><tr>
                            <th data-i18n="dentist">Dentist</th>
                            <th data-i18n="revenue">Revenue</th>
                            <th data-i18n="lab_expense">Lab Expense</th>
                            <th data-i18n="gross_margin">Gross Margin</th>
                        </tr></thead>
                        <tbody id="report-dentist-breakdown-body"><tr><td colspan="4" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
```

- [ ] **Step 4: Wire the render function**

In `templates.py`, find `function renderReportStats(data) {` and add this line right before its closing `}`:

```javascript
            renderDentistBreakdownTable(data.dentist_breakdown || []);
```

Immediately after `renderReportStats`'s closing `}`, add the new render function:

```javascript

        function renderDentistBreakdownTable(rows) {
            const tbody = document.getElementById('report-dentist-breakdown-body');
            if (!tbody) return;
            const money = (v) => '₪ ' + parseCurrency(v).toFixed(2);
            if (!Array.isArray(rows) || !rows.length) {
                tbody.innerHTML = `<tr><td colspan="4">${t('no_data', 'No data')}</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(row => `
                <tr>
                    <td>${escapeHtml(row.dentist_name || '')}</td>
                    <td>${money(row.revenue)}</td>
                    <td>${money(row.lab_expense)}</td>
                    <td>${money(row.gross_margin)}</td>
                </tr>
            `).join('');
        }
```

Add the new EN i18n keys (verified during planning: `revenue`/`lab_expense` keys **already exist** in the EN/AR dicts, used by the existing `report-revenue`/`report-lab-expenses` stat cards — do not add them again, that would create a duplicate key that silently shadows the original in this codebase's single flat i18n object). Find the EN dict's `unassigned:` entry (added earlier today by the multi-dentist-attribution work) and add right after it:
```javascript
                dentist_breakdown_title: 'By Dentist',
                gross_margin: 'Gross Margin',
```

Add the matching AR keys right after the AR `unassigned:` entry:
```javascript
                dentist_breakdown_title: 'حسب الطبيب',
                gross_margin: 'هامش الربح',
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_per_dentist_reporting_ui.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_per_dentist_reporting_ui.py
git commit -m "feat(per-dentist-reporting): add By Dentist table to Reports tab"
```

---

### Task 4: Full regression gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full Python suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (964 pre-existing + 9 new from Tasks 1-3 = 973), zero failures/errors.

- [ ] **Step 2: Manual visual check**

Open the desktop Reports tab (any period with mixed follow-up/billing data across a couple of dentists), confirm the "By Dentist" table appears below the existing Finance stat-grid with correct revenue/lab expense/margin figures, and that an "Unassigned" row appears last when there's unattributed work.
