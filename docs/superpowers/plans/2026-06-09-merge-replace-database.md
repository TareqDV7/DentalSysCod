# Merge / Replace Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-app Settings → Data Tools surface that lets a clinic export a portable bundle, **merge** another (possibly different) clinic's data additively into the current database, and **replace** the current database with an imported one — all login-gated, safety-backed-up, and never corrupting existing data.

**Architecture:** A pure, Flask-free engine in a new `db_merge.py` opens the imported DB as a read-only second connection and inserts its records into the live DB in foreign-key dependency order, assigning fresh IDs and rewriting every link (including the soft links `expenses.reference_id`→follow-up and `patient_credit_transactions.invoice_id`→billing). Catalog tables dedupe by name. Thin route handlers in `dental_clinic.py` handle upload, zip/SQLite validation, automatic safety backup, transaction control, and a brief maintenance window for the live file swap on Replace.

**Tech Stack:** Python 3 / Flask / SQLite (stdlib `sqlite3`, `zipfile`), pytest. Frontend is vanilla JS injected into `templates.py`'s `HTML_TEMPLATE`.

**Reference spec:** `docs/superpowers/specs/2026-06-09-merge-replace-database-design.md`

---

## Background the engineer needs

- **Schema lives in** `dental_clinic.py::init_database()` (~line 671). Synced/clinical tables and their foreign keys (verified against the schema):
  - `patients(id)` — root, **no `updated_at`**, only `created_at`.
  - `appointments(patient_id→patients)`
  - `visits(patient_id→patients, appointment_id→appointments NULLABLE)`
  - `treatments(patient_id→patients, appointment_id→appointments NULLABLE)` — note: **no `visit_id`**.
  - `treatment_plans(patient_id→patients)`
  - `treatment_plan_teeth(plan_id→treatment_plans)`
  - `treatment_procedures(id, name UNIQUE)` — catalog.
  - `tooth_conditions(id, name UNIQUE)` — catalog.
  - `patient_followups(patient_id→patients, procedure_id→treatment_procedures NULLABLE)`
  - `billing(patient_id→patients, treatment_id→treatments NULLABLE)`
  - `expenses(patient_id→patients NULLABLE, treatment_id→treatments NULLABLE, reference_id INTEGER, source_type TEXT)` — when `source_type='followup'`, `reference_id` is a **soft FK to `patient_followups.id`**.
  - `patient_tooth_chart(patient_id→patients, condition_id→tooth_conditions NULLABLE)`
  - `medical_images(patient_id→patients, file_name TEXT, file_path TEXT)` — files live on disk under `UPLOAD_FOLDER` (`_DATA_DIR/uploads`); `file_path` is an **absolute path**.
  - `patient_credit_transactions(patient_id→patients, invoice_id INTEGER NULLABLE)` — `invoice_id` is a **soft FK to `billing.id`**.
  - **Excluded from merge:** `holidays`, `users`, `app_settings`, audit/sync/pairing/license tables.
- **Helpers to reuse** (all in `dental_clinic.py`):
  - `get_table_columns(cursor, table_name)` (~line 666) → list of column names. Use for schema-drift tolerance.
  - `run_database_backup()` (~line 5565) → online-backup snapshot of `DB_NAME` into `BACKUP_DIR`; returns list of written paths. Use for the safety backup.
  - `_recompute_followup_balances(cursor, patient_id)` (~line 2427) → recompute the running ledger for one patient.
  - `UPLOAD_FOLDER` (Path, ~line 201), `_DATA_DIR`, `DB_NAME`, `CLOUD_MODE`, `BACKUP_DIR`.
- **Auth gate:** `_AUTH_REQUIRED_EXACT` set (~line 1877) + `_require_login_for_portal` before_request. Add new endpoints to that set; unauthenticated `/api/*` returns 401.
- **Cloud gate pattern:** handlers start with `if CLOUD_MODE: return jsonify({'error': 'Not available on the cloud node'}), 404`.
- **Test harness pattern** (mirror `tests/test_cloud_pairing_qr.py`): `pytest` fixture monkeypatches `DB_NAME` (+ `_DATA_DIR`, `UPLOAD_FOLDER`, `BACKUP_DIR` when needed) to `tmp_path`, sets `CLOUD_MODE=False`, calls `dental_clinic.init_database()`, yields `dental_clinic.app.test_client()`. Login = `with client.session_transaction() as sess: sess['uid']=1`.
- **Run tests:** `python -m pytest tests/ -q` (the suite summary may be suppressed by tooling — check `$LASTEXITCODE`). Run a single test with `python -m pytest tests/test_db_merge.py::test_name -v`.
- **Commit prefix convention:** `feat:` / `test:` / `docs:` (conventional commits). Do **not** stage the pre-existing unrelated changes to `serial_generator.py` / `tests/test_serial_admin_d.py`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `db_merge.py` (**create**) | Pure engine: `MergeReport` dataclass + `merge_database()` + private insert/remap/image-copy helpers. No Flask. |
| `db_import.py` (**create**) | Pure I/O helpers: `is_sqlite_file()`, `extract_bundle()` (zip-slip-safe), `build_bundle()`. No Flask. |
| `dental_clinic.py` (**modify**) | Three route handlers (`/api/data/export-bundle`, `/api/data/merge`, `/api/data/replace`), maintenance guard, add endpoints to `_AUTH_REQUIRED_EXACT`. |
| `templates.py` (**modify**) | Settings → Data Tools card markup, JS handlers, EN/AR translation keys. |
| `tests/test_db_merge.py` (**create**) | Engine unit tests (colliding IDs, remaps, dedup, schema drift, images, credit). |
| `tests/test_db_import.py` (**create**) | `is_sqlite_file` / `extract_bundle` / `build_bundle` unit tests. |
| `tests/test_data_tools_api.py` (**create**) | Route tests (auth, cloud-disabled, validation, safety backup, report, replace swap). |
| `README.md` (**modify**) | Features + REST API + Project Structure entries. |

---

## Task 1: `MergeReport` + engine skeleton

