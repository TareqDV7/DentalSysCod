# Multi-Dentist Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tag which dentist did each appointment/follow-up/billing entry — data-tagging only, no scheduling, no reporting UI yet.

**Architecture:** Additive `dentist_id` column on `appointments`/`patient_followups`/`billing` (desktop) and their local mirrors (mobile), plus `is_dentist` on `users`. A new open `GET /api/dentists` lookup feeds both the desktop dropdowns and mobile's picker (mobile has no session to gate behind anyway). Desktop POST routes auto-fill from the session user when they're a dentist; mobile always shows a manual picker.

**Tech Stack:** Flask/SQLite (desktop), Dart/sqflite (mobile).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-12-multi-dentist-attribution-design.md`, all Decisions.
- **Refinement over the spec, decided during planning:** the spec says desktop auto-fills `dentist_id` from `session.get('uid')`. That session user might not be a dentist at all (e.g. front-desk staff creating a billing entry) — in that case auto-fill must leave `dentist_id` as `NULL` (unassigned), never store a non-dentist's id. Validation only ever runs against an **explicitly-provided** `dentist_id` (reject if that user isn't `is_dentist=1` and active); the auto-fill path silently no-ops instead of rejecting the whole request.
- `dentist_id` is nullable everywhere — no backfill, existing records stay unattributed.
- Reuses the existing `ensure_table_column(cursor, table, column, type)` helper (`dental_clinic.py:581`) for all new desktop columns — the same pattern already used for `users.must_change_password` (`dental_clinic.py:1348`) and every other additive column in this codebase.
- Mobile: reuses the existing `_addColumnIfMissing(db, table, column, type)` helper (`database_service.dart:195`) inside a new `if (oldVersion < 10)` migration block, and bumps `version: 9` → `version: 10` (`database_service.dart:28`).
- `GET /api/dentists` is intentionally **not** added to `_AUTH_REQUIRED_EXACT`/`_PERMISSION_RULES` — it must stay reachable the same way `/api/patients` and other mobile-consumed lookups already are (mobile has no session to gate behind at all; see spec Decision 4/Context).
- Full existing test suite (942+ tests as of 2026-07-12) must stay green throughout. `flutter analyze` clean, `flutter test` green throughout.
- dental_clinic.py has been edited multiple times today already (recall/reminder + gross-profit work) — every task below re-reads the current file and anchors on function/variable names, not the line numbers cited (cited line numbers were correct at planning time but WILL drift task-to-task).

---

### Task 1: Schema — `users.is_dentist`, `dentist_id` on the three tables, `GET /api/dentists`

**Files:**
- Modify: `dental_clinic.py` — `users`/`appointments`/`patient_followups`/`billing` CREATE TABLE statements (fresh-install path) + the `ensure_table_column` block (upgrade path) + a new route.
- Test: `tests/test_multi_dentist_schema.py` (new)

**Interfaces:**
- Produces: `users.is_dentist` column, `dentist_id` column on `appointments`/`patient_followups`/`billing`, `GET /api/dentists` → `[{"id": int, "display_name": str}, ...]` (only `is_dentist=1 AND is_active=1`, ordered by `display_name`).
- Consumed by: Tasks 2-4 (route logic), Task 6 (dropdown UI).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multi_dentist_schema.py`:

```python
"""users.is_dentist + dentist_id on appointments/patient_followups/billing,
and the GET /api/dentists lookup that feeds both the desktop dropdowns and
mobile's picker (mobile has no session, so this endpoint stays unauthenticated
like /api/patients already is)."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_schema_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _make_user(is_dentist=1, is_active=1, username='drtest', display_name='Dr. Test'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_active, is_dentist) '
        'VALUES (?, ?, ?, ?, ?)',
        (username, 'x', display_name, is_active, is_dentist),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def test_schema_has_dentist_id_columns(client):
    conn = dental_clinic.get_db_connection()
    for table in ('appointments', 'patient_followups', 'billing'):
        cols = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        assert 'dentist_id' in cols, table
    user_cols = {row[1] for row in conn.execute('PRAGMA table_info(users)')}
    assert 'is_dentist' in user_cols
    conn.close()


def test_get_dentists_lists_only_active_dentists(client):
    d1 = _make_user(is_dentist=1, is_active=1, username='d1', display_name='Dr. Amy')
    _make_user(is_dentist=0, is_active=1, username='front_desk', display_name='Front Desk')
    _make_user(is_dentist=1, is_active=0, username='d_inactive', display_name='Dr. Gone')

    resp = client.get('/api/dentists')
    assert resp.status_code == 200
    rows = resp.get_json()
    assert [r['id'] for r in rows] == [d1]
    assert rows[0]['display_name'] == 'Dr. Amy'


def test_get_dentists_ordered_by_display_name(client):
    _make_user(username='d2', display_name='Dr. Zed')
    _make_user(username='d3', display_name='Dr. Amy')

    resp = client.get('/api/dentists')
    names = [r['display_name'] for r in resp.get_json()]
    assert names == sorted(names)


def test_get_dentists_requires_no_session(client):
    # Mobile has no session at all -- this must be reachable without login,
    # matching /api/patients' existing open posture.
    resp = client.get('/api/dentists')
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multi_dentist_schema.py -v`
Expected: FAIL — `sqlite3.OperationalError: table users has no column named is_dentist` (or 404 for `/api/dentists`).

