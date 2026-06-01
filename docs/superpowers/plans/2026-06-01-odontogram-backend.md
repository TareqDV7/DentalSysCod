# Odontogram — Backend Implementation Plan (Track A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the backend schema, sync wiring, and REST API for the whole-tooth odontogram — an editable tooth-condition catalog, a per-patient tooth chart with read-time plan/unpaid badges and legacy auto-adopt, and multi-tooth treatment plans.

**Architecture:** Two new synced tables (`tooth_conditions`, `patient_tooth_chart`) plus a `treatment_plan_teeth` link table, all registered in `SYNC_TABLES` so they inherit the existing `updated_at` trigger + last-write-wins + tombstone sync with no bespoke sync code. New routes mirror the existing `/api/treatment-procedures` and follow-up patterns. Chart badges are computed at read time from `patient_followups` + plans, never stored.

**Tech Stack:** Python 3.10+, Flask, SQLite (WAL), pytest. All backend code lives in `dental_clinic.py`; tests in `tests/`.

**This is the foundation track — it must land and be green before the Desktop (Track B) and Mobile (Track C) plans can be verified end-to-end.** The frozen cross-track contract is the `GET /api/patients/<id>/tooth-chart` JSON shape (Task 8) and the FDI helper (Task 5).

**Spec:** `docs/superpowers/specs/2026-06-01-odontogram-design.md`

**Run all tests:** `python -m pytest tests/ -q` (the repo's RTK note: pytest summary is suppressed under `rtk`, so check `$LASTEXITCODE`; run plain `python -m pytest` when you need the summary). Per-test: `python -m pytest tests/test_x.py::test_name -v`.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `dental_clinic.py` | schema, migrations, sync list, routes | Modify: `CREATE TABLE` blocks near `~640`; Core-8 seed near `929`; `SYNC_TABLES` `361`; indexes near `902`; new `_is_valid_fdi` helper; new catalog + chart routes near `~2490`; treatment-plans routes `2420‑2489`; full-profile `1858` |
| `tests/test_tooth_conditions.py` | catalog CRUD + seed + soft-delete | Create |
| `tests/test_tooth_chart_api.py` | chart upsert / clear / FDI validation / scoping | Create |
| `tests/test_tooth_chart_badges.py` | computed `has_plan` / `unpaid_balance` + legacy adopt | Create |
| `tests/test_treatment_plan_teeth.py` | multi-tooth plan link CRUD | Create |
| `tests/test_tooth_chart_sync.py` | export/import + tombstones for the 3 tables | Create |
| `tests/test_api_fuzz.py` | no 5xx on malformed input to new routes | Modify |

---

## Task 1: `tooth_conditions` table + Core-8 seed

**Files:**
- Modify: `dental_clinic.py` (`CREATE TABLE` near `~640`; seed near `929`)
- Test: `tests/test_tooth_conditions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tooth_conditions.py`:

```python
"""Editable tooth-condition catalog (mirrors the treatment_procedures catalog)."""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def test_core_eight_seeded(client):
    rows = client.get('/api/tooth-conditions').get_json()
    names = {r['name'] for r in rows}
    assert {'Healthy', 'Decay', 'Filled', 'Crown', 'Root canal',
            'Missing', 'Implant', 'Needs extraction'} <= names
    # Catalog carries display metadata.
    decay = next(r for r in rows if r['name'] == 'Decay')
    assert decay['color'].startswith('#')
    assert decay['name_ar']
    assert 'sort_order' in decay
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tooth_conditions.py::test_core_eight_seeded -v`
Expected: FAIL — 404 (route missing) / no such table `tooth_conditions`.

- [ ] **Step 3: Add the table + seed**

In `dental_clinic.py`, after the `treatment_procedures` `CREATE TABLE` block (ends `~618`), add:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tooth_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            name_ar TEXT,
            color TEXT DEFAULT '#9ca3af',
            icon TEXT,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
```

After the `default_procedures` `executemany` block (ends `~943`), add the Core-8 seed:

```python
    default_tooth_conditions = [
        # name, name_ar, color, sort_order
        ('Healthy', 'سليم', '#22c55e', 0),
        ('Decay', 'تسوّس', '#ef4444', 1),
        ('Filled', 'حشوة', '#3b82f6', 2),
        ('Crown', 'تاج', '#a855f7', 3),
        ('Root canal', 'علاج عصب', '#f59e0b', 4),
        ('Missing', 'مفقود', '#6b7280', 5),
        ('Implant', 'زرعة', '#06b6d4', 6),
        ('Needs extraction', 'يحتاج خلع', '#dc2626', 7),
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO tooth_conditions (name, name_ar, color, sort_order)
        VALUES (?, ?, ?, ?)
    ''', default_tooth_conditions)
```

- [ ] **Step 4: Add a temporary inline route so the test can read the seed**

> The full catalog routes land in Task 6. To make Step 2's test pass now without dead code, add the GET collection route (the POST half comes in Task 6). Place it near the other catalog routes (`~1878`):

```python
@app.route('/api/tooth-conditions', methods=['GET'])
def tooth_conditions_list():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    include_inactive = str(request.args.get('all', '0')).strip() in ('1', 'true', 'True')
    where = '' if include_inactive else 'WHERE active = 1'
    cursor.execute(f'''
        SELECT id, name, name_ar, color, icon, sort_order, active, created_at
        FROM tooth_conditions {where}
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)
```

> Note: in Task 6 this `GET`-only route is replaced by a `GET/POST` collection route — the method list changes, body stays. Flask forbids two routes on the same rule, so Task 6 **edits this function** rather than adding a second one.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_tooth_conditions.py::test_core_eight_seeded -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_tooth_conditions.py
git commit -m "feat: tooth_conditions catalog table + Core-8 seed + list route"
```

---

## Task 2: `patient_tooth_chart` table + index

**Files:**
- Modify: `dental_clinic.py` (`CREATE TABLE` near `~640`; index near `902`)
- Test: `tests/test_tooth_chart_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tooth_chart_api.py`:

```python
"""Per-patient tooth chart: upsert, clear, FDI validation, scoping."""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(name='Tooth', last='Chart', phone='0590'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _condition_id(client, name):
    rows = client.get('/api/tooth-conditions').get_json()
    return next(r['id'] for r in rows if r['name'] == name)


def test_chart_table_exists(client):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patient_tooth_chart'")
    assert cur.fetchone() is not None
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tooth_chart_api.py::test_chart_table_exists -v`
Expected: FAIL — `assert None is not None`.

- [ ] **Step 3: Add the table + index**

After the `tooth_conditions` block from Task 1, add:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patient_tooth_chart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            tooth_no TEXT NOT NULL,
            condition_id INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (condition_id) REFERENCES tooth_conditions (id)
        )
    ''')
```

Near the other `CREATE INDEX` lines (`~902`), add:

```python
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_patient_tooth_chart_patient_id ON patient_tooth_chart(patient_id)')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tooth_chart_api.py::test_chart_table_exists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_api.py
git commit -m "feat: patient_tooth_chart table + index"
```

---

## Task 3: `treatment_plan_teeth` table + index

**Files:**
- Modify: `dental_clinic.py` (`CREATE TABLE` near `~640`; index near `902`)
- Test: `tests/test_treatment_plan_teeth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_treatment_plan_teeth.py`:

```python
"""Multi-tooth treatment plans via the treatment_plan_teeth link table."""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(name='Plan', last='Teeth', phone='0591'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_plan_teeth_table_exists(client):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='treatment_plan_teeth'")
    assert cur.fetchone() is not None
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_treatment_plan_teeth.py::test_plan_teeth_table_exists -v`
Expected: FAIL — `assert None is not None`.

- [ ] **Step 3: Add the table + index**

After the `patient_tooth_chart` block, add:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS treatment_plan_teeth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            tooth_no TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (plan_id) REFERENCES treatment_plans (id)
        )
    ''')