**Files:**
- Create: `db_merge.py`
- Test: `tests/test_db_merge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py
"""Engine tests for additive cross-clinic database merge (db_merge.py).

Builds two independent clinic DBs with COLLIDING primary-key ids, merges
source into destination, and asserts the destination keeps its own data while
the source's records arrive under fresh ids with every foreign key rewritten.
"""
import sqlite3

import pytest

import dental_clinic
import db_merge


def _new_db(path):
    """Create a real, fully-migrated clinic DB at `path` and return a Row-factory
    connection. Reuses dental_clinic.init_database by pointing DB_NAME at it."""
    prev = dental_clinic.DB_NAME
    dental_clinic.DB_NAME = str(path)
    try:
        dental_clinic.init_database()
    finally:
        dental_clinic.DB_NAME = prev
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def test_merge_report_starts_empty():
    report = db_merge.MergeReport()
    assert report.total_added() == 0
    assert report.warnings == []
    assert report.images_copied == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_merge.py::test_merge_report_starts_empty -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db_merge'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_merge.py
"""Additive cross-clinic database merge engine.

Pure (no Flask). Opens a source SQLite DB read-only and inserts its records into
a destination connection in foreign-key dependency order, assigning fresh ids
and rewriting every foreign key. Catalog tables dedupe by name. The destination's
existing rows are never updated or deleted — the merge is purely additive.

The caller owns the transaction: run inside one and commit on success / roll back
on exception so a partial merge never lands.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MergeReport:
    tables: dict = field(default_factory=dict)   # table -> {'added': int, 'skipped': int}
    images_copied: int = 0
    images_skipped: int = 0
    warnings: list = field(default_factory=list)

    def add(self, table: str, added: int, skipped: int = 0) -> None:
        entry = self.tables.setdefault(table, {'added': 0, 'skipped': 0})
        entry['added'] += added
        entry['skipped'] += skipped

    def total_added(self) -> int:
        return sum(t['added'] for t in self.tables.values())

    def as_dict(self) -> dict:
        return {
            'tables': self.tables,
            'images_copied': self.images_copied,
            'images_skipped': self.images_skipped,
            'warnings': self.warnings,
            'total_added': self.total_added(),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_merge.py::test_merge_report_starts_empty -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db_merge.py tests/test_db_merge.py
git commit -m "feat(db-merge): MergeReport dataclass + engine module skeleton"
```

---

## Task 2: Generic additive row insert with FK remap

**Files:**
- Modify: `db_merge.py`
- Test: `tests/test_db_merge.py`