- [ ] **Step 3: Add the schema + route**

In `dental_clinic.py`, find the `users` CREATE TABLE (search for `CREATE TABLE IF NOT EXISTS users (`) and add a column to its literal, right after `is_active INTEGER DEFAULT 1,`:
```python
            is_dentist INTEGER DEFAULT 0,
```

Find the `appointments` CREATE TABLE (search `CREATE TABLE IF NOT EXISTS appointments (`) and add, right before the closing `FOREIGN KEY (patient_id) REFERENCES patients (id)` line:
```python
            dentist_id INTEGER,
```

Find `patient_followups` CREATE TABLE similarly and add the same `dentist_id INTEGER,` line before its `FOREIGN KEY` lines.

Find `billing` CREATE TABLE similarly and add the same `dentist_id INTEGER,` line before its `FOREIGN KEY` lines.

Find the block of `ensure_table_column(cursor, ...)` calls (search for `ensure_table_column(cursor, 'billing', 'updated_at'` to locate it — that's the most recently-added call in this block as of today) and add, right after it:
```python
    ensure_table_column(cursor, 'users', 'is_dentist', 'INTEGER DEFAULT 0')
    ensure_table_column(cursor, 'appointments', 'dentist_id', 'INTEGER')
    ensure_table_column(cursor, 'patient_followups', 'dentist_id', 'INTEGER')
    ensure_table_column(cursor, 'billing', 'dentist_id', 'INTEGER')
```

Add the new route. Find `@app.route('/api/staff', methods=['GET', 'POST'])` and insert this new route immediately before it:

```python
@app.route('/api/dentists')
def list_dentists():
    conn = get_db_connection(with_row_factory=True)
    rows = conn.execute(
        'SELECT id, display_name FROM users WHERE is_dentist = 1 AND is_active = 1 '
        'ORDER BY display_name'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multi_dentist_schema.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_multi_dentist_schema.py
git commit -m "feat(multi-dentist): add is_dentist flag, dentist_id columns, GET /api/dentists"
```

---

### Task 2: Appointments — auto-fill/validate `dentist_id`, expose it in GET

**Files:**
- Modify: `dental_clinic.py` — the `appointments()` POST route and `appointment_row_to_dict()`.
- Test: `tests/test_multi_dentist_appointments.py` (new)

**Interfaces:**
- Consumes: `users.is_dentist` (Task 1).
- Produces: `appointment_row_to_dict()` now includes `dentist_id` in its returned dict.

**Design note — `appointment_row_to_dict()` has a fragile dual code path** (search for `def appointment_row_to_dict`): a named-access branch (`row['id']`, used when the caller passed `with_row_factory=True`) and a **positional** branch (`row[0]`, `row[1]`, ...) used by the `appointments()` GET route specifically, which calls `get_db_connection()` **without** `with_row_factory=True`. The positional branch already relies on `row[-1]` always being `patient_name` (the JOIN always appends it last, regardless of how many `appointments` columns precede it) and `row[7] if len(row) > 7` for `created_at`. Since `dentist_id` is appended via `ALTER TABLE` (so it becomes the *last* column of `appointments` itself, after `updated_at`), it will land at `row[-2]` in the `SELECT a.*, p.first_name...` result — the second-to-last element, immediately before the always-last `patient_name`. This holds regardless of how many other `appointments` columns exist, exactly like the existing `row[-1]` trick for `patient_name`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multi_dentist_appointments.py`:

```python
"""dentist_id on appointments: auto-fills from the session user when they're
a dentist, leaves it unset otherwise, is overridable, and round-trips through
both GET code paths (get_db_connection() with and without with_row_factory)."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_appt_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(client=None):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _dentist(username='dr1', display_name='Dr. One'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 1)',
        (username, 'x', display_name),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def _front_desk(username='fd1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 0)',
        (username, 'x', 'Front Desk'),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def test_post_auto_fills_dentist_id_from_dentist_session(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-01 10:00:00',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == dentist_id


def test_post_leaves_dentist_id_unset_for_non_dentist_session(client):
    pid = _patient()
    fd_id = _front_desk()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-02 10:00:00',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] is None


def test_post_accepts_explicit_dentist_id_override(client):
    pid = _patient()
    fd_id = _front_desk()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-03 10:00:00', 'dentist_id': dentist_id,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == dentist_id


def test_post_rejects_explicit_non_dentist_id(client):
    pid = _patient()
    fd_id = _front_desk()
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-04 10:00:00', 'dentist_id': fd_id,
    })
    assert r.status_code == 400


def test_get_appointments_includes_dentist_id(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-05 10:00:00',
    })
    rows = client.get('/api/appointments').get_json()
    assert rows[0]['dentist_id'] == dentist_id


def test_post_empty_string_dentist_id_treated_as_unset(client):
    # The desktop form always submits dentist_id (via FormData), so an
    # "Unassigned" selection arrives as '' not a missing key -- this must
    # fall through to the same auto-fill path as omitting the field
    # entirely, not be treated as an invalid explicit value.
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-08-06 10:00:00', 'dentist_id': '',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['dentist_id'] == dentist_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multi_dentist_appointments.py -v`
Expected: FAIL — `KeyError: 'dentist_id'` (route doesn't set/return it yet).

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, find the `appointments()` function's POST branch (search `def appointments():`). Immediately before the conflict-check block (search for `cursor.execute('''\n            SELECT a.id, a.appointment_date, a.duration,` to find the conflict query), insert:

```python
        dentist_id = data.get('dentist_id')
        if dentist_id not in (None, ''):
            try:
                dentist_id = int(dentist_id)
            except (TypeError, ValueError):
                conn.close()
                return jsonify({'error': 'Invalid dentist_id'}), 400
            cursor.execute('SELECT 1 FROM users WHERE id = ? AND is_dentist = 1 AND is_active = 1', (dentist_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({'error': 'dentist_id must refer to an active dentist'}), 400
        else:
            dentist_id = None
            uid = session.get('uid')
            if uid:
                cursor.execute('SELECT 1 FROM users WHERE id = ? AND is_dentist = 1 AND is_active = 1', (uid,))
                if cursor.fetchone():
                    dentist_id = uid

```

Then change the `INSERT INTO appointments` statement from:
```python
        cursor.execute('''
            INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (patient_id, appointment_date, duration,
              data.get('treatment_type'), status, data.get('notes')))
```
to:
```python
        cursor.execute('''
            INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, status, notes, dentist_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (patient_id, appointment_date, duration,
              data.get('treatment_type'), status, data.get('notes'), dentist_id))
```

Now fix `appointment_row_to_dict()` (search `def appointment_row_to_dict`). In the named-access branch, add after `patient_name_raw = row['patient_name'] if 'patient_name' in row.keys() else ''`:
```python
        dentist_id = row['dentist_id'] if 'dentist_id' in row.keys() else None
```
In the positional branch, add after `patient_name_raw = row[-1] if len(row) > 8 else ''`:
```python
        dentist_id = row[-2] if len(row) > 9 else None
```
And in the returned dict literal, add a new key:
```python
        'dentist_id': dentist_id,
```
(right after `'created_at': created_at,`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multi_dentist_appointments.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_multi_dentist_appointments.py
git commit -m "feat(multi-dentist): attribute appointments to a dentist"
```

---

### Task 3: Follow-ups — auto-fill/validate `dentist_id`

**Files:**
- Modify: `dental_clinic.py` — the `patient_followups()` POST route (`/api/patients/<int:patient_id>/followups`).
- Test: `tests/test_multi_dentist_followups.py` (new)

**Interfaces:**
- Consumes: `users.is_dentist` (Task 1).
- Produces: nothing new consumed by later tasks — the GET path already returns `dentist_id` automatically via `dict(row)` (no code change needed there, only a test).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multi_dentist_followups.py`:

```python
"""dentist_id on patient_followups -- same auto-fill/override/reject rules as
appointments (Task 2). GET needs no code change: patient_followups() already
returns `dict(row)` from a with_row_factory=True cursor, so a new column
appears automatically -- this file just proves that."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_followup_test.db'
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


def _dentist(username='dr1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, 'x', 'Dr. One', 1)",
        (username,),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def _front_desk(username='fd1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, 'x', 'Front Desk', 0)",
        (username,),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def _followup(client, pid, **overrides):
    payload = {'followup_date': '15/06/2026', 'treatment_procedure': 'Filling', 'price': 100}
    payload.update(overrides)
    return client.post(f'/api/patients/{pid}/followups', json=payload)


def test_post_auto_fills_from_dentist_session(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = _followup(client, pid)
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['dentist_id'] == dentist_id


def test_post_leaves_unset_for_non_dentist_session(client):
    pid = _patient()
    fd_id = _front_desk()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    _followup(client, pid)
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['dentist_id'] is None


def test_post_rejects_explicit_non_dentist_id(client):
    pid = _patient()
    fd_id = _front_desk()
    r = _followup(client, pid, dentist_id=fd_id)
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multi_dentist_followups.py -v`
Expected: FAIL — `dentist_id` is `None`/absent regardless of who's logged in (not wired up yet); the reject test gets 200 instead of 400.

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, find `def patient_followups(patient_id):`. Immediately before `# Parse followup date to ensure YYYY-MM-DD format` (search for that exact comment), insert:

```python
    dentist_id = data.get('dentist_id')
    if dentist_id not in (None, ''):
        try:
            dentist_id = int(dentist_id)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Invalid dentist_id'}), 400
        cursor.execute('SELECT 1 FROM users WHERE id = ? AND is_dentist = 1 AND is_active = 1', (dentist_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'dentist_id must refer to an active dentist'}), 400
    else:
        dentist_id = None
        uid = session.get('uid')
        if uid:
            cursor.execute('SELECT 1 FROM users WHERE id = ? AND is_dentist = 1 AND is_active = 1', (uid,))
            if cursor.fetchone():
                dentist_id = uid

```

Then change the `INSERT INTO patient_followups` statement from:
```python
    cursor.execute('''
        INSERT INTO patient_followups (
            patient_id, followup_date, tooth_no, diagnosis, treatment_procedure, procedure_id,
            price, discount, lab_expense, clinic_profit, payment, remaining_amount, notes,
            price_expr, discount_expr, lab_expense_expr, payment_expr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        patient_id,
        parsed_followup_date,
        data.get('tooth_no'),
        data.get('diagnosis'),
        treatment_procedure,
        procedure_id,
        price,
        discount,
        lab_expense,
        clinic_profit,
        payment,
        remaining_amount,
        data.get('notes'),
        price_expr,
        discount_expr,
        lab_expense_expr,
        payment_expr
    ))
```
to:
```python
    cursor.execute('''
        INSERT INTO patient_followups (
            patient_id, followup_date, tooth_no, diagnosis, treatment_procedure, procedure_id,
            price, discount, lab_expense, clinic_profit, payment, remaining_amount, notes,
            price_expr, discount_expr, lab_expense_expr, payment_expr, dentist_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        patient_id,
        parsed_followup_date,
        data.get('tooth_no'),
        data.get('diagnosis'),
        treatment_procedure,
        procedure_id,
        price,
        discount,
        lab_expense,
        clinic_profit,
        payment,
        remaining_amount,
        data.get('notes'),
        price_expr,
        discount_expr,
        lab_expense_expr,
        payment_expr,
        dentist_id
    ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multi_dentist_followups.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_multi_dentist_followups.py
git commit -m "feat(multi-dentist): attribute follow-ups to a dentist"
```

---

### Task 4: Billing — auto-fill/validate `dentist_id`, expose it in GET

**Files:**
- Modify: `dental_clinic.py` — the `billing()` POST route and its GET response dict builder.
- Test: `tests/test_multi_dentist_billing.py` (new)

**Interfaces:**
- Consumes: `users.is_dentist` (Task 1).
- Produces: `billing()` GET's per-row dict now includes `dentist_id`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multi_dentist_billing.py`:

```python
"""dentist_id on billing -- same auto-fill/override/reject rules as
appointments/follow-ups. billing()'s GET builds an explicit dict per row
(not dict(row)), so it needs its own added key -- unlike follow-ups."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_billing_test.db'
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


def _dentist(username='dr1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, 'x', 'Dr. One', 1)",
        (username,),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def _front_desk(username='fd1'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, 'x', 'Front Desk', 0)",
        (username,),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def test_post_auto_fills_from_dentist_session(client):
    pid = _patient()
    dentist_id = _dentist()
    with client.session_transaction() as sess:
        sess['uid'] = dentist_id
    r = client.post('/api/billing', json={'patient_id': pid, 'subtotal': 100, 'paid_amount': 100})
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get('/api/billing').get_json()
    assert rows[0]['dentist_id'] == dentist_id


def test_post_leaves_unset_for_non_dentist_session(client):
    pid = _patient()
    fd_id = _front_desk()
    with client.session_transaction() as sess:
        sess['uid'] = fd_id
    client.post('/api/billing', json={'patient_id': pid, 'subtotal': 100, 'paid_amount': 100})
    rows = client.get('/api/billing').get_json()
    assert rows[0]['dentist_id'] is None


def test_post_rejects_explicit_non_dentist_id(client):
    pid = _patient()
    fd_id = _front_desk()
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 100, 'paid_amount': 100, 'dentist_id': fd_id,
    })
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multi_dentist_billing.py -v`
Expected: FAIL — `dentist_id` missing/`None` regardless of session; reject test gets 200.

- [ ] **Step 3: Fix the implementation**

In `dental_clinic.py`, find `def billing():`. In the GET branch, add a new key to the per-row dict (search for `'patient_name': row_data.get('patient_name')` — the last key in that dict):
```python
                'patient_name': row_data.get('patient_name'),
                'dentist_id': row_data.get('dentist_id'),
```

In the POST branch, immediately before `invoice_number = data.get('invoice_number') or generate_invoice_number()`, insert:
```python
        dentist_id = data.get('dentist_id')
        if dentist_id not in (None, ''):
            try:
                dentist_id = int(dentist_id)
            except (TypeError, ValueError):
                conn.close()
                return jsonify({'error': 'Invalid dentist_id'}), 400
            cursor.execute('SELECT 1 FROM users WHERE id = ? AND is_dentist = 1 AND is_active = 1', (dentist_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({'error': 'dentist_id must refer to an active dentist'}), 400
        else:
            dentist_id = None
            uid = session.get('uid')
            if uid:
                cursor.execute('SELECT 1 FROM users WHERE id = ? AND is_dentist = 1 AND is_active = 1', (uid,))
                if cursor.fetchone():
                    dentist_id = uid

```

Then change the `INSERT INTO billing` statement from:
```python
        cursor.execute('''
            INSERT INTO billing (
                patient_id, treatment_id, invoice_number, amount,
                subtotal, discount, paid_amount, credit_used, balance_due,
                payment_method, payment_status, payment_date,
                subtotal_expr, discount_expr, paid_amount_expr
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['patient_id'],
            data.get('treatment_id'),
            invoice_number,
```
to (adding `dentist_id` to both the column list/placeholder count and the params — re-read the full statement in the current file first, since it continues past what's shown here, and append `dentist_id` as the last column/placeholder/param without disturbing the existing ones):
```python
        cursor.execute('''
            INSERT INTO billing (
                patient_id, treatment_id, invoice_number, amount,
                subtotal, discount, paid_amount, credit_used, balance_due,
                payment_method, payment_status, payment_date,
                subtotal_expr, discount_expr, paid_amount_expr, dentist_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['patient_id'],
            data.get('treatment_id'),
            invoice_number,
```
(the remaining params tuple entries — `total_amount, settled, balance_due, payment_method, payment_status, payment_date, subtotal_expr, discount_expr, paid_amount_expr` — stay exactly as they are today; just append `dentist_id` as the final tuple element to match the new final placeholder.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_multi_dentist_billing.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_multi_dentist_billing.py
git commit -m "feat(multi-dentist): attribute billing entries to a dentist"
```

---

### Task 5: Manage Staff UI — "Is dentist" checkbox

**Files:**
- Modify: `dental_clinic.py` — `staff_accounts()` (GET/POST) and `staff_account_update()` routes.
- Modify: `templates.py` — the Manage Staff add/edit UI.
- Test: `tests/test_multi_dentist_staff_ui.py` (new)

**Interfaces:**
- Consumes: `users.is_dentist` (Task 1).
- Produces: `is_dentist` settable via `POST /api/staff` (create) and `PUT /api/staff/<id>` (update); surfaced in `GET /api/staff`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multi_dentist_staff_ui.py`:

```python
"""Manage Staff: is_dentist is settable at account creation and via update,
and shows up in the account list. Mirrors the existing is_active handling in
staff_account_update()'s sets/vals pattern."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_staffui_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _login_as_admin(client):
    conn = dental_clinic.get_db_connection()
    uid = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    conn.close()
    with client.session_transaction() as sess:
        sess['uid'] = uid


def test_create_staff_with_is_dentist_true(client):
    r = client.post('/api/staff', json={
        'username': 'dr2', 'password': 'pw123456', 'display_name': 'Dr. Two', 'is_dentist': True,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get('/api/staff').get_json()
    dr2 = next(u for u in rows if u['username'] == 'dr2')
    assert dr2['is_dentist'] == 1


def test_create_staff_defaults_is_dentist_false(client):
    client.post('/api/staff', json={'username': 'fd2', 'password': 'pw123456'})
    rows = client.get('/api/staff').get_json()
    fd2 = next(u for u in rows if u['username'] == 'fd2')
    assert fd2['is_dentist'] == 0


def test_update_staff_toggles_is_dentist(client):
    client.post('/api/staff', json={'username': 'dr3', 'password': 'pw123456'})
    rows = client.get('/api/staff').get_json()
    dr3_id = next(u for u in rows if u['username'] == 'dr3')['id']

    r = client.put(f'/api/staff/{dr3_id}', json={'is_dentist': True})
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get('/api/staff').get_json()
    assert next(u for u in rows if u['id'] == dr3_id)['is_dentist'] == 1


def test_reminders_panel_markup_unaffected():
    # Regression guard: templates.py must still parse/import cleanly.
    from templates import HTML_TEMPLATE
    assert 'id="staff-accounts-body"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multi_dentist_staff_ui.py -v`
Expected: FAIL — `is_dentist` key missing from `GET /api/staff` rows; PUT doesn't accept it.

- [ ] **Step 3: Fix the backend**

In `dental_clinic.py`, find `def staff_accounts():`. Change the GET query from:
```python
        rows = cursor.execute(
            'SELECT id, username, display_name, is_active, created_at, last_login_at FROM users '
            'ORDER BY username'
        ).fetchall()
```
to:
```python
        rows = cursor.execute(
            'SELECT id, username, display_name, is_active, is_dentist, created_at, last_login_at FROM users '
            'ORDER BY username'
        ).fetchall()
```

In the POST branch, change:
```python
    cursor.execute(
        'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
        (username, hash_password(password), data.get('display_name') or username))
```
to:
```python
    cursor.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, ?)',
        (username, hash_password(password), data.get('display_name') or username,
         1 if data.get('is_dentist') else 0))
```

In `staff_account_update()`, add a branch to the `sets`/`vals` block — change:
```python
    if 'display_name' in data:
        sets.append('display_name = ?'); vals.append(data['display_name'])
    if not sets:
```
to:
```python
    if 'display_name' in data:
        sets.append('display_name = ?'); vals.append(data['display_name'])
    if 'is_dentist' in data:
        sets.append('is_dentist = ?'); vals.append(1 if data['is_dentist'] else 0)
    if not sets:
```

- [ ] **Step 4: Add the UI checkbox**

In `templates.py`, find the Manage Staff "Add Staff" modal (search for `id="staff-add-display-name"` to locate the form) and add a checkbox right after that display-name field's `</div>`:
```html
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="staff-add-is-dentist">
                            <span data-i18n="staff_is_dentist">Is dentist</span>
                        </label>
                    </div>
```

Find `async function openAddStaffModal()` and add a reset line, right after `document.getElementById('staff-add-display-name').value = '';`:
```javascript
            document.getElementById('staff-add-is-dentist').checked = false;
```

Find `async function saveNewStaff(event)` and add the field to the payload — change:
```javascript
                body: JSON.stringify({ username, password, display_name: displayName || username, permissions: checked })
```
to:
```javascript
                body: JSON.stringify({
                    username, password, display_name: displayName || username, permissions: checked,
                    is_dentist: document.getElementById('staff-add-is-dentist').checked
                })
```

Find `renderStaffAccountsTable()` and add an "Is dentist" toggle button next to the existing activate/deactivate button — change the actions-cell `<div>` from:
```javascript
                            <div style="display:flex;gap:6px;flex-wrap:wrap;">
                                <button class="btn btn-primary" type="button" onclick="openStaffPermissionsModal(${u.id})">${t('edit_permissions', 'Edit Permissions')}</button>
                                <button class="btn ${toggleClass}" type="button" onclick="toggleStaffActive(${u.id}, ${!isActive})">${toggleLabel}</button>
                            </div>
```
to:
```javascript
                            <div style="display:flex;gap:6px;flex-wrap:wrap;">
                                <button class="btn btn-primary" type="button" onclick="openStaffPermissionsModal(${u.id})">${t('edit_permissions', 'Edit Permissions')}</button>
                                <button class="btn ${toggleClass}" type="button" onclick="toggleStaffActive(${u.id}, ${!isActive})">${toggleLabel}</button>
                                <button class="btn btn-secondary" type="button" onclick="toggleStaffIsDentist(${u.id}, ${parseInt(u.is_dentist, 10) !== 1})">${parseInt(u.is_dentist, 10) === 1 ? t('unmark_dentist', 'Unmark dentist') : t('mark_dentist', 'Mark as dentist')}</button>
                            </div>
```

Add a new JS function right after `toggleStaffActive` (search for `async function toggleStaffActive` to find it and place this immediately after its closing `}`):
```javascript
        async function toggleStaffIsDentist(userId, makeDentist) {
            try {
                const res = await fetch(`/api/staff/${userId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_dentist: makeDentist })
                });
                if (!res.ok) throw new Error(res.status);
                await loadStaffAccounts();
            } catch (_) {
                showToast(t('unable_save_staff', 'Unable to save staff account.'), 'error');
            }
        }
```

Add i18n strings: find the EN i18n dict's `staff_saved:` entry (search `staff_saved: 'Staff account saved.'`) and add right after it:
```javascript
                staff_is_dentist: 'Is dentist',
                mark_dentist: 'Mark as dentist',
                unmark_dentist: 'Unmark dentist',
```
Find the matching AR entry (search for the Arabic translation of `staff_saved`, same key) and add:
```javascript
                staff_is_dentist: 'طبيب',
                mark_dentist: 'تعيين كطبيب',
                unmark_dentist: 'إلغاء تعيين كطبيب',
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_multi_dentist_staff_ui.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py templates.py tests/test_multi_dentist_staff_ui.py
git commit -m "feat(multi-dentist): Is-dentist toggle on Manage Staff"
```

---

### Task 6: Dentist dropdown on appointment/follow-up/billing forms (desktop)

**Files:**
- Modify: `templates.py` — `dentistsCache` + `loadDentists()`/`populateDentistSelect()` helpers, the appointment form (`add-appointment-form`, static HTML), the billing form (`billing-form`, static HTML), the follow-up entry form (`patient-followup-form`, a JS template literal built inside `viewPatientProfile`).
- Test: `tests/test_multi_dentist_forms_ui.py` (new)

**Interfaces:**
- Consumes: `GET /api/dentists` (Task 1).

**Verified during planning (all three forms use `Object.fromEntries(new FormData(form))` to build their POST body — `templates.py:9181` for appointments, `templates.py:9294` for billing, `templates.py:8606` for follow-ups): a `<select name="dentist_id">` placed inside any of the three `<form>` elements is picked up automatically. No save-function JS changes are needed — only adding the `<select>` itself and keeping it populated.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_multi_dentist_forms_ui.py`:

```python
"""A shared dentistsCache/loadDentists() exists and each of the three forms
has a name="dentist_id" select -- FormData auto-includes it in the POST body,
so no save-function changes are needed, only presence of the field. Mirrors
tests/test_reports_ui.py's presence-check style."""
from templates import HTML_TEMPLATE


def test_load_dentists_helper_present():
    assert 'async function loadDentists()' in HTML_TEMPLATE
    assert 'let dentistsCache' in HTML_TEMPLATE


def test_dentist_selects_present_on_all_three_forms():
    assert 'id="appointment-dentist"' in HTML_TEMPLATE
    assert 'id="followup-dentist"' in HTML_TEMPLATE
    assert 'id="billing-dentist"' in HTML_TEMPLATE
    assert 'name="dentist_id"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_multi_dentist_forms_ui.py -v`
Expected: FAIL — none of these strings exist yet.

- [ ] **Step 3: Add the cache + loader**

In `templates.py`, find `let treatmentProceduresCache = [];` (around the other cache declarations) and add right after it:
```javascript
        let dentistsCache = [];
```

Find `async function loadTreatmentProcedures() {` and add this new function right after its closing `}`:
```javascript

        async function loadDentists() {
            const r = await fetch('/api/dentists').catch(() => null);
            dentistsCache = (r && r.ok) ? await r.json().catch(() => []) : [];
            if (!Array.isArray(dentistsCache)) dentistsCache = [];
        }

        function populateDentistSelect(selectId) {
            const sel = document.getElementById(selectId);
            if (!sel) return;
            const opts = [`<option value="">${t('unassigned', 'Unassigned')}</option>`];
            dentistsCache.forEach(d => {
                const name = String(d.display_name || '').trim();
                if (name) opts.push(`<option value="${d.id}">${escapeHtml(name)}</option>`);
            });
            sel.innerHTML = opts.join('');
        }
```

Add i18n key: find the EN dict's `staff_is_dentist:` entry (added in Task 5) and add right after it: `unassigned: 'Unassigned',`. Find the matching AR entry and add: `unassigned: 'غير معيّن',`.

Find the top-level `loadTreatmentProcedures();` call (search for the line that is JUST that call, not inside a function — it's part of the page's init sequence) and add `loadDentists();` right after it.

- [ ] **Step 4: Wire the appointment form**

In `templates.py`, find the appointment form's patient-select form-group (search for `id="appointment-patient-select"`) and add a new form-group right after that `<select>`'s closing tag, inside the same `.form-row`:
```html
                        <div class="form-group">
                            <label data-i18n="dentist">Dentist</label>
                            <select name="dentist_id" id="appointment-dentist"></select>
                        </div>
```

Find `async function showAddAppointmentModal(patientId = null, preferredDate = null) {` and add, right after the line `await loadPatientsSelect('appointment-patient-select');`:
```javascript
            populateDentistSelect('appointment-dentist');
```

- [ ] **Step 5: Wire the billing form**

In `templates.py`, find the billing form's patient-select form-group (search for `id="billing-patient-select"`) and add a new form-group right after it, inside the same `.form-row`:
```html
                        <div class="form-group">
                            <label data-i18n="dentist">Dentist</label>
                            <select name="dentist_id" id="billing-dentist"></select>
                        </div>
```

Find the top-level `DOMContentLoaded` handler that wires `billing-patient-select`'s change listener (search for `const billingPatientSel = document.getElementById('billing-patient-select');`) and add, inside the same handler, right after that block:
```javascript
            populateDentistSelect('billing-dentist');
```

- [ ] **Step 6: Wire the follow-up entry form**

In `templates.py`, find the follow-up form's tooth-no form-group inside the template literal (search for `id="followup-tooth-no"`) and add a new form-group right after its closing `</div>`, inside the same `.form-row`:
```javascript
                                <div class="form-group">
                                    <label>${t('dentist', 'Dentist')}</label>
                                    <select name="dentist_id" id="followup-dentist">
                                        <option value="">${t('unassigned', 'Unassigned')}</option>
                                        ${dentistsCache.map(d => `<option value="${d.id}">${String(d.display_name || '').trim()}</option>`).join('')}
                                    </select>
                                </div>
```

Since this form is a template literal rebuilt fresh each time `viewPatientProfile` renders, `dentistsCache` must already be populated by then. Find `await loadTreatmentProcedures();` at `templates.py:8396` (inside `viewPatientProfile`) and add right after it:
```javascript
            await loadDentists();
```

Add the EN i18n key `dentist: 'Dentist',` right after the `unassigned:` key added in Step 3, and the AR equivalent `dentist: 'طبيب',` in the matching spot.

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_multi_dentist_forms_ui.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add templates.py tests/test_multi_dentist_forms_ui.py
git commit -m "feat(multi-dentist): dentist dropdown on appointment/follow-up/billing forms"
```

---

### Task 7: Mobile — local schema migration

**Files:**
- Modify: `clinic_mobile_app/lib/services/database_service.dart`.
- Test: none (schema-only; covered indirectly by Task 8's model tests exercising `toDb()`/`fromDb()` against a real migrated table would need sqflite test infra this codebase doesn't have — see the identical reasoning in `docs/superpowers/plans/2026-07-11-unified-gross-profit.md` Task 4's design note. Verified instead via `dart analyze` + the manual check in Task 9).

**Interfaces:**
- Produces: `dentist_id INTEGER` column on local `appointments`, `followups`, `billing_records`.

- [ ] **Step 1: Bump the version and add the migration**

In `database_service.dart`, change:
```dart
    return openDatabase(path,
        version: 9, onCreate: _onCreate, onUpgrade: _onUpgrade);
```
to:
```dart
    return openDatabase(path,
        version: 10, onCreate: _onCreate, onUpgrade: _onUpgrade);
```

In `_onUpgrade`, add a new block right after the existing `if (oldVersion < 9) { ... }` block:
```dart
    if (oldVersion < 10) {
      await _addColumnIfMissing(db, 'appointments', 'dentist_id', 'INTEGER');
      await _addColumnIfMissing(db, 'followups', 'dentist_id', 'INTEGER');
      await _addColumnIfMissing(db, 'billing_records', 'dentist_id', 'INTEGER');
    }
```

In `_onCreate`, add `dentist_id INTEGER,` to each of the three CREATE TABLE literals (fresh-install path), right after each table's `updated_at TEXT,` line:
- The inline `appointments` CREATE (search `CREATE TABLE appointments (`): add after `updated_at TEXT,`.
- The `_createFollowups` constant (search `static const String _createFollowups`): add after its `updated_at TEXT,` line.
- The inline `billing_records` CREATE (search `CREATE TABLE billing_records (`): add after its `updated_at TEXT,` line.

- [ ] **Step 2: Run dart analyze**

Run: `cd clinic_mobile_app && dart analyze lib/services/database_service.dart`
Expected: no issues found.

- [ ] **Step 3: Commit**

```bash
git add clinic_mobile_app/lib/services/database_service.dart
git commit -m "feat(multi-dentist): add dentist_id to local appointments/followups/billing_records"
```

---

### Task 8: Mobile — model fields for `dentist_id`

**Files:**
- Modify: `clinic_mobile_app/lib/models/appointment.dart`, `clinic_mobile_app/lib/models/followup.dart`, `clinic_mobile_app/lib/models/billing_record.dart`.
- Test: `clinic_mobile_app/test/multi_dentist_models_test.dart` (new)

**Interfaces:**
- Consumes: local schema (Task 7).
- Produces: `dentistId` field on all three model classes, round-tripping through `fromJson`/`fromDb`/`toDb`/`toJson`/`copyWith`.

- [ ] **Step 1: Write the failing test**

Create `clinic_mobile_app/test/multi_dentist_models_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/appointment.dart';
import 'package:clinic_mobile_app/models/followup.dart';
import 'package:clinic_mobile_app/models/billing_record.dart';

void main() {
  group('Appointment dentistId', () {
    test('fromJson reads dentist_id', () {
      final a = Appointment.fromJson({
        'id': 1, 'patient_id': 2, 'appointment_datetime': '2026-08-01 10:00:00',
        'status': 'scheduled', 'dentist_id': 7,
      });
      expect(a.dentistId, 7);
    });

    test('fromJson tolerates missing dentist_id', () {
      final a = Appointment.fromJson({
        'id': 1, 'patient_id': 2, 'appointment_datetime': '2026-08-01 10:00:00', 'status': 'scheduled',
      });
      expect(a.dentistId, isNull);
    });

    test('toDb/fromDb round-trips dentist_id', () {
      final a = Appointment(
        patientId: 2, appointmentDatetime: '2026-08-01 10:00:00', dentistId: 9,
      );
      final restored = Appointment.fromDb(a.toDb());
      expect(restored.dentistId, 9);
    });

    test('toJson includes dentist_id when set', () {
      final a = Appointment(patientId: 2, appointmentDatetime: '2026-08-01 10:00:00', dentistId: 5);
      expect(a.toJson()['dentist_id'], 5);
    });
  });

  group('Followup dentistId', () {
    test('toDb/fromDb round-trips dentist_id', () {
      final f = Followup(patientId: 2, followupDate: '2026-08-01', treatmentProcedure: 'Filling', dentistId: 4);
      final restored = Followup.fromDb(f.toDb());
      expect(restored.dentistId, 4);
    });
  });

  group('BillingRecord dentistId', () {
    test('toDb/fromDb round-trips dentist_id', () {
      final b = BillingRecord(patientId: 2, subtotal: 100, paidAmount: 100, dentistId: 3);
      final restored = BillingRecord.fromDb(b.toDb());
      expect(restored.dentistId, 3);
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clinic_mobile_app && flutter test test/multi_dentist_models_test.dart`
Expected: FAIL — `dentistId` named parameter doesn't exist on any of the three classes.

- [ ] **Step 3: Add the field to each model**

In `appointment.dart`: add `final int? dentistId;` to the field list, `this.dentistId,` to the constructor, `dentistId: j['dentist_id'],` to `fromJson`, `if (dentistId != null) 'dentist_id': dentistId,` to `toJson`, `dentistId: row['dentist_id'],` to `fromDb`, `'dentist_id': dentistId,` to `toDb`, and thread it through `copyWith` (add `int? dentistId,` parameter and `dentistId: dentistId ?? this.dentistId,` in the returned instance).

In `followup.dart`: add `final int? dentistId;` to the field list, `this.dentistId,` to the constructor, `dentistId: j['dentist_id'] is int ? j['dentist_id'] : int.tryParse('${j['dentist_id'] ?? ''}'),` to `fromJson`, `dentistId: row['dentist_id'] as int?,` to `fromDb`, `'dentist_id': dentistId,` to `toDb`, and thread it through `copyWith` (add `int? dentistId,` parameter and `dentistId: dentistId ?? this.dentistId,`).

In `billing_record.dart`: add `final int? dentistId;` to the field list, `this.dentistId,` to the constructor, `dentistId: j['dentist_id'],` to `fromJson`, `dentistId: row['dentist_id'],` to `fromDb`, `'dentist_id': dentistId,` to both `toDb` and `toJson`. (`BillingRecord` has no `copyWith` today — none needed for this field.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clinic_mobile_app && flutter test test/multi_dentist_models_test.dart`
Expected: PASS (6 passed)

- [ ] **Step 5: Run dart analyze**

Run: `cd clinic_mobile_app && dart analyze lib/models/appointment.dart lib/models/followup.dart lib/models/billing_record.dart`
Expected: no issues found.

- [ ] **Step 6: Commit**

```bash
git add clinic_mobile_app/lib/models/appointment.dart clinic_mobile_app/lib/models/followup.dart clinic_mobile_app/lib/models/billing_record.dart clinic_mobile_app/test/multi_dentist_models_test.dart
git commit -m "feat(multi-dentist): add dentistId to mobile Appointment/Followup/BillingRecord models"
```

---

### Task 9: Full regression gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full Python suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (942 pre-existing + 22 new from Tasks 1-6 = 964), zero failures/errors.

- [ ] **Step 2: Run Flutter analyze + test**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: no issues found.

Run: `cd clinic_mobile_app && flutter test`
Expected: all pre-existing tests pass + 6 new from Task 8.

- [ ] **Step 3: Manual visual check (desktop)**

Open Settings → Manage Staff, mark an account as a dentist, confirm the toggle button label flips and persists after reload. Open the appointment/follow-up/billing forms, confirm each shows a dentist dropdown populated from that account.

- [ ] **Step 4: Manual visual check (mobile)**

Open the mobile app's appointment/follow-up/billing entry screens, confirm a dentist picker is present and populated from `GET /api/dentists` (requires the paired clinic to have at least one `is_dentist=1` account).