```

Near the `CREATE INDEX` lines, add:

```python
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_treatment_plan_teeth_plan_id ON treatment_plan_teeth(plan_id)')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_treatment_plan_teeth.py::test_plan_teeth_table_exists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_treatment_plan_teeth.py
git commit -m "feat: treatment_plan_teeth link table + index"
```

---

## Task 4: Register the three tables in `SYNC_TABLES`

**Files:**
- Modify: `dental_clinic.py:361` (`SYNC_TABLES`)
- Test: `tests/test_tooth_chart_sync.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tooth_chart_sync.py`:

```python
"""The three new odontogram tables sync like every other SYNC_TABLES entry:
they export, import, last-write-wins by updated_at, and tombstone on delete.
"""

import sqlite3

import pytest

import dental_clinic


AUTH = {'X-Device-Token': 'test-token'}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO paired_devices (device_id, device_name, device_token) VALUES (?,?,?)',
                ('dev-test', 'Test Device', 'test-token'))
    conn.commit()
    conn.close()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def test_new_tables_in_sync_export(client):
    data = client.get('/api/sync/export', headers=AUTH).get_json()
    assert 'tooth_conditions' in data['tables']
    assert 'patient_tooth_chart' in data['tables']
    assert 'treatment_plan_teeth' in data['tables']
    # The Core-8 seed rides along.
    assert len(data['tables']['tooth_conditions']) >= 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tooth_chart_sync.py::test_new_tables_in_sync_export -v`
Expected: FAIL — `KeyError`/assert: the three keys aren't in `data['tables']`.

- [ ] **Step 3: Add the three entries to `SYNC_TABLES`**

`dental_clinic.py:361` — add the three new tables (order doesn't matter):

```python
SYNC_TABLES = [
    'patients',
    'appointments',
    'visits',
    'treatments',
    'treatment_plans',
    'treatment_procedures',
    'treatment_plan_teeth',
    'tooth_conditions',
    'patient_tooth_chart',
    'patient_followups',
    'expenses',
    'billing',
    'holidays'
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tooth_chart_sync.py::test_new_tables_in_sync_export -v`
Expected: PASS. (The trigger loop at `dental_clinic.py:926` now also creates `trg_tooth_conditions_updated_at`, `trg_patient_tooth_chart_updated_at`, `trg_treatment_plan_teeth_updated_at` — verified implicitly because each table carries an `updated_at` column from Tasks 1‑3.)

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_sync.py
git commit -m "feat: sync the three odontogram tables via SYNC_TABLES"
```

---

## Task 5: FDI validation helper

**Files:**
- Modify: `dental_clinic.py` (add `_is_valid_fdi` near the other module helpers, e.g. just above `ensure_table_column` at `~377`)
- Test: `tests/test_tooth_chart_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tooth_chart_api.py`:

```python
def test_is_valid_fdi():
    valid = ['11', '18', '21', '28', '31', '38', '41', '48', '34', '16']
    invalid = ['10', '19', '51', '85', '09', '99', '1', '111', '5a', 'ab', '', None, ' 16']
    for s in valid:
        assert dental_clinic._is_valid_fdi(s) is True, s
    for s in invalid:
        assert dental_clinic._is_valid_fdi(s) is False, s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tooth_chart_api.py::test_is_valid_fdi -v`
Expected: FAIL — `AttributeError: module 'dental_clinic' has no attribute '_is_valid_fdi'`.

- [ ] **Step 3: Implement the helper**

Add near `~376` (just above `def ensure_table_column`):

```python
import re

_FDI_RE = re.compile(r'^[1-4][1-8]$')


def _is_valid_fdi(tooth_no):
    """True for a permanent-dentition FDI tooth number ('11'..'48').

    Quadrant 1-4, tooth 1-8. Rejects primary teeth (51-85), free text,
    whitespace, None, and non-two-digit values.
    """
    if not isinstance(tooth_no, str):
        return False
    return bool(_FDI_RE.match(tooth_no))
```

> If `import re` already exists at the top of `dental_clinic.py`, do not add a duplicate — place only the regex + function.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tooth_chart_api.py::test_is_valid_fdi -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_api.py
git commit -m "feat: _is_valid_fdi permanent-dentition tooth-number validator"
```

---

## Task 6: Tooth-condition catalog — POST / PUT / DELETE

**Files:**
- Modify: `dental_clinic.py` (extend the Task-1 `tooth_conditions_list` route to `GET/POST`; add a `/<id>` route)
- Test: `tests/test_tooth_conditions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tooth_conditions.py`:

```python
def test_create_condition(client):
    r = client.post('/api/tooth-conditions', json={
        'name': 'Veneer', 'name_ar': 'فينير', 'color': '#10b981', 'sort_order': 9,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    names = {c['name'] for c in client.get('/api/tooth-conditions').get_json()}
    assert 'Veneer' in names


def test_duplicate_condition_rejected(client):
    client.post('/api/tooth-conditions', json={'name': 'Sealant'})
    r = client.post('/api/tooth-conditions', json={'name': 'Sealant'})
    assert r.status_code == 409


def test_blank_name_rejected(client):
    r = client.post('/api/tooth-conditions', json={'name': '   '})
    assert r.status_code == 400


def test_update_condition(client):
    rows = client.get('/api/tooth-conditions').get_json()
    decay_id = next(c['id'] for c in rows if c['name'] == 'Decay')
    r = client.put(f'/api/tooth-conditions/{decay_id}', json={
        'name': 'Decay', 'name_ar': 'نخر', 'color': '#b91c1c', 'sort_order': 1, 'active': 1,
    })
    assert r.status_code == 200
    rows = client.get('/api/tooth-conditions').get_json()
    decay = next(c for c in rows if c['id'] == decay_id)
    assert decay['name_ar'] == 'نخر'
    assert decay['color'] == '#b91c1c'


def test_soft_delete_condition(client):
    rows = client.get('/api/tooth-conditions').get_json()
    implant_id = next(c['id'] for c in rows if c['name'] == 'Implant')
    assert client.delete(f'/api/tooth-conditions/{implant_id}').status_code == 200
    # Hidden from the default (active-only) list...
    active_names = {c['name'] for c in client.get('/api/tooth-conditions').get_json()}
    assert 'Implant' not in active_names
    # ...still present with ?all=1, marked inactive.
    all_rows = client.get('/api/tooth-conditions?all=1').get_json()
    implant = next(c for c in all_rows if c['id'] == implant_id)
    assert implant['active'] == 0
    # And a tombstone was recorded so the deactivation syncs.
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='tooth_conditions' AND row_id=?", (implant_id,))
    assert cur.fetchone()[0] == 1
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tooth_conditions.py -v`
Expected: the four new tests FAIL — POST returns 405 (route is GET-only) / `/<id>` route 404.

- [ ] **Step 3: Replace the Task-1 GET route with a full collection route + item route**

Replace the `tooth_conditions_list` function from Task 1 with:

```python
@app.route('/api/tooth-conditions', methods=['GET', 'POST'])
def tooth_conditions_collection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'GET':
        include_inactive = str(request.args.get('all', '0')).strip() in ('1', 'true', 'True')
        where = '' if include_inactive else 'WHERE active = 1'
        cursor.execute(f'''
            SELECT id, name, name_ar, color, icon, sort_order, active, created_at
            FROM tooth_conditions {where}
            ORDER BY sort_order ASC, name COLLATE NOCASE ASC
        ''')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(rows)

    data = request.json or {}
    name = str(data.get('name') or '').strip()
    if not name:
        conn.close()
        return jsonify({'error': 'Condition name is required'}), 400

    def as_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    try:
        cursor.execute('''
            INSERT INTO tooth_conditions (name, name_ar, color, icon, sort_order, active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (
            name,
            (data.get('name_ar') or None),
            (str(data.get('color') or '#9ca3af').strip() or '#9ca3af'),
            (data.get('icon') or None),
            as_int(data.get('sort_order'), 0),
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Condition already exists'}), 409

    conn.close()
    return jsonify({'success': True})


@app.route('/api/tooth-conditions/<int:condition_id>', methods=['PUT', 'DELETE'])
def tooth_condition_item(condition_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if request.method == 'DELETE':
        # Soft-delete (matches the procedure catalog) + tombstone so it syncs.
        cursor.execute('UPDATE tooth_conditions SET active = 0 WHERE id = ?', (condition_id,))
        record_tombstone(cursor, 'tooth_conditions', condition_id)
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    data = request.json or {}
    name = str(data.get('name') or '').strip()
    if not name:
        conn.close()
        return jsonify({'error': 'Condition name is required'}), 400

    def as_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    active = 1 if str(data.get('active', '1')).strip() in ('1', 'true', 'True', 'on') else 0
    try:
        cursor.execute('''
            UPDATE tooth_conditions
            SET name = ?, name_ar = ?, color = ?, icon = ?, sort_order = ?, active = ?
            WHERE id = ?
        ''', (
            name,
            (data.get('name_ar') or None),
            (str(data.get('color') or '#9ca3af').strip() or '#9ca3af'),
            (data.get('icon') or None),
            as_int(data.get('sort_order'), 0),
            active,
            condition_id,
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Condition already exists'}), 409

    conn.close()
    return jsonify({'success': True})
```

> Note: soft-delete records a tombstone but leaves the row (just `active=0`). That mirrors how the procedure catalog hides inactive entries while keeping referential history; chart rows pointing at the condition keep their `condition_id` and render neutral until re-set (handled in Task 8's GET via a `LEFT JOIN`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tooth_conditions.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_conditions.py
git commit -m "feat: tooth-condition catalog create/update/soft-delete routes"
```

---

## Task 7: Treatment plans — multi-tooth link handling

**Files:**
- Modify: `dental_clinic.py:2420‑2489` (`/api/treatment-plans` GET/POST + `/<id>` PUT/DELETE); add a small `_set_plan_teeth` helper
- Test: `tests/test_treatment_plan_teeth.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_treatment_plan_teeth.py`:

```python
def _create_plan(client, pid, teeth, name='Upper crowns'):
    r = client.post('/api/treatment-plans', json={
        'patient_id': pid, 'plan_name': name, 'teeth': teeth,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    return r


def _plan(client, plan_id):
    plans = client.get('/api/treatment-plans').get_json()
    return next(p for p in plans if p['id'] == plan_id)


def _plan_id(client):
    return client.get('/api/treatment-plans').get_json()[0]['id']


def test_create_plan_with_teeth(client):
    pid = _patient()
    _create_plan(client, pid, ['16', '26', '36'])
    plan = _plan(client, _plan_id(client))
    assert sorted(plan['teeth']) == ['16', '26', '36']
    # patient_name still resolves correctly (positional-serializer regression guard).
    assert plan['patient_name'] == 'Plan Teeth'


def test_invalid_tooth_skipped_on_create(client):
    pid = _patient()
    _create_plan(client, pid, ['16', '99', 'junk', '36'])
    plan = _plan(client, _plan_id(client))
    assert sorted(plan['teeth']) == ['16', '36']


def test_update_plan_teeth_diffs(client):
    pid = _patient()
    _create_plan(client, pid, ['16', '26'])
    plan_id = _plan_id(client)
    r = client.put(f'/api/treatment-plans/{plan_id}', json={
        'plan_name': 'Upper crowns', 'teeth': ['26', '46'],
    })
    assert r.status_code == 200
    assert sorted(_plan(client, plan_id)['teeth']) == ['26', '46']
    # Removing 16 tombstoned its link row.
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='treatment_plan_teeth'")
    assert cur.fetchone()[0] >= 1
    conn.close()


def test_delete_plan_cascades_teeth(client):
    pid = _patient()
    _create_plan(client, pid, ['16', '26', '36'])
    plan_id = _plan_id(client)
    assert client.delete(f'/api/treatment-plans/{plan_id}').status_code == 200
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM treatment_plan_teeth WHERE plan_id = ?', (plan_id,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='treatment_plan_teeth'")
    assert cur.fetchone()[0] == 3
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_treatment_plan_teeth.py -v`
Expected: the new tests FAIL — `plan` has no `teeth` key (`KeyError`).

- [ ] **Step 3: Add the `_set_plan_teeth` helper**

Add just above the `treatment_plans` route (`~2419`):

```python
def _set_plan_teeth(cursor, plan_id, teeth):
    """Reconcile a plan's linked teeth to exactly `teeth` (valid FDI only).

    Inserts new links, deletes (and tombstones) removed ones. No-ops for any
    tooth_no that isn't valid FDI. Caller commits.
    """
    wanted = {t for t in (teeth or []) if _is_valid_fdi(t)}
    cursor.execute('SELECT id, tooth_no FROM treatment_plan_teeth WHERE plan_id = ?', (plan_id,))
    existing = {row[1]: row[0] for row in cursor.fetchall()}

    for tooth_no in wanted - set(existing):
        cursor.execute(
            'INSERT INTO treatment_plan_teeth (plan_id, tooth_no) VALUES (?, ?)',
            (plan_id, tooth_no),
        )
    for tooth_no in set(existing) - wanted:
        link_id = existing[tooth_no]
        cursor.execute('DELETE FROM treatment_plan_teeth WHERE id = ?', (link_id,))
        record_tombstone(cursor, 'treatment_plan_teeth', link_id)
```

- [ ] **Step 4: Rewrite the GET serializer to dict access + `teeth`, and wire POST/PUT/DELETE**

Replace the `treatment_plans()` GET body (`2424‑2447`) so it uses `sqlite3.Row` and attaches a `teeth` array (fixes the positional `row[10]` fragility):

```python
    if request.method == 'GET':
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tp.*, p.first_name || ' ' || p.last_name AS patient_name
            FROM treatment_plans tp
            JOIN patients p ON tp.patient_id = p.id
            ORDER BY tp.id DESC
        ''')
        plans = [dict(row) for row in cursor.fetchall()]
        if plans:
            ids = [p['id'] for p in plans]
            qmarks = ','.join('?' * len(ids))
            cursor.execute(
                f'SELECT plan_id, tooth_no FROM treatment_plan_teeth WHERE plan_id IN ({qmarks}) ORDER BY tooth_no',
                ids,
            )
            teeth_by_plan = {}
            for r in cursor.fetchall():
                teeth_by_plan.setdefault(r['plan_id'], []).append(r['tooth_no'])
            for p in plans:
                p['teeth'] = teeth_by_plan.get(p['id'], [])
        conn.close()
        return jsonify(plans)
```

In the POST branch, after `conn.commit()` for the INSERT (`~2460`), capture the new id and set its teeth before closing:

```python
    cursor.execute('''
        INSERT INTO treatment_plans (patient_id, plan_name, goals, estimated_cost, status, start_date, end_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['patient_id'], data['plan_name'], data.get('goals'), data.get('estimated_cost'),
        data.get('status', 'draft'), data.get('start_date'), data.get('end_date'), data.get('notes')
    ))
    plan_id = cursor.lastrowid
    _set_plan_teeth(cursor, plan_id, data.get('teeth'))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': plan_id})
```

In `treatment_plan_detail` DELETE branch (`2468‑2473`), tombstone the links too:

```python
    if request.method == 'DELETE':
        _set_plan_teeth(cursor, plan_id, [])  # delete + tombstone every linked tooth
        cursor.execute('DELETE FROM treatment_plans WHERE id = ?', (plan_id,))
        record_tombstone(cursor, 'treatment_plans', plan_id)
        conn.commit()
        conn.close()
        return jsonify({'success': True})
```

In the PUT branch, after the `UPDATE treatment_plans ...` execute and before `conn.commit()` (`~2486`):

```python
        data['plan_name'], data.get('goals'), data.get('estimated_cost'), data.get('status', 'draft'),
        data.get('start_date'), data.get('end_date'), data.get('notes'), plan_id
    ))
    if 'teeth' in data:
        _set_plan_teeth(cursor, plan_id, data.get('teeth'))
    conn.commit()
```

> `'teeth' in data` guards so a PUT that doesn't mention teeth (e.g. a status-only edit from the existing plan form) leaves the links untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_treatment_plan_teeth.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full suite (regression guard for the serializer rewrite)**

Run: `python -m pytest tests/ -q`
Expected: all green — confirms the GET-serializer change didn't break any existing treatment-plan consumer.

- [ ] **Step 7: Commit**

```bash
git add dental_clinic.py tests/test_treatment_plan_teeth.py
git commit -m "feat: multi-tooth treatment plans (treatment_plan_teeth) + dict serializer"
```

---

## Task 8: Patient tooth-chart GET (the frozen contract)

**Files:**
- Modify: `dental_clinic.py` (new route near the catalog routes, `~2490`)
- Test: `tests/test_tooth_chart_badges.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tooth_chart_badges.py`:

```python
"""Tooth-chart GET shape: marked teeth, legacy auto-adopt, computed badges."""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient(name='Chart', last='Badge', phone='0592'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _condition_id(client, name):
    return next(c['id'] for c in client.get('/api/tooth-conditions').get_json() if c['name'] == name)


def _followup(client, pid, tooth_no, price=0, payment=0, discount=0):
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/06/2026', 'treatment_procedure': 'Tx',
        'tooth_no': tooth_no, 'price': price, 'discount': discount, 'payment': payment,
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def test_empty_chart(client):
    pid = _patient()
    data = client.get(f'/api/patients/{pid}/tooth-chart').get_json()
    assert data['teeth'] == {}
    assert len(data['conditions']) >= 8  # catalog rides along for the legend/picker


def test_marked_tooth_has_condition_and_color(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay, 'note': 'distal'})
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['16']['condition_id'] == decay
    assert teeth['16']['condition_name'] == 'Decay'
    assert teeth['16']['color'].startswith('#')
    assert teeth['16']['note'] == 'distal'
    assert teeth['16']['source'] == 'chart'


def test_unpaid_balance_badge_from_followups(client):
    pid = _patient()
    _followup(client, pid, '26', price=300, payment=100)  # 200 owed on tooth 26
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['26']['source'] == 'legacy'         # adopted, no explicit chart row
    assert teeth['26']['unpaid_balance'] == 200
    assert teeth['26']['has_plan'] is False


def test_has_plan_badge(client):
    pid = _patient()
    client.post('/api/treatment-plans', json={'patient_id': pid, 'plan_name': 'P', 'teeth': ['36']})
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['36']['has_plan'] is True


def test_legacy_junk_tooth_ignored(client):
    pid = _patient()
    _followup(client, pid, 'upper left', price=100)   # free-text junk
    _followup(client, pid, '51', price=100)           # primary tooth, out of scope
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert 'upper left' not in teeth
    assert '51' not in teeth


def test_explicit_mark_overrides_legacy_source(client):
    pid = _patient()
    _followup(client, pid, '16', price=100)           # would adopt as legacy...
    filled = _condition_id(client, 'Filled')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': filled})
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['16']['source'] == 'chart'           # explicit row wins
    assert teeth['16']['condition_name'] == 'Filled'


def test_chart_scoped_to_patient(client):
    a, b = _patient(phone='0001'), _patient(phone='0002')
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{a}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    assert client.get(f'/api/patients/{b}/tooth-chart').get_json()['teeth'] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tooth_chart_badges.py -v`
Expected: FAIL — 404 (route missing) on `GET /api/patients/<id>/tooth-chart`.

- [ ] **Step 3: Implement the GET route**

Add near the catalog routes (`~2490`, after the tooth-condition routes from Task 6):

```python
@app.route('/api/patients/<int:patient_id>/tooth-chart', methods=['GET'])
def patient_tooth_chart_get(patient_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Active catalog for the legend + picker.
    cursor.execute('''
        SELECT id, name, name_ar, color, icon, sort_order
        FROM tooth_conditions WHERE active = 1
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
    ''')
    conditions = [dict(r) for r in cursor.fetchall()]

    # Explicit chart rows, newest-updated wins per tooth (cross-device dup collapse).
    cursor.execute('''
        SELECT c.tooth_no, c.condition_id, c.note,
               tc.name AS condition_name, tc.color AS color
        FROM patient_tooth_chart c
        LEFT JOIN tooth_conditions tc ON tc.id = c.condition_id
        WHERE c.patient_id = ?
        ORDER BY c.updated_at ASC
    ''', (patient_id,))
    teeth = {}
    for r in cursor.fetchall():
        teeth[r['tooth_no']] = {
            'condition_id': r['condition_id'],
            'condition_name': r['condition_name'],
            'color': r['color'],
            'note': r['note'],
            'source': 'chart',
        }

    # Legacy auto-adopt: valid-FDI follow-up teeth that have no explicit chart row.
    cursor.execute(
        'SELECT DISTINCT tooth_no FROM patient_followups WHERE patient_id = ? AND tooth_no IS NOT NULL',
        (patient_id,),
    )
    for r in cursor.fetchall():
        t = r['tooth_no']
        if _is_valid_fdi(t) and t not in teeth:
            teeth[t] = {
                'condition_id': None, 'condition_name': None, 'color': None,
                'note': None, 'source': 'legacy',
            }

    # Computed badges (read-time, never stored).
    for tooth_no, entry in teeth.items():
        cursor.execute(
            'SELECT COALESCE(SUM(price - discount - payment), 0) FROM patient_followups '
            'WHERE patient_id = ? AND tooth_no = ?',
            (patient_id, tooth_no),
        )
        entry['unpaid_balance'] = max(0, round(cursor.fetchone()[0], 2))
        cursor.execute(
            'SELECT 1 FROM treatment_plan_teeth tpt JOIN treatment_plans tp ON tpt.plan_id = tp.id '
            'WHERE tp.patient_id = ? AND tpt.tooth_no = ? LIMIT 1',
            (patient_id, tooth_no),
        )
        entry['has_plan'] = cursor.fetchone() is not None

    conn.close()
    return jsonify({'conditions': conditions, 'teeth': teeth})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tooth_chart_badges.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_badges.py
git commit -m "feat: GET tooth-chart with computed badges + legacy auto-adopt"
```

---

## Task 9: Patient tooth-chart upsert + clear

**Files:**
- Modify: `dental_clinic.py` (extend the Task-8 route to `GET/POST`; add `/<tooth_no>` DELETE)
- Test: `tests/test_tooth_chart_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tooth_chart_api.py`:

```python
def test_upsert_then_update_keeps_one_row(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    crown = _condition_id(client, 'Crown')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': crown})
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM patient_tooth_chart WHERE patient_id=? AND tooth_no=?', (pid, '16'))
    assert cur.fetchone()[0] == 1  # updated in place, not duplicated
    conn.close()
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    assert teeth['16']['condition_name'] == 'Crown'


def test_null_condition_clears_tooth(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    r = client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': None})
    assert r.status_code == 200
    assert '16' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='patient_tooth_chart'")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_delete_endpoint_clears_tooth(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '21', 'condition_id': decay})
    assert client.delete(f'/api/patients/{pid}/tooth-chart/21').status_code == 200
    assert '21' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']


def test_invalid_fdi_rejected_on_upsert(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    for bad in ['99', '51', '5a', '1']:
        r = client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': bad, 'condition_id': decay})
        assert r.status_code == 400, bad


def test_unknown_condition_rejected(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': 99999})
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tooth_chart_api.py -v`
Expected: the new tests FAIL — POST returns 405 / DELETE 404.

- [ ] **Step 3: Extend the route to GET/POST + add DELETE**

Change the Task-8 decorator to accept POST and add the upsert + delete logic. Replace the `@app.route(... methods=['GET'])` line with `methods=['GET', 'POST']` and, at the **end** of `patient_tooth_chart_get` (before it returns for GET), branch on method. Cleanest: keep the GET function as-is and add the POST handling in the same function by checking `request.method`. Restructure the top of the function:

```python
@app.route('/api/patients/<int:patient_id>/tooth-chart', methods=['GET', 'POST'])
def patient_tooth_chart_collection(patient_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        tooth_no = str(data.get('tooth_no') or '').strip()
        if not _is_valid_fdi(tooth_no):
            conn.close()
            return jsonify({'error': 'Invalid FDI tooth number'}), 400

        condition_id = data.get('condition_id')
        if condition_id in (None, '', 0, '0'):
            # Clear to healthy = delete the row (+ tombstone) if present.
            cursor.execute(
                'SELECT id FROM patient_tooth_chart WHERE patient_id = ? AND tooth_no = ?',
                (patient_id, tooth_no),
            )
            for row in cursor.fetchall():
                cursor.execute('DELETE FROM patient_tooth_chart WHERE id = ?', (row['id'],))
                record_tombstone(cursor, 'patient_tooth_chart', row['id'])
            conn.commit()
            conn.close()
            return jsonify({'success': True})

        # Validate the condition exists.
        cursor.execute('SELECT id FROM tooth_conditions WHERE id = ?', (condition_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'error': 'Unknown condition_id'}), 400

        note = (data.get('note') or None)
        # Upsert: one row per (patient, tooth) on this device.
        cursor.execute(
            'SELECT id FROM patient_tooth_chart WHERE patient_id = ? AND tooth_no = ? ORDER BY updated_at DESC',
            (patient_id, tooth_no),
        )
        rows = cursor.fetchall()
        if rows:
            cursor.execute(
                'UPDATE patient_tooth_chart SET condition_id = ?, note = ? WHERE id = ?',
                (condition_id, note, rows[0]['id']),
            )
            # Drop any stray duplicate rows (e.g. from a past cross-device merge).
            for extra in rows[1:]:
                cursor.execute('DELETE FROM patient_tooth_chart WHERE id = ?', (extra['id'],))
                record_tombstone(cursor, 'patient_tooth_chart', extra['id'])
        else:
            cursor.execute(
                'INSERT INTO patient_tooth_chart (patient_id, tooth_no, condition_id, note) VALUES (?, ?, ?, ?)',
                (patient_id, tooth_no, condition_id, note),
            )
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    # --- GET (unchanged from Task 8) ---
    cursor.execute('''
        SELECT id, name, name_ar, color, icon, sort_order
        FROM tooth_conditions WHERE active = 1
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
    ''')
    conditions = [dict(r) for r in cursor.fetchall()]
    # ... (rest of the Task-8 GET body verbatim: explicit rows, legacy adopt, badges) ...
```

> Keep the entire Task-8 GET body (explicit rows → legacy adopt → badges → return) below the `# --- GET ---` marker unchanged. Only the function name, decorator methods, and the prepended POST branch are new.

Add the DELETE-by-tooth route immediately after:

```python
@app.route('/api/patients/<int:patient_id>/tooth-chart/<tooth_no>', methods=['DELETE'])
def patient_tooth_chart_delete(patient_id, tooth_no):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM patient_tooth_chart WHERE patient_id = ? AND tooth_no = ?',
        (patient_id, str(tooth_no)),
    )
    for row in cursor.fetchall():
        cursor.execute('DELETE FROM patient_tooth_chart WHERE id = ?', (row[0],))
        record_tombstone(cursor, 'patient_tooth_chart', row[0])
    conn.commit()
    conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tooth_chart_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_api.py
git commit -m "feat: tooth-chart upsert + clear (FDI-validated, dedup, tombstoned)"
```

---

## Task 10: Sync round-trip for chart rows + plan-teeth

**Files:**
- Test: `tests/test_tooth_chart_sync.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tooth_chart_sync.py`:

```python
def _patient():
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                ('Sync', 'Tooth', '0593'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_chart_row_exports_and_imports(client):
    pid = _patient()
    decay = next(c['id'] for c in client.get('/api/tooth-conditions').get_json() if c['name'] == 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})

    exported = client.get('/api/sync/export', headers=AUTH).get_json()
    chart_rows = exported['tables']['patient_tooth_chart']
    assert any(r['tooth_no'] == '16' for r in chart_rows)

    # Import the same row into a fresh DB shape via /import (idempotent, no resurrection).
    resp = client.post('/api/sync/import', headers=AUTH, json={'tables': {'patient_tooth_chart': chart_rows}})
    assert resp.status_code == 200


def test_chart_delete_tombstone_propagates(client):
    pid = _patient()
    decay = next(c['id'] for c in client.get('/api/tooth-conditions').get_json() if c['name'] == 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    client.delete(f'/api/patients/{pid}/tooth-chart/16')

    exported = client.get('/api/sync/export', headers=AUTH).get_json()
    assert any(t['table_name'] == 'patient_tooth_chart' for t in exported['tombstones'])
```

- [ ] **Step 2: Run tests to verify they fail (or pass)**

Run: `python -m pytest tests/test_tooth_chart_sync.py -v`
Expected: these PASS immediately if Tasks 4/9 are correct — the generic sync machinery already handles any `SYNC_TABLES` entry. **If they fail, it signals a real wiring bug** (e.g. missing `updated_at` column → trigger error, or table not in `SYNC_TABLES`). Treat a failure here as a regression to fix, not a test to weaken.

- [ ] **Step 3: (only if failing) fix wiring**

If export is missing the table → re-check Task 4. If an UPDATE on the table errors → re-check the `updated_at` column in Tasks 1‑3.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tooth_chart_sync.py
git commit -m "test: tooth-chart + plan-teeth sync round-trip and tombstones"
```

---

## Task 11: Expose `teeth` on the full patient profile

**Files:**
- Modify: `dental_clinic.py:1858` (the `treatment_plans` block inside `full-profile`)
- Test: `tests/test_treatment_plan_teeth.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_treatment_plan_teeth.py`:

```python
def test_full_profile_includes_plan_teeth(client):
    pid = _patient()
    _create_plan(client, pid, ['16', '26'])
    profile = client.get(f'/api/patients/{pid}/full-profile').get_json()
    plan = profile['treatment_plans'][0]
    assert sorted(plan['teeth']) == ['16', '26']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_treatment_plan_teeth.py::test_full_profile_includes_plan_teeth -v`
Expected: FAIL — `KeyError: 'teeth'`.

- [ ] **Step 3: Read the current full-profile block, then attach teeth**

Read `dental_clinic.py:1855‑1870` to see how `treatment_plans` is fetched (`fetch_all('SELECT * FROM treatment_plans WHERE patient_id = ? ORDER BY id DESC', ...)`). After that list is built, attach a `teeth` array to each plan:

```python
    plans = result['treatment_plans']  # however the existing code names this list
    if plans:
        plan_ids = [p['id'] for p in plans]
        qmarks = ','.join('?' * len(plan_ids))
        teeth_cur = conn.cursor()  # reuse the profile's existing connection/cursor
        teeth_cur.execute(
            f'SELECT plan_id, tooth_no FROM treatment_plan_teeth WHERE plan_id IN ({qmarks}) ORDER BY tooth_no',
            plan_ids,
        )
        teeth_by_plan = {}
        for plan_id_val, tooth_no in teeth_cur.fetchall():
            teeth_by_plan.setdefault(plan_id_val, []).append(tooth_no)
        for p in plans:
            p['teeth'] = teeth_by_plan.get(p['id'], [])
```

> Adapt the variable names to the actual `full-profile` handler (it uses a `fetch_all` helper returning dict rows). The principle is fixed: for the patient's plans, group `treatment_plan_teeth.tooth_no` by `plan_id` and attach as `teeth`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_treatment_plan_teeth.py::test_full_profile_includes_plan_teeth -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_treatment_plan_teeth.py
git commit -m "feat: include plan teeth in patient full-profile"
```

---

## Task 12: Fuzz guard for the new endpoints

**Files:**
- Modify: `tests/test_api_fuzz.py`
- Test: same

- [ ] **Step 1: Read the fuzz test to learn its structure**

Read `tests/test_api_fuzz.py` — it iterates endpoints and asserts no 5xx on malformed payloads. Identify the list/loop of endpoints it exercises.

- [ ] **Step 2: Add the new endpoints to the fuzz coverage**

Following the file's existing pattern, add these to the endpoints it fuzzes (use whatever shape the file already uses — a list of `(method, path)` tuples or similar):

```python
# Odontogram endpoints (must never return 5xx on garbage input):
('GET',  '/api/tooth-conditions'),
('POST', '/api/tooth-conditions'),
('PUT',  '/api/tooth-conditions/1'),
('DELETE', '/api/tooth-conditions/1'),
('GET',  '/api/patients/1/tooth-chart'),
('POST', '/api/patients/1/tooth-chart'),
('DELETE', '/api/patients/1/tooth-chart/16'),
```

> Match the file's existing tuple/registration format exactly; if it auto-discovers routes from `app.url_map`, no edit may be needed — in that case just run it (Step 3) and confirm the new routes are covered and green.

- [ ] **Step 3: Run the fuzz suite**

Run: `python -m pytest tests/test_api_fuzz.py -v`
Expected: PASS — no 5xx from the new routes on malformed JSON / wrong types / missing fields.

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_fuzz.py
git commit -m "test: fuzz-cover the odontogram endpoints"
```

---

## Task 13: Full-suite green + backend done

- [ ] **Step 1: Run the entire suite**

Run: `python -m pytest tests/ -q`
Expected: all green (the README's headline count rises by the new suites — the README test-count update is owned by the docs task in the Mobile/Desktop wrap-up, not here).

- [ ] **Step 2: Manual smoke against a running server (optional but recommended)**

```bash
CLINIC_HEADLESS=1 python dental_clinic.py   # in one terminal
# in another:
curl -s localhost:5000/api/tooth-conditions | head
curl -s -X POST localhost:5000/api/patients/1/tooth-chart -H 'Content-Type: application/json' -d '{"tooth_no":"16","condition_id":2}'
curl -s localhost:5000/api/patients/1/tooth-chart | head
```

Expected: catalog lists the Core 8; the chart GET returns `{conditions, teeth}` with tooth `16` marked. (Windows: use `py dental_clinic.py`; `$env:CLINIC_HEADLESS=1`.)

- [ ] **Step 3: Commit any final tidy-ups, then hand off**

The frozen contract (Task 8 JSON shape, Task 5 FDI helper) is now live — the Desktop (Track B) and Mobile (Track C) plans can be verified end-to-end against this backend.

---

## Self-Review (completed during planning)

- **Spec coverage:** schema (Tasks 1‑3) · sync wiring + `updated_at` requirement (Task 4) · FDI validation (Task 5) · catalog CRUD/soft-delete (Tasks 1,6) · chart GET with computed badges + legacy adopt (Task 8) · upsert/clear/dedup (Task 9) · multi-tooth plans + serializer fix (Task 7) · full-profile teeth (Task 11) · fuzz (Task 12). All spec API rows covered. The README "Features / REST API / table" doc updates are deliberately deferred to the final docs task in Track C so the count is updated once, after all three tracks land.
- **Type/route consistency:** `_is_valid_fdi` (str→bool) and `_set_plan_teeth(cursor, plan_id, teeth)` are used consistently across Tasks 5/7/8/9. The chart GET JSON shape (`{conditions:[…], teeth:{tooth_no:{condition_id,condition_name,color,note,source,unpaid_balance,has_plan}}}`) is identical in Task 8 and consumed unchanged by Tracks B/C.
- **Placeholder scan:** every code step carries complete code; Task 11 intentionally points the engineer to read the exact `full-profile` variable names (the principle + query are fully specified) because that handler's local naming wasn't captured verbatim during planning.