This builds the reusable primitive used by almost every table: insert a source row as a new destination row, dropping `id`, keeping only columns that exist in the destination (schema-drift tolerance), and rewriting foreign-key columns through previously-built id maps.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py  (append)
def test_copy_table_remaps_fk_and_assigns_new_id(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    # Destination already has a patient at id=1 (occupies the colliding id).
    dst.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Dst', 'Existing')")
    dst.commit()
    # Source patient id=1 ('Src One') and an appointment for them.
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Src', 'One')")
    src.execute("INSERT INTO appointments (id, patient_id, appointment_date) VALUES (5, 1, '2026-01-01')")
    src.commit()

    remaps = {}
    patient_map = db_merge._copy_table(dst.cursor(), src.cursor(), 'patients', {}, remaps, db_merge.MergeReport())
    remaps['patients'] = patient_map
    appt_map = db_merge._copy_table(dst.cursor(), src.cursor(), 'appointments',
                                    {'patient_id': 'patients'}, remaps, db_merge.MergeReport())
    dst.commit()

    # Source patient id=1 must have landed under a NEW id (not 1 — that's taken).
    new_pid = patient_map[1]
    assert new_pid != 1
    row = dst.execute('SELECT first_name, last_name FROM patients WHERE id = ?', (new_pid,)).fetchone()
    assert (row['first_name'], row['last_name']) == ('Src', 'One')
    # The destination's original patient is untouched.
    assert dst.execute("SELECT first_name FROM patients WHERE id = 1").fetchone()['first_name'] == 'Dst'
    # The appointment's patient_id was rewritten to the new patient id.
    new_aid = appt_map[5]
    assert dst.execute('SELECT patient_id FROM appointments WHERE id = ?', (new_aid,)).fetchone()['patient_id'] == new_pid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_merge.py::test_copy_table_remaps_fk_and_assigns_new_id -v`
Expected: FAIL — `AttributeError: module 'db_merge' has no attribute '_copy_table'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_merge.py  (append)
def _dst_columns(dst_cur, table: str) -> list:
    dst_cur.execute(f'PRAGMA table_info({table})')
    return [r[1] for r in dst_cur.fetchall()]


def _remap_value(old_value, id_map: dict):
    """Translate one foreign-key value through an id map.

    None/0/'' stay null (no link). A value with no entry in the map (orphan)
    becomes None so we never point at a non-existent row."""
    if old_value in (None, 0, ''):
        return None
    return id_map.get(old_value)


def _copy_table(dst_cur, src_cur, table: str, fk_cols: dict, remaps: dict, report: MergeReport) -> dict:
    """Additively copy every row of `table` from source to destination.

    fk_cols maps a column name -> the remap key (an earlier table's id map) to
    rewrite it through. Returns this table's own old_id -> new_id map. Rows that
    raise a per-row SQLite error are counted as skipped without aborting.
    """
    cols = [c for c in _dst_columns(dst_cur, table) if c != 'id']
    src_cur.execute(f'SELECT * FROM {table} ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    id_map = {}
    added = skipped = 0
    for row in rows:
        old_id = row.get('id')
        values = []
        for col in cols:
            val = row.get(col)
            if col in fk_cols:
                val = _remap_value(val, remaps.get(fk_cols[col], {}))
            values.append(val)
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(values),
            )
        except sqlite3.Error as exc:
            skipped += 1
            report.warnings.append(f'{table}: skipped a row ({exc})')
            continue
        if old_id is not None:
            id_map[old_id] = dst_cur.lastrowid
        added += 1
    report.add(table, added, skipped)
    return id_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_merge.py::test_copy_table_remaps_fk_and_assigns_new_id -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db_merge.py tests/test_db_merge.py
git commit -m "feat(db-merge): generic additive row copy with FK remap + schema-drift tolerance"
```

---

## Task 3: Catalog dedupe by name

**Files:**
- Modify: `db_merge.py`
- Test: `tests/test_db_merge.py`

`treatment_procedures.name` and `tooth_conditions.name` are `UNIQUE`, so a blind insert would crash on a shared name. Dedupe: reuse the destination's row id when the name already exists, else insert.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py  (append)
def test_dedupe_catalog_by_name(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    dst.execute("INSERT INTO treatment_procedures (id, name, default_price) VALUES (3, 'Cleaning', 100)")
    dst.commit()
    src.execute("INSERT INTO treatment_procedures (id, name, default_price) VALUES (1, 'Cleaning', 250)")
    src.execute("INSERT INTO treatment_procedures (id, name, default_price) VALUES (2, 'Whitening', 400)")
    src.commit()

    report = db_merge.MergeReport()
    id_map = db_merge._dedupe_catalog(dst.cursor(), src.cursor(), 'treatment_procedures', report)
    dst.commit()

    # 'Cleaning' existed (dst id 3) -> reused, price NOT overwritten.
    assert id_map[1] == 3
    assert dst.execute("SELECT default_price FROM treatment_procedures WHERE id = 3").fetchone()[0] == 100
    # 'Whitening' was new -> inserted under a fresh id.
    assert id_map[2] not in (1, 2, 3)
    names = {r[0] for r in dst.execute("SELECT name FROM treatment_procedures").fetchall()}
    assert names == {'Cleaning', 'Whitening'}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_merge.py::test_dedupe_catalog_by_name -v`
Expected: FAIL — `AttributeError: module 'db_merge' has no attribute '_dedupe_catalog'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_merge.py  (append)
def _dedupe_catalog(dst_cur, src_cur, table: str, report: MergeReport, name_col: str = 'name') -> dict:
    """Merge a name-unique catalog. Reuse the destination row when the name
    already exists (keeping the destination's values); otherwise insert as new.
    Returns old_id -> resolved_id."""
    dst_cur.execute(f'SELECT id, {name_col} FROM {table}')
    existing = {str(r[1]).strip().lower(): r[0] for r in dst_cur.fetchall()}
    cols = [c for c in _dst_columns(dst_cur, table) if c != 'id']
    src_cur.execute(f'SELECT * FROM {table} ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    id_map = {}
    added = skipped = 0
    for row in rows:
        old_id = row.get('id')
        key = str(row.get(name_col) or '').strip().lower()
        if not key:
            skipped += 1
            continue
        if key in existing:
            id_map[old_id] = existing[key]
            skipped += 1
            continue
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(row.get(c) for c in cols),
            )
        except sqlite3.Error as exc:
            skipped += 1
            report.warnings.append(f'{table}: skipped a row ({exc})')
            continue
        new_id = dst_cur.lastrowid
        id_map[old_id] = new_id
        existing[key] = new_id
        added += 1
    report.add(table, added, skipped)
    return id_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_merge.py::test_dedupe_catalog_by_name -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db_merge.py tests/test_db_merge.py
git commit -m "feat(db-merge): dedupe catalog tables by name"
```

---

## Task 4: Soft-link remap for expenses

**Files:**
- Modify: `db_merge.py`
- Test: `tests/test_db_merge.py`

`expenses.reference_id` points at `patient_followups.id` only when `source_type='followup'`. The generic `_copy_table` can't express a column whose remap depends on another column's value, so expenses gets a dedicated copier.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py  (append)
def test_copy_expenses_remaps_followup_reference(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'S', 'One')")
    src.execute("INSERT INTO patient_followups (id, patient_id, followup_date) VALUES (9, 1, '2026-01-01')")
    # A followup-sourced expense (auto lab cost) referencing followup id 9 ...
    # (expenses.category is NOT NULL; there is no 'description' column.)
    src.execute("""INSERT INTO expenses (id, category, amount, source_type, reference_id, patient_id)
                   VALUES (4, 'Lab', 50, 'followup', 9, 1)""")
    # ... and a manual expense whose reference_id must be left untouched.
    src.execute("""INSERT INTO expenses (id, category, amount, source_type, reference_id)
                   VALUES (5, 'Rent', 800, 'manual', 999)""")
    src.commit()

    remaps = {
        'patients': {1: 100},
        'treatments': {},
        'patient_followups': {9: 700},
    }
    report = db_merge.MergeReport()
    db_merge._copy_expenses(dst.cursor(), src.cursor(), remaps, report)
    dst.commit()

    lab = dst.execute("SELECT patient_id, reference_id FROM expenses WHERE category = 'Lab'").fetchone()
    assert (lab['patient_id'], lab['reference_id']) == (100, 700)   # both links rewritten
    rent = dst.execute("SELECT reference_id FROM expenses WHERE category = 'Rent'").fetchone()
    assert rent['reference_id'] == 999                              # manual reference_id preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_merge.py::test_copy_expenses_remaps_followup_reference -v`
Expected: FAIL — `AttributeError: ... '_copy_expenses'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_merge.py  (append)
def _copy_expenses(dst_cur, src_cur, remaps: dict, report: MergeReport) -> dict:
    """Copy expenses, rewriting patient_id and treatment_id via their maps, and
    reference_id via the follow-up map ONLY when source_type == 'followup'
    (otherwise reference_id is unrelated bookkeeping and is preserved)."""
    cols = [c for c in _dst_columns(dst_cur, 'expenses') if c != 'id']
    src_cur.execute('SELECT * FROM expenses ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    patient_map = remaps.get('patients', {})
    treatment_map = remaps.get('treatments', {})
    followup_map = remaps.get('patient_followups', {})
    id_map = {}
    added = skipped = 0
    for row in rows:
        old_id = row.get('id')
        out = dict(row)
        if 'patient_id' in cols:
            out['patient_id'] = _remap_value(row.get('patient_id'), patient_map)
        if 'treatment_id' in cols:
            out['treatment_id'] = _remap_value(row.get('treatment_id'), treatment_map)
        if 'reference_id' in cols and str(row.get('source_type') or '') == 'followup':
            out['reference_id'] = _remap_value(row.get('reference_id'), followup_map)
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO expenses ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(out.get(c) for c in cols),
            )
        except sqlite3.Error as exc:
            skipped += 1
            report.warnings.append(f'expenses: skipped a row ({exc})')
            continue
        if old_id is not None:
            id_map[old_id] = dst_cur.lastrowid
        added += 1
    report.add('expenses', added, skipped)
    return id_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_merge.py::test_copy_expenses_remaps_followup_reference -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db_merge.py tests/test_db_merge.py
git commit -m "feat(db-merge): expenses copier with conditional followup reference remap"
```

---

## Task 5: Medical-image copier (file copy + path rewrite)

**Files:**
- Modify: `db_merge.py`
- Test: `tests/test_db_merge.py`

Images are files on disk. Copy each into the destination uploads dir under a fresh unique name, rewrite `file_path` (absolute) + remap `patient_id`. Skip with a warning when the source file is missing or no uploads dir was provided (bare `.db`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py  (append)
def test_copy_medical_images_copies_file_and_repaths(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src_uploads = tmp_path / 'src_uploads'
    dst_uploads = tmp_path / 'dst_uploads'
    src_uploads.mkdir(); dst_uploads.mkdir()
    img = src_uploads / 'xray1.png'
    img.write_bytes(b'\x89PNG fake bytes')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'S', 'One')")
    src.execute("""INSERT INTO medical_images (id, patient_id, file_name, file_path)
                   VALUES (1, 1, 'xray1.png', ?)""", (str(img),))
    src.commit()

    report = db_merge.MergeReport()
    remaps = {'patients': {1: 50}}
    db_merge._copy_medical_images(dst.cursor(), src.cursor(), remaps,
                                  str(src_uploads), str(dst_uploads), report)
    dst.commit()

    row = dst.execute("SELECT patient_id, file_name, file_path FROM medical_images").fetchone()
    assert row['patient_id'] == 50
    assert row['file_name'] == 'xray1.png'
    # File physically copied into the destination uploads dir, path rewritten there.
    import os
    assert os.path.dirname(row['file_path']) == str(dst_uploads)
    assert os.path.exists(row['file_path'])
    assert report.images_copied == 1


def test_copy_medical_images_skips_when_no_uploads(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'S', 'One')")
    src.execute("""INSERT INTO medical_images (id, patient_id, file_name, file_path)
                   VALUES (1, 1, 'x.png', '/nowhere/x.png')""")
    src.commit()
    report = db_merge.MergeReport()
    db_merge._copy_medical_images(dst.cursor(), src.cursor(), {'patients': {1: 50}},
                                  None, None, report)
    dst.commit()
    assert dst.execute("SELECT COUNT(*) FROM medical_images").fetchone()[0] == 0
    assert report.images_skipped == 1
    assert any('image' in w.lower() for w in report.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_merge.py -k medical_images -v`
Expected: FAIL — `AttributeError: ... '_copy_medical_images'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_merge.py  (append)
def _unique_dest_name(dst_uploads: str, file_name: str) -> str:
    stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base = os.path.basename(file_name or 'image')
    candidate = os.path.join(dst_uploads, f'merged_{stamp}_{base}')
    n = 0
    while os.path.exists(candidate):
        n += 1
        candidate = os.path.join(dst_uploads, f'merged_{stamp}_{n}_{base}')
    return candidate


def _copy_medical_images(dst_cur, src_cur, remaps: dict, src_uploads, dst_uploads,
                         report: MergeReport) -> None:
    patient_map = remaps.get('patients', {})
    cols = [c for c in _dst_columns(dst_cur, 'medical_images') if c != 'id']
    src_cur.execute('SELECT * FROM medical_images ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    if not rows:
        return
    if not src_uploads or not dst_uploads:
        report.images_skipped += len(rows)
        report.warnings.append(
            f'{len(rows)} medical image(s) skipped — image files were not included '
            f'(import a .zip bundle to carry X-rays).')
        return
    os.makedirs(dst_uploads, exist_ok=True)
    for row in rows:
        new_pid = _remap_value(row.get('patient_id'), patient_map)
        if new_pid is None:
            report.images_skipped += 1
            continue
        # Resolve the source file: stored absolute path, else by file_name in src uploads.
        candidates = []
        if row.get('file_path'):
            candidates.append(row['file_path'])
            candidates.append(os.path.join(src_uploads, os.path.basename(row['file_path'])))
        if row.get('file_name'):
            candidates.append(os.path.join(src_uploads, os.path.basename(row['file_name'])))
        source_file = next((p for p in candidates if p and os.path.exists(p)), None)
        if not source_file:
            report.images_skipped += 1
            report.warnings.append(f"medical image missing on disk: {row.get('file_name')}")
            continue
        dest_file = _unique_dest_name(dst_uploads, row.get('file_name') or os.path.basename(source_file))
        try:
            shutil.copy2(source_file, dest_file)
        except OSError as exc:
            report.images_skipped += 1
            report.warnings.append(f"could not copy image {row.get('file_name')}: {exc}")
            continue
        out = dict(row)
        out['patient_id'] = new_pid
        out['file_path'] = dest_file
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO medical_images ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(out.get(c) for c in cols),
            )
        except sqlite3.Error as exc:
            report.images_skipped += 1
            report.warnings.append(f'medical_images: skipped a row ({exc})')
            continue
        report.images_copied += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_merge.py -k medical_images -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add db_merge.py tests/test_db_merge.py
git commit -m "feat(db-merge): medical-image copier (file copy + path rewrite + skip warnings)"
```

---

## Task 6: Top-level `merge_database()` orchestration

**Files:**
- Modify: `db_merge.py`
- Test: `tests/test_db_merge.py`

Wire the helpers together in dependency order, opening the source read-only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py  (append)
def _seed_full_clinic(conn, tag, base):
    """Seed one patient + appointment + followup + billing + credit at colliding
    base ids so a merge has cross-table links to rewrite."""
    conn.execute("INSERT INTO patients (id, first_name, last_name, phone) VALUES (?, ?, 'X', '050')",
                 (base, tag))
    conn.execute("INSERT INTO appointments (id, patient_id, appointment_date) VALUES (?, ?, '2026-02-02')",
                 (base, base))
    conn.execute("INSERT INTO patient_followups (id, patient_id, followup_date, price) VALUES (?, ?, '2026-02-02', 300)",
                 (base, base))
    conn.execute("INSERT INTO billing (id, patient_id, amount, paid_amount) VALUES (?, ?, 300, 100)",
                 (base, base))
    conn.execute("INSERT INTO patient_credit_transactions (id, patient_id, amount, type, invoice_id) VALUES (?, ?, 20, 'manual', ?)",
                 (base, base, base))
    conn.commit()


def test_merge_database_full_roundtrip(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    _seed_full_clinic(dst, 'DstPatient', 1)
    _seed_full_clinic(src, 'SrcPatient', 1)   # colliding id=1 everywhere

    report = db_merge.merge_database(dst, str(tmp_path / 'src.db'),
                                     include_images=True, include_credit=True)
    dst.commit()

    # Destination still has its own patient at id 1.
    assert dst.execute("SELECT first_name FROM patients WHERE id=1").fetchone()['first_name'] == 'DstPatient'
    # Both clinics' patients now present (2 total).
    assert dst.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2
    # The imported patient's appointment/followup/billing point at the imported patient.
    src_pid = dst.execute("SELECT id FROM patients WHERE first_name='SrcPatient'").fetchone()['id']
    assert dst.execute("SELECT patient_id FROM appointments WHERE patient_id=?", (src_pid,)).fetchone() is not None
    assert dst.execute("SELECT patient_id FROM patient_followups WHERE patient_id=?", (src_pid,)).fetchone() is not None
    # Credit invoice_id rewritten to the imported billing row.
    src_bill = dst.execute("SELECT id FROM billing WHERE patient_id=?", (src_pid,)).fetchone()['id']
    cred = dst.execute("SELECT invoice_id FROM patient_credit_transactions WHERE patient_id=?", (src_pid,)).fetchone()
    assert cred['invoice_id'] == src_bill
    assert report.total_added() >= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_merge.py::test_merge_database_full_roundtrip -v`
Expected: FAIL — `AttributeError: ... 'merge_database'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_merge.py  (append)
# (table, {fk_column: remap_key}) in foreign-key dependency order.
_GENERIC_ORDER = [
    ('appointments',         {'patient_id': 'patients'}),
    ('visits',               {'patient_id': 'patients', 'appointment_id': 'appointments'}),
    ('treatments',           {'patient_id': 'patients', 'appointment_id': 'appointments'}),
    ('treatment_plans',      {'patient_id': 'patients'}),
    ('treatment_plan_teeth', {'plan_id': 'treatment_plans'}),
    ('patient_followups',    {'patient_id': 'patients', 'procedure_id': 'treatment_procedures'}),
    ('billing',              {'patient_id': 'patients', 'treatment_id': 'treatments'}),
]


def merge_database(dst_conn, src_db_path, *, src_uploads=None, dst_uploads=None,
                   include_images=True, include_credit=True) -> MergeReport:
    """Additively merge the SQLite DB at src_db_path into dst_conn. Caller commits."""
    report = MergeReport()
    src_conn = sqlite3.connect(f'file:{src_db_path}?mode=ro', uri=True)
    src_conn.row_factory = sqlite3.Row
    try:
        dst_cur = dst_conn.cursor()
        src_cur = src_conn.cursor()
        remaps = {}
        # Catalogs first (deduped by name) so followups/tooth-chart can remap to them.
        remaps['treatment_procedures'] = _dedupe_catalog(dst_cur, src_cur, 'treatment_procedures', report)
        remaps['tooth_conditions'] = _dedupe_catalog(dst_cur, src_cur, 'tooth_conditions', report)
        # Patients next, then everything that hangs off them.
        remaps['patients'] = _copy_table(dst_cur, src_cur, 'patients', {}, remaps, report)
        for table, fk_cols in _GENERIC_ORDER:
            remaps[table] = _copy_table(dst_cur, src_cur, table, fk_cols, remaps, report)
        _copy_expenses(dst_cur, src_cur, remaps, report)
        remaps['patient_tooth_chart'] = _copy_table(
            dst_cur, src_cur, 'patient_tooth_chart',
            {'patient_id': 'patients', 'condition_id': 'tooth_conditions'}, remaps, report)
        if include_images:
            _copy_medical_images(dst_cur, src_cur, remaps, src_uploads, dst_uploads, report)
        if include_credit:
            _copy_table(dst_cur, src_cur, 'patient_credit_transactions',
                        {'patient_id': 'patients', 'invoice_id': 'billing'}, remaps, report)
        # Recompute running balances for every imported patient.
        for new_pid in remaps['patients'].values():
            try:
                _recompute_balances(dst_cur, new_pid)
            except sqlite3.Error:
                pass
    finally:
        src_conn.close()
    return report


def _recompute_balances(dst_cur, patient_id):
    """Defer to dental_clinic's ledger recompute. Imported here lazily to keep
    db_merge import-light and avoid a circular import at module load."""
    import dental_clinic
    dental_clinic._recompute_followup_balances(dst_cur, patient_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_merge.py::test_merge_database_full_roundtrip -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db_merge.py tests/test_db_merge.py
git commit -m "feat(db-merge): merge_database orchestration in FK dependency order"
```

---

## Task 7: Schema-drift + garbage-source robustness tests

**Files:**
- Test: `tests/test_db_merge.py`

No new engine code expected — these prove the drift tolerance and no-crash guarantees already built in. If a test fails, fix the engine minimally.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_merge.py  (append)
def test_merge_tolerates_older_source_missing_column(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Old', 'Schema')")
    src.commit()
    # Simulate an older source DB lacking a newer column the destination has.
    src.execute("ALTER TABLE patients DROP COLUMN notes")   # 'notes' added by a later migration
    src.commit()

    report = db_merge.merge_database(dst, str(tmp_path / 'src.db'),
                                     include_images=False, include_credit=False)
    dst.commit()
    assert dst.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 1
    assert report.tables['patients']['added'] == 1


def test_merge_garbage_source_raises_cleanly(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    junk = tmp_path / 'junk.db'
    junk.write_bytes(b'not a sqlite database at all')
    with pytest.raises(Exception):
        db_merge.merge_database(dst, str(junk))
    # Destination untouched (caller would roll back; here nothing was inserted).
    assert dst.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify behavior**

Run: `python -m pytest tests/test_db_merge.py -k "older_source or garbage_source" -v`
Expected: PASS. (If `DROP COLUMN` is unsupported on the installed SQLite, replace that test with a source built from a hand-written `CREATE TABLE patients` lacking `notes`.)

- [ ] **Step 3: (only if a test failed) fix engine minimally**

If `older_source` failed, confirm `_copy_table` derives columns from the **destination** and intersects with source row keys (it reads `row.get(col)` for destination columns, so a missing source key yields `None` — already correct). Adjust only if needed.

- [ ] **Step 4: Re-run**

Run: `python -m pytest tests/test_db_merge.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_db_merge.py db_merge.py
git commit -m "test(db-merge): schema-drift tolerance + garbage-source safety"
```

---

## Task 8: I/O helpers — `is_sqlite_file`, `extract_bundle`, `build_bundle`

**Files:**
- Create: `db_import.py`
- Test: `tests/test_db_import.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_import.py
"""Bundle / file-validation helpers for the data-tools import surface."""
import sqlite3
import zipfile

import pytest

import db_import


def test_is_sqlite_file_true_for_real_db(tmp_path):
    db = tmp_path / 'real.db'
    sqlite3.connect(str(db)).close()
    assert db_import.is_sqlite_file(str(db)) is True


def test_is_sqlite_file_false_for_junk(tmp_path):
    junk = tmp_path / 'junk.bin'
    junk.write_bytes(b'PK\x03\x04 not a db')
    assert db_import.is_sqlite_file(str(junk)) is False


def test_build_then_extract_bundle_roundtrip(tmp_path):
    db = tmp_path / 'dental_clinic.db'
    sqlite3.connect(str(db)).close()
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    (uploads / 'x.png').write_bytes(b'img')
    bundle = tmp_path / 'bundle.zip'

    db_import.build_bundle(str(bundle), str(db), str(uploads))
    out = tmp_path / 'out'
    db_path, uploads_dir = db_import.extract_bundle(str(bundle), str(out))

    assert db_import.is_sqlite_file(db_path)
    assert (uploads_dir is not None) and (out / 'uploads' / 'x.png').exists()


def test_extract_bundle_rejects_zip_slip(tmp_path):
    evil = tmp_path / 'evil.zip'
    with zipfile.ZipFile(str(evil), 'w') as z:
        z.writestr('../escape.txt', 'pwned')
    with pytest.raises(ValueError):
        db_import.extract_bundle(str(evil), str(tmp_path / 'out'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db_import'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db_import.py
"""Pure helpers for the data-tools import/export surface: SQLite validation and
zip-bundle build/extract (zip-slip-safe). No Flask."""
from __future__ import annotations

import os
import sqlite3
import zipfile

_SQLITE_MAGIC = b'SQLite format 3\x00'
_DB_MEMBER = 'dental_clinic.db'
_UPLOADS_PREFIX = 'uploads/'


def is_sqlite_file(path: str) -> bool:
    try:
        with open(path, 'rb') as fh:
            return fh.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def build_bundle(zip_path: str, db_path: str, uploads_dir: str | None) -> None:
    """Write a .zip containing the DB as `dental_clinic.db` plus the uploads tree."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(db_path, _DB_MEMBER)
        if uploads_dir and os.path.isdir(uploads_dir):
            for root, _dirs, files in os.walk(uploads_dir):
                for name in files:
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, uploads_dir)
                    z.write(full, _UPLOADS_PREFIX + rel.replace(os.sep, '/'))


def _safe_members(z: zipfile.ZipFile, dest_root: str):
    dest_root = os.path.abspath(dest_root)
    for member in z.namelist():
        target = os.path.abspath(os.path.join(dest_root, member))
        if target != dest_root and not target.startswith(dest_root + os.sep):
            raise ValueError(f'unsafe path in archive: {member}')
        yield member


def extract_bundle(zip_path: str, dest_dir: str):
    """Extract a bundle into dest_dir, guarding against zip-slip. Returns
    (db_path, uploads_dir_or_None)."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = list(_safe_members(z, dest_dir))   # validates before extracting
        z.extractall(dest_dir, members=members)
    db_path = os.path.join(dest_dir, _DB_MEMBER)
    if not os.path.exists(db_path):
        # Fall back to the first *.db member.
        dbs = [m for m in members if m.lower().endswith('.db')]
        if not dbs:
            raise ValueError('bundle contains no database file')
        db_path = os.path.join(dest_dir, dbs[0])
    uploads_dir = os.path.join(dest_dir, 'uploads')
    return db_path, (uploads_dir if os.path.isdir(uploads_dir) else None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_import.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add db_import.py tests/test_db_import.py
git commit -m "feat(db-import): sqlite validation + zip-slip-safe bundle build/extract"
```

---

## Task 9: `/api/data/export-bundle` endpoint

**Files:**
- Modify: `dental_clinic.py` (add route near `backup_database` ~line 3669; add path to `_AUTH_REQUIRED_EXACT` ~line 1877)
- Test: `tests/test_data_tools_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_tools_api.py
"""Route tests for the Settings -> Data Tools surface."""
import io
import os
import sqlite3
import zipfile

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db = data_dir / 'dental_clinic.db'
    uploads = data_dir / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', uploads)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def test_export_bundle_requires_login(client):
    assert client.get('/api/data/export-bundle').status_code == 401


def test_export_bundle_returns_zip_with_db(client):
    _login(client)
    resp = client.get('/api/data/export-bundle')
    assert resp.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'dental_clinic.db' in z.namelist()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_tools_api.py -k export_bundle -v`
Expected: FAIL — 404 (route missing) / or 401 test passes but zip test 404s.

- [ ] **Step 3: Write minimal implementation**

Add `'/api/data/export-bundle'`, `'/api/data/merge'`, `'/api/data/replace'` to the `_AUTH_REQUIRED_EXACT` set (line ~1877). Then add the route (place after `backup_database`, ~line 3672):

```python
# dental_clinic.py  (after backup_database)
import tempfile
import db_import
import db_merge


@app.route('/api/data/export-bundle')
def data_export_bundle():
    if CLOUD_MODE:
        return jsonify({'error': 'Not available on the cloud node'}), 404
    # Snapshot the live DB consistently (online backup) into a temp file, then zip.
    tmpdir = tempfile.mkdtemp(prefix='dc_export_')
    snap = os.path.join(tmpdir, 'dental_clinic.db')
    src = sqlite3.connect(str(DB_NAME))
    try:
        dst = sqlite3.connect(snap)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    bundle = os.path.join(tmpdir, 'dentacare_bundle.zip')
    db_import.build_bundle(bundle, snap, str(UPLOAD_FOLDER))
    name = f"dentacare_bundle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return send_file(bundle, as_attachment=True, download_name=name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_data_tools_api.py -k export_bundle -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_data_tools_api.py
git commit -m "feat(data-tools): export-bundle endpoint (db + uploads zip)"
```

---

## Task 10: `/api/data/merge` endpoint

**Files:**
- Modify: `dental_clinic.py`
- Test: `tests/test_data_tools_api.py`

Accepts a multipart upload (`.zip` or `.db`), takes a safety backup, runs the engine in one transaction, returns the report.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_tools_api.py  (append)
def _make_source_db(path):
    """A second clinic's DB with one patient, colliding id 1."""
    prev = dental_clinic.DB_NAME
    dental_clinic.DB_NAME = str(path)
    try:
        dental_clinic.init_database()
    finally:
        dental_clinic.DB_NAME = prev
    conn = sqlite3.connect(str(path))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Imported', 'Patient')")
    conn.commit()
    conn.close()


def test_merge_requires_login(client):
    assert client.post('/api/data/merge').status_code == 401


def test_merge_rejects_non_sqlite(client):
    _login(client)
    data = {'file': (io.BytesIO(b'not a database'), 'evil.db')}
    resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 400


def test_merge_adds_imported_patient_and_keeps_existing(client, tmp_path):
    _login(client)
    # Destination already has a patient at id 1.
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Local', 'Owner')")
    conn.commit(); conn.close()

    src = tmp_path / 'other_clinic.db'
    _make_source_db(src)
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'other_clinic.db')}
        resp = client.post('/api/data/merge', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['report']['total_added'] >= 1
    assert body['backup_path']                      # safety backup was taken

    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    names = {r[0] for r in conn.execute("SELECT first_name FROM patients").fetchall()}
    conn.close()
    assert {'Local', 'Imported'} <= names


def test_merge_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    resp = client.post('/api/data/merge', data={}, content_type='multipart/form-data')
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_tools_api.py -k merge -v`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Write minimal implementation**

```python
# dental_clinic.py  (after data_export_bundle)
def _save_and_resolve_upload(tmpdir):
    """Persist the uploaded file and resolve it to (db_path, uploads_dir|None).
    Returns (None, None, error_message) on validation failure."""
    file = request.files.get('file')
    if not file or not file.filename:
        return None, None, 'No file uploaded'
    raw = os.path.join(tmpdir, secure_filename(file.filename) or 'upload')
    file.save(raw)
    if zipfile.is_zipfile(raw):
        try:
            db_path, uploads_dir = db_import.extract_bundle(raw, os.path.join(tmpdir, 'unpacked'))
        except (ValueError, zipfile.BadZipFile) as exc:
            return None, None, f'Invalid bundle: {exc}'
        if not db_import.is_sqlite_file(db_path):
            return None, None, 'Bundle does not contain a valid database'
        return db_path, uploads_dir, None
    if db_import.is_sqlite_file(raw):
        return raw, None, None
    return None, None, 'File is not a DentaCare database or bundle'


@app.route('/api/data/merge', methods=['POST'])
def data_merge():
    if CLOUD_MODE:
        return jsonify({'error': 'Not available on the cloud node'}), 404
    tmpdir = tempfile.mkdtemp(prefix='dc_merge_')
    db_path, uploads_dir, err = _save_and_resolve_upload(tmpdir)
    if err:
        return jsonify({'error': err}), 400
    backups = run_database_backup()
    backup_path = backups[0] if backups else None
    conn = sqlite3.connect(str(DB_NAME))
    try:
        report = db_merge.merge_database(
            conn, db_path, src_uploads=uploads_dir, dst_uploads=str(UPLOAD_FOLDER),
            include_images=True, include_credit=True)
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — any failure must roll back the whole merge
        conn.rollback()
        return jsonify({'error': f'Merge failed and was rolled back: {exc}',
                        'backup_path': backup_path}), 500
    finally:
        conn.close()
    return jsonify({'success': True, 'report': report.as_dict(), 'backup_path': backup_path})
```

Confirm imports exist at the top of `dental_clinic.py`: `zipfile`, `tempfile`, `secure_filename` (already imported from `werkzeug.utils` for medical images), `db_import`, `db_merge`. Add any missing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_data_tools_api.py -k merge -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_data_tools_api.py
git commit -m "feat(data-tools): merge endpoint (safety backup + transactional additive merge)"
```

---

## Task 11: Maintenance guard + `/api/data/replace` endpoint

**Files:**
- Modify: `dental_clinic.py` (add a maintenance flag + before_request guard near the other before_request hooks ~line 1882; add the route)
- Test: `tests/test_data_tools_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_tools_api.py  (append)
def test_replace_requires_login(client):
    assert client.post('/api/data/replace').status_code == 401


def test_replace_swaps_database(client, tmp_path):
    _login(client)
    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Local', 'Owner')")
    conn.commit(); conn.close()

    src = tmp_path / 'replacement.db'
    _make_source_db(src)   # has 'Imported Patient', no 'Local Owner'
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'replacement.db')}
        resp = client.post('/api/data/replace', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.get_json()['backup_path']

    conn = sqlite3.connect(str(dental_clinic.DB_NAME))
    names = {r[0] for r in conn.execute("SELECT first_name FROM patients").fetchall()}
    conn.close()
    assert names == {'Imported'}              # local data replaced, not merged


def test_replace_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    resp = client.post('/api/data/replace', data={}, content_type='multipart/form-data')
    assert resp.status_code == 404


def test_maintenance_guard_blocks_api(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, '_MAINTENANCE', True)
    resp = client.get('/api/patients')
    assert resp.status_code == 503
    assert resp.get_json().get('maintenance') is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_tools_api.py -k "replace or maintenance" -v`
Expected: FAIL — route missing / `_MAINTENANCE` undefined.

- [ ] **Step 3: Write minimal implementation**

Add the maintenance flag + guard. Put the flag near other module globals and the guard as a `before_request` (place it just before `_require_login_for_portal` ~line 1882):

```python
# dental_clinic.py  (module-level global, near other flags)
_MAINTENANCE = False


# dental_clinic.py  (before_request, before _require_login_for_portal)
@app.before_request
def _maintenance_gate():
    if _MAINTENANCE and (request.path or '').startswith('/api/') \
            and not (request.path or '').startswith('/api/data/'):
        return jsonify({'maintenance': True,
                        'error': 'Database maintenance in progress — retry shortly.'}), 503
    return None
```

Add the replace route (after `data_merge`):

```python
# dental_clinic.py  (after data_merge)
@app.route('/api/data/replace', methods=['POST'])
def data_replace():
    global _MAINTENANCE
    if CLOUD_MODE:
        return jsonify({'error': 'Not available on the cloud node'}), 404
    tmpdir = tempfile.mkdtemp(prefix='dc_replace_')
    db_path, uploads_dir, err = _save_and_resolve_upload(tmpdir)
    if err:
        return jsonify({'error': err}), 400
    backups = run_database_backup()
    backup_path = backups[0] if backups else None
    _MAINTENANCE = True
    try:
        target = str(DB_NAME)
        # Release WAL sidecars on the live DB before overwriting.
        try:
            c = sqlite3.connect(target)
            c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            c.close()
        except sqlite3.Error:
            pass
        for sidecar in (target + '-wal', target + '-shm'):
            try:
                os.remove(sidecar)
            except OSError:
                pass
        shutil.copy2(db_path, target)
        # Swap uploads when the bundle carried them.
        if uploads_dir and os.path.isdir(uploads_dir):
            if UPLOAD_FOLDER.exists():
                shutil.rmtree(UPLOAD_FOLDER, ignore_errors=True)
            shutil.copytree(uploads_dir, str(UPLOAD_FOLDER))
        # Migrate the incoming DB forward to the current schema.
        init_database()
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': f'Replace failed: {exc}', 'backup_path': backup_path}), 500
    finally:
        _MAINTENANCE = False
    return jsonify({'success': True, 'backup_path': backup_path})
```

Confirm `import shutil` exists at the top of `dental_clinic.py`; add if missing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_data_tools_api.py -k "replace or maintenance" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_data_tools_api.py
git commit -m "feat(data-tools): replace endpoint with maintenance guard + live file swap"
```

---

## Task 12: Settings → Data Tools UI

**Files:**
- Modify: `templates.py` (Settings section of `HTML_TEMPLATE`; `translations` object — EN ~line 3008, AR ~line 3380)
- Test: manual `node --check` render sweep (see `reference_templates_js_escaping`)

**WARNING (templates.py JS escaping trap):** `HTML_TEMPLATE` is a normal Python string. A JS `'\n'` collapses to a real newline and breaks the whole inline script. Use `'\\n'` for any literal newline in JS, and verify with the render sweep below before committing.

- [ ] **Step 1: Locate the Settings markup**

Run: `python - <<'PY'`
```python
import re, pathlib
src = pathlib.Path('templates.py').read_text(encoding='utf-8')
i = src.find('download_backup')
print(src[i-400:i+400])
PY
```
Identify where the Download Backup button lives so the Data Tools card sits beside it in Settings.

- [ ] **Step 2: Add the Data Tools card markup**

Insert near the Download Backup button:

```html
<div class="card data-tools-card">
  <h3 data-i18n="data_tools">Data Tools</h3>
  <p class="muted" data-i18n="data_tools_hint">Export a portable copy, merge another clinic's data, or replace this database.</p>
  <div class="data-tools-actions">
    <button class="btn" onclick="exportBundle()" data-i18n="export_bundle">⬇️ Export bundle (.zip)</button>
    <label class="btn" for="merge-file" data-i18n="merge_db">🔀 Merge another clinic</label>
    <input type="file" id="merge-file" accept=".zip,.db" style="display:none" onchange="startDataImport('merge', this)">
    <label class="btn btn-danger" for="replace-file" data-i18n="replace_db">♻️ Replace database</label>
    <input type="file" id="replace-file" accept=".zip,.db" style="display:none" onchange="startDataImport('replace', this)">
  </div>
  <div id="data-tools-result" class="muted"></div>
</div>
```

- [ ] **Step 3: Add the JS handlers**

Add inside the existing `<script>` block (mind the escaping trap — use `\\n` not `\n`):

```javascript
function exportBundle() {
  window.location.href = '/api/data/export-bundle';
}

async function startDataImport(mode, input) {
  const file = input.files[0];
  input.value = '';
  if (!file) return;
  const verb = mode === 'replace' ? 'REPLACE' : 'MERGE';
  const warn = mode === 'replace'
    ? 'This REPLACES all current data with the imported file. A safety backup is taken first.'
    : "This MERGES the imported clinic's records into your current data. Existing data is kept.";
  const typed = prompt(warn + '\\n\\nType ' + verb + ' to confirm:');
  if (typed !== verb) return;
  const result = document.getElementById('data-tools-result');
  result.textContent = 'Working… do not close this window.';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const resp = await fetch('/api/data/' + mode, { method: 'POST', body: fd });
    const body = await resp.json();
    if (!resp.ok) { result.textContent = 'Error: ' + (body.error || resp.status); return; }
    if (mode === 'merge') {
      const r = body.report || {};
      result.textContent = 'Merged ' + (r.total_added || 0) + ' records. Backup: ' + (body.backup_path || '—');
    } else {
      result.textContent = 'Database replaced. Reloading… Backup: ' + (body.backup_path || '—');
      setTimeout(() => window.location.reload(), 1500);
    }
  } catch (e) {
    result.textContent = 'Error: ' + e;
  }
}
```

- [ ] **Step 4: Add translation keys (EN + AR)**

In the EN `translations` block (~line 3008) add:
```javascript
data_tools: 'Data Tools',
data_tools_hint: "Export a portable copy, merge another clinic's data, or replace this database.",
export_bundle: 'Export bundle (.zip)',
merge_db: 'Merge another clinic',
replace_db: 'Replace database',
```
In the AR block (~line 3380) add:
```javascript
data_tools: 'أدوات البيانات',
data_tools_hint: 'صدّر نسخة محمولة، أو ادمج بيانات عيادة أخرى، أو استبدل قاعدة البيانات.',
export_bundle: 'تصدير حزمة (.zip)',
merge_db: 'دمج عيادة أخرى',
replace_db: 'استبدال قاعدة البيانات',
```

- [ ] **Step 5: Verify JS syntax (render sweep) + commit**

Run:
```bash
python - <<'PY'
import templates, subprocess, re, tempfile, os
html = templates.HTML_TEMPLATE
for m in re.findall(r'<script>(.*?)</script>', html, re.S):
    f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
    f.write(m); f.close()
    r = subprocess.run(['node', '--check', f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode: print('JS SYNTAX ERROR:', r.stderr); raise SystemExit(1)
print('all inline scripts parse OK')
PY
```
Expected: `all inline scripts parse OK`.

```bash
git add templates.py
git commit -m "feat(data-tools): Settings Data Tools card (export/merge/replace) + EN/AR strings"
```

---

## Task 13: README + full-suite green

**Files:**
- Modify: `README.md`
- Verify: whole test suite

- [ ] **Step 1: Update README**

- In **Features → Access Control & Security** (or a new "Data tools" bullet under Backups), document: Settings → Data Tools with Export bundle, Merge another clinic (additive, never overwrites; deduped catalogs; images need the .zip bundle), Replace database (safety backup + live swap).
- In **REST API Reference → Administration**, add:
  | GET | `/api/data/export-bundle` | Login. Zip of DB snapshot + uploads |
  | POST | `/api/data/merge` | Login. Additive merge of an uploaded `.db`/`.zip`; returns a report |
  | POST | `/api/data/replace` | Login. Replace current DB with the uploaded one (safety backup first) |
- In **Project Structure**, add `db_merge.py` and `db_import.py` lines and the three new test files; bump the test count.

- [ ] **Step 2: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (check `$LASTEXITCODE` is 0 — the summary may be suppressed by tooling).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document Data Tools (export/merge/replace) endpoints + structure"
```

---

## Task 14: Code review

- [ ] **Step 1:** Invoke the **code-reviewer** agent on the diff (`db_merge.py`, `db_import.py`, the `dental_clinic.py` routes, `templates.py`). Pay attention to: SQL injection (all table names come from hard-coded lists, never user input — confirm), file-handling safety, transaction/rollback correctness, and the maintenance-guard window.
- [ ] **Step 2:** Invoke the **security-reviewer** agent (file upload + path traversal + auth gating are the sensitive surface).
- [ ] **Step 3:** Address CRITICAL/HIGH findings; re-run `python -m pytest tests/ -q`.
- [ ] **Step 4:** Commit any fixes.

---

## Self-Review (completed during planning)

**Spec coverage:**
- Replace ✓ (Task 11) · Merge additive ✓ (Tasks 2–6, 10) · keep-patients-separate ✓ (no patient dedup; only catalogs dedupe, Task 3) · medical images ✓ (Task 5) · credit balances ✓ (Task 6 orchestration) · holidays excluded ✓ (not in `_GENERIC_ORDER`/specials) · `db_merge.py` module ✓ · zip bundle + bare .db ✓ (Tasks 8, 10) · live swap ✓ (Task 11) · catalog dedupe forced by UNIQUE ✓ · schema-drift tolerance ✓ (Tasks 2, 7) · login gate ✓ (Tasks 9–11) · SQLite-magic + zip-slip validation ✓ (Task 8) · typed confirmation ✓ (Task 12) · auto safety backup + returned path ✓ (Tasks 10, 11) · cloud-node disabled ✓ (Tasks 9–11) · UI ✓ (Task 12) · tests ✓ (Tasks 1–11) · README ✓ (Task 13).

**Placeholder scan:** none — every code/test step contains complete content.

**Type/name consistency:** `MergeReport` (`.add`, `.total_added`, `.as_dict`, `.images_copied`, `.images_skipped`, `.warnings`), `_copy_table`, `_dedupe_catalog`, `_copy_expenses`, `_copy_medical_images`, `_remap_value`, `_dst_columns`, `merge_database`, `_recompute_balances` — consistent across tasks. Route names `data_export_bundle`/`data_merge`/`data_replace` and `_MAINTENANCE`/`_maintenance_gate`/`_save_and_resolve_upload` consistent. `db_import.is_sqlite_file`/`build_bundle`/`extract_bundle` consistent.

**Note for the implementer:** if the installed SQLite rejects `ALTER TABLE … DROP COLUMN` (Task 7), build that test's source DB from a hand-written `CREATE TABLE patients(...)` lacking the `notes` column instead — the engine behavior under test is unchanged.
