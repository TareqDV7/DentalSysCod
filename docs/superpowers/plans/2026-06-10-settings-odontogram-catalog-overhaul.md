# Settings, Odontogram & Catalog Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the desktop Settings page (foldable Audit Log), fix and extend the odontogram so a tooth can carry multiple describable conditions, and ship empty catalogs (no demo seed + a clear-catalogs action), keeping desktop and Flutter in parity.

**Architecture:** Multi-condition rides the existing `patient_tooth_chart` sync table — drop the "one row per tooth" dedupe so a tooth holds N rows (one per condition + note). The GET response shape changes from a single `condition_id` to a `conditions[]` list; all consumers (desktop JS, Flutter, tests) are in this repo and updated together. Catalog clear is a soft-delete (`active=0`) + tombstone so it propagates over sync. Settings + chart redraw are presentational.

**Tech Stack:** Python 3 / Flask / SQLite (`dental_clinic.py`), inline HTML/CSS/JS portal (`templates.py`), Flutter/Dart (`clinic_mobile_app/`), pytest, flutter_test.

**Spec:** `docs/superpowers/specs/2026-06-10-settings-odontogram-catalog-overhaul-design.md`

**Conventions:**
- Run Python tests with `python -m pytest tests/ -q` (RTK note: `rtk pytest` suppresses the summary — check `$LASTEXITCODE`). Single test: `python -m pytest tests/test_x.py::test_y -q`.
- `templates.py` `HTML_TEMPLATE` is a **normal Python string**: a literal `'\n'` inside inline JS collapses to a real newline and breaks the whole script — always double-escape (`'\\n'`). Verify JS edits with a `node --check` render sweep (see Task 6.2).
- Flutter: `cd clinic_mobile_app && flutter test`, `dart analyze`, `dart format .`.
- Commit after each task. Conventional-commit messages. No attribution trailer (disabled globally).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `dental_clinic.py` | seeds, tooth-chart GET/POST, clear-catalogs endpoint | Modify |
| `templates.py` | Settings layout, odontogram SVG + popup, Data Tools button, i18n | Modify |
| `clinic_mobile_app/lib/models/tooth_chart_entry.dart` | per-tooth `conditions[]` model | Modify |
| `clinic_mobile_app/lib/services/tooth_chart_service.dart` | parse new shape + replace-set write | Modify |
| `clinic_mobile_app/lib/screens/odontogram_view.dart` | banded painter + multi-select sheet | Modify |
| `tests/test_tooth_chart_api.py` | multi-condition contract | Rewrite cases |
| `tests/test_tooth_chart_badges.py` | badges with `conditions[]` | Modify |
| `tests/test_tooth_chart_sync.py` | multi-row export/import | Modify |
| `tests/test_data_tools_api.py` | clear-catalogs cases | Add cases |
| `tests/test_catalog_migration.py` | seed-count assumptions | Adjust |
| `clinic_mobile_app/test/...` | service parse + widget | Modify |

---

# Phase 1 — Empty the catalogs

### Task 1.1: Remove demo seeds from `init_database()`

**Files:**
- Modify: `dental_clinic.py:1165-1195` (`default_procedures`, `default_tooth_conditions`)
- Test: `tests/test_catalog_migration.py`, a new `tests/test_seed_empty.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_seed_empty.py`:

```python
"""A fresh database ships with empty catalogs (no demo seed)."""
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    return str(db)


def test_no_seeded_procedures(fresh_db):
    conn = sqlite3.connect(fresh_db)
    n = conn.execute('SELECT COUNT(*) FROM treatment_procedures').fetchone()[0]
    conn.close()
    assert n == 0


def test_no_seeded_tooth_conditions(fresh_db):
    conn = sqlite3.connect(fresh_db)
    n = conn.execute('SELECT COUNT(*) FROM tooth_conditions').fetchone()[0]
    conn.close()
    assert n == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_seed_empty.py -q`
Expected: FAIL — counts are 9 and 8 (seeds still present).

- [ ] **Step 3: Remove the seed blocks**

In `dental_clinic.py`, delete the `default_procedures = [...]` list **and** its `cursor.executemany('''INSERT OR IGNORE INTO treatment_procedures ...''', default_procedures)` call (lines ~1165-1179), and delete the `default_tooth_conditions = [...]` list **and** its `cursor.executemany('''INSERT OR IGNORE INTO tooth_conditions ...''', default_tooth_conditions)` call (lines ~1181-1195). Leave the legacy `treatment_catalog` migration block that follows untouched.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_seed_empty.py -q`
Expected: PASS.

- [ ] **Step 5: Fix any seed-dependent tests**

Run: `python -m pytest tests/test_catalog_migration.py -q`
If a test assumed seeded rows exist, change it to insert its own procedure rows first (via `client.post('/api/treatment-procedures', json={'name': 'X'})` or a direct `INSERT`). Do **not** weaken what the test actually checks (the legacy→new migration); just stop relying on the removed seed.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_seed_empty.py tests/test_catalog_migration.py
git commit -m "feat(catalog): ship empty catalogs — remove demo procedure/condition seeds"
```

---

### Task 1.2: `POST /api/data/clear-catalogs` endpoint

**Files:**
- Modify: `dental_clinic.py` (after `data_replace`, near line 3776+)
- Test: `tests/test_data_tools_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_tools_api.py` (mirror its existing `client` fixture; if it logs in, reuse that helper — the endpoint sits under the same `/api/data/` gate):

```python
def test_clear_catalogs_soft_deletes_and_tombstones(client):
    # seed a procedure + a condition through the API
    client.post('/api/treatment-procedures', json={'name': 'Cleaning', 'default_price': 200})
    client.post('/api/tooth-conditions', json={'name': 'Decay', 'color': '#ef4444'})

    r = client.post('/api/data/clear-catalogs')
    assert r.status_code == 200
    body = r.get_json()
    assert body['procedures_cleared'] >= 1
    assert body['conditions_cleared'] >= 1

    # active lists are now empty
    assert client.get('/api/treatment-procedures').get_json() == []
    assert client.get('/api/tooth-conditions').get_json() == []

    # deletions are tombstoned for both tables
    import sqlite3, dental_clinic
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    tp = conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='treatment_procedures'").fetchone()[0]
    tc = conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='tooth_conditions'").fetchone()[0]
    conn.close()
    assert tp >= 1 and tc >= 1


def test_clear_catalogs_blocked_on_cloud_node(client, monkeypatch):
    import dental_clinic
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert client.post('/api/data/clear-catalogs').status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_data_tools_api.py -q -k clear_catalogs`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Implement the endpoint**

Add after the `data_replace` function in `dental_clinic.py`:

```python
@app.route('/api/data/clear-catalogs', methods=['POST'])
def data_clear_catalogs():
    """Soft-delete + tombstone every procedure and tooth-condition row.

    Patient data is untouched. Tombstones propagate the wipe to the cloud
    node and paired phones on the next sync. Disabled on the cloud node.
    """
    if CLOUD_MODE:
        return jsonify({'error': 'Not available on the cloud node'}), 404
    conn = sqlite3.connect(str(DB_NAME))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    procedures = 0
    conditions = 0
    cursor.execute('SELECT id FROM treatment_procedures WHERE active = 1')
    for row in cursor.fetchall():
        cursor.execute('UPDATE treatment_procedures SET active = 0 WHERE id = ?', (row['id'],))
        record_tombstone(cursor, 'treatment_procedures', row['id'])
        procedures += 1
    cursor.execute('SELECT id FROM tooth_conditions WHERE active = 1')
    for row in cursor.fetchall():
        cursor.execute('UPDATE tooth_conditions SET active = 0 WHERE id = ?', (row['id'],))
        record_tombstone(cursor, 'tooth_conditions', row['id'])
        conditions += 1
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'procedures_cleared': procedures, 'conditions_cleared': conditions})
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_data_tools_api.py -q -k clear_catalogs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_data_tools_api.py
git commit -m "feat(data-tools): add clear-catalogs endpoint (soft-delete + tombstone, cloud-disabled)"
```

---

# Phase 2 — Multi-condition tooth-chart backend

### Task 2.1: GET returns `conditions[]` per tooth

**Files:**
- Modify: `dental_clinic.py:3055-3135` (GET branch of `patient_tooth_chart_collection`)
- Test: `tests/test_tooth_chart_api.py`

- [ ] **Step 1: Rewrite the affected tests for the new shape**

In `tests/test_tooth_chart_api.py`, replace `test_upsert_then_update_keeps_one_row` with the multi-condition behavior and update `_condition_id` usage. Add:

```python
def _post_conditions(client, pid, tooth, items):
    return client.post(f'/api/patients/{pid}/tooth-chart',
                       json={'tooth_no': tooth, 'conditions': items})


def test_get_returns_conditions_list(client):
    pid = _patient()
    decay = _condition_id(client, 'Decay')   # NOTE: test seeds these itself now (see Step 2)
    crown = _condition_id(client, 'Crown')
    _post_conditions(client, pid, '16', [
        {'condition_id': decay, 'note': 'distal'},
        {'condition_id': crown, 'note': 'PFM'},
    ])
    teeth = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']
    conds = teeth['16']['conditions']
    names = {c['condition_name'] for c in conds}
    assert names == {'Decay', 'Crown'}
    notes = {c['condition_name']: c['note'] for c in conds}
    assert notes['Decay'] == 'distal' and notes['PFM' if False else 'Crown'] == 'PFM'
    assert all('color' in c and 'condition_id' in c for c in conds)
```

- [ ] **Step 2: Make condition seeding explicit (seeds are gone)**

Since Phase 1 removed seeded conditions, add a helper at the top of the test module and call it in tests that need conditions:

```python
def _seed_conditions(client):
    for name, color in [('Decay', '#ef4444'), ('Crown', '#a855f7'),
                        ('Root canal', '#f59e0b'), ('Filled', '#3b82f6')]:
        client.post('/api/tooth-conditions', json={'name': name, 'color': color})
```

Call `_seed_conditions(client)` at the start of every test that uses `_condition_id(...)`.

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_tooth_chart_api.py::test_get_returns_conditions_list -q`
Expected: FAIL — `teeth['16']` has no `conditions` key (old shape).

- [ ] **Step 4: Rewrite the GET branch**

Replace the teeth-building block (lines ~3063-3079) so rows group into a `conditions` list, and update the two legacy auto-adopt blocks + badge loop to use the new shape. New GET body from line ~3055:

```python
    # --- GET ---
    cursor.execute('''
        SELECT id, name, name_ar, color, icon, sort_order
        FROM tooth_conditions WHERE active = 1
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
    ''')
    conditions = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
        SELECT c.tooth_no, c.condition_id, c.note,
               tc.name AS condition_name, tc.color AS color, tc.sort_order AS sort_order
        FROM patient_tooth_chart c
        LEFT JOIN tooth_conditions tc ON tc.id = c.condition_id
        WHERE c.patient_id = ?
        ORDER BY COALESCE(tc.sort_order, 999) ASC, c.updated_at ASC
    ''', (patient_id,))
    teeth = {}
    for r in cursor.fetchall():
        entry = teeth.setdefault(r['tooth_no'], {'conditions': [], 'source': 'chart'})
        entry['conditions'].append({
            'condition_id': r['condition_id'],
            'condition_name': r['condition_name'],
            'color': r['color'],
            'note': r['note'],
        })

    # Legacy auto-adopt: surface valid-FDI teeth that have a follow-up or a plan
    # but no explicit chart row, so badges show before the tooth is charted.
    def _adopt(tooth_no):
        if _is_valid_fdi(tooth_no) and tooth_no not in teeth:
            teeth[tooth_no] = {'conditions': [], 'source': 'legacy'}

    cursor.execute(
        'SELECT DISTINCT tooth_no FROM patient_followups '
        'WHERE patient_id = ? AND tooth_no IS NOT NULL AND COALESCE(is_deleted, 0) = 0',
        (patient_id,),
    )
    for r in cursor.fetchall():
        _adopt(r['tooth_no'])

    cursor.execute(
        '''SELECT DISTINCT tpt.tooth_no
           FROM treatment_plan_teeth tpt
           JOIN treatment_plans tp ON tpt.plan_id = tp.id
           WHERE tp.patient_id = ? AND tpt.tooth_no IS NOT NULL''',
        (patient_id,),
    )
    for r in cursor.fetchall():
        _adopt(r['tooth_no'])
```

Leave the two badge queries (`balance_map`, `plan_teeth`) unchanged, and keep the final badge loop as-is (it still sets `entry['unpaid_balance']` / `entry['has_plan']` on each entry dict). The final `return jsonify({'conditions': conditions, 'teeth': teeth})` is unchanged.

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_tooth_chart_api.py::test_get_returns_conditions_list -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_api.py
git commit -m "feat(odontogram): tooth-chart GET returns conditions[] per tooth"
```

---

### Task 2.2: POST replaces a tooth's full condition set

**Files:**
- Modify: `dental_clinic.py:3007-3053` (POST branch)
- Test: `tests/test_tooth_chart_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tooth_chart_api.py`:

```python
def test_post_conditions_replaces_set(client):
    _seed_conditions(client)
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    crown = _condition_id(client, 'Crown')
    rc = _condition_id(client, 'Root canal')
    _post_conditions(client, pid, '16', [{'condition_id': decay}, {'condition_id': crown}])
    # replace: drop decay, keep crown, add root canal
    _post_conditions(client, pid, '16', [{'condition_id': crown}, {'condition_id': rc}])
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert {c['condition_name'] for c in conds} == {'Crown', 'Root canal'}
    # removed condition is tombstoned
    import sqlite3, dental_clinic
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    n = conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='patient_tooth_chart'").fetchone()[0]
    conn.close()
    assert n >= 1


def test_post_empty_conditions_clears_tooth(client):
    _seed_conditions(client)
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    _post_conditions(client, pid, '16', [{'condition_id': decay}])
    assert _post_conditions(client, pid, '16', []).status_code == 200
    assert '16' not in client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']


def test_post_legacy_single_condition_still_works(client):
    _seed_conditions(client)
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    client.post(f'/api/patients/{pid}/tooth-chart', json={'tooth_no': '16', 'condition_id': decay})
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert [c['condition_name'] for c in conds] == ['Decay']


def test_post_dedupes_repeated_condition(client):
    _seed_conditions(client)
    pid = _patient()
    decay = _condition_id(client, 'Decay')
    _post_conditions(client, pid, '16', [{'condition_id': decay}, {'condition_id': decay, 'note': 'x'}])
    conds = client.get(f'/api/patients/{pid}/tooth-chart').get_json()['teeth']['16']['conditions']
    assert len(conds) == 1
```

Keep `test_invalid_fdi_rejected_on_upsert`, `test_unknown_condition_rejected` (call `_seed_conditions` where needed), and `test_delete_endpoint_clears_tooth`. Delete the obsolete `test_null_condition_clears_tooth` (superseded by `test_post_empty_conditions_clears_tooth`).

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_tooth_chart_api.py -q -k "post_conditions or empty_conditions or legacy_single or dedupes"`
Expected: FAIL — POST ignores `conditions`.

- [ ] **Step 3: Rewrite the POST branch**

Replace lines ~3007-3053 with:

```python
    if request.method == 'POST':
        data = request.json or {}
        tooth_no = str(data.get('tooth_no') or '').strip()
        if not _is_valid_fdi(tooth_no):
            conn.close()
            return jsonify({'error': 'Invalid FDI tooth number'}), 400

        # New multi-condition shape; tolerate the legacy single {condition_id, note}.
        if 'conditions' in data:
            raw = data.get('conditions') or []
        else:
            cid = data.get('condition_id')
            raw = [] if cid in (None, '', 0, '0') else [{'condition_id': cid, 'note': data.get('note')}]

        requested = []          # [(condition_id:int, note)]
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            cid = item.get('condition_id')
            if cid in (None, '', 0, '0'):
                continue
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                conn.close()
                return jsonify({'error': 'Invalid condition_id'}), 400
            if cid in seen:
                continue
            seen.add(cid)
            requested.append((cid, (item.get('note') or None)))

        for cid, _ in requested:
            cursor.execute('SELECT id FROM tooth_conditions WHERE id = ?', (cid,))
            if cursor.fetchone() is None:
                conn.close()
                return jsonify({'error': 'Unknown condition_id'}), 400

        cursor.execute(
            'SELECT id, condition_id FROM patient_tooth_chart WHERE patient_id = ? AND tooth_no = ?',
            (patient_id, tooth_no),
        )
        existing_by_cond = {}
        for row in cursor.fetchall():
            existing_by_cond.setdefault(row['condition_id'], []).append(row['id'])

        requested_ids = {cid for cid, _ in requested}

        # Remove rows whose condition is no longer requested.
        for cond_id, ids in existing_by_cond.items():
            if cond_id not in requested_ids:
                for rid in ids:
                    cursor.execute('DELETE FROM patient_tooth_chart WHERE id = ?', (rid,))
                    record_tombstone(cursor, 'patient_tooth_chart', rid)

        # Upsert each requested condition (collapse any duplicate rows to one).
        for cid, note in requested:
            ids = existing_by_cond.get(cid, [])
            if ids:
                cursor.execute(
                    'UPDATE patient_tooth_chart SET condition_id = ?, note = ? WHERE id = ?',
                    (cid, note, ids[0]),
                )
                for extra in ids[1:]:
                    cursor.execute('DELETE FROM patient_tooth_chart WHERE id = ?', (extra,))
                    record_tombstone(cursor, 'patient_tooth_chart', extra)
            else:
                cursor.execute(
                    'INSERT INTO patient_tooth_chart (patient_id, tooth_no, condition_id, note) VALUES (?, ?, ?, ?)',
                    (patient_id, tooth_no, cid, note),
                )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_tooth_chart_api.py -q`
Expected: PASS (whole file).

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_tooth_chart_api.py
git commit -m "feat(odontogram): tooth-chart POST replaces a tooth's full condition set"
```

---

### Task 2.3: Badges + sync tests for the new shape

**Files:**
- Modify: `tests/test_tooth_chart_badges.py`, `tests/test_tooth_chart_sync.py`

- [ ] **Step 1: Update badge tests**

In `tests/test_tooth_chart_badges.py`: any access to `teeth['16']['condition_id']` / `['condition_name']` becomes `teeth['16']['conditions']` (a list). Auto-adopted legacy teeth now assert `teeth[t]['conditions'] == []` and still carry `has_plan` / `unpaid_balance`. Add `_seed_conditions` where conditions are needed. Run:

`python -m pytest tests/test_tooth_chart_badges.py -q` → fix until PASS.

- [ ] **Step 2: Update sync test for multiple rows per tooth**

In `tests/test_tooth_chart_sync.py`: add/adjust a case that POSTs two conditions to one tooth, calls `/api/sync/export`, and asserts **two** `patient_tooth_chart` rows for that `(patient_id, tooth_no)` appear in the export; then a removal POSTs one condition and asserts a tombstone for the dropped row propagates. Run:

`python -m pytest tests/test_tooth_chart_sync.py -q` → fix until PASS.

- [ ] **Step 3: Full backend sweep**

Run: `python -m pytest tests/ -q` then check `echo $LASTEXITCODE` (PowerShell: `$LASTEXITCODE`).
Expected: 0. Fix any other test that read the old single-condition shape (grep: `condition_name'\]` / `'condition_id'\]` under `tests/`).

- [ ] **Step 4: Commit**

```bash
git add tests/test_tooth_chart_badges.py tests/test_tooth_chart_sync.py
git commit -m "test(odontogram): badges + sync cover multi-condition shape"
```

---

# Phase 3 — Desktop chart redraw + multi-select popup

### Task 3.1: Diagnose the current chart (screenshot)

**Files:** none (investigation)

- [ ] **Step 1: Capture the live chart**

Follow the web-visual-smoke recipe: fresh temp DB → unlicensed gate → login `admin`/`admin` → create a patient → POST a couple of tooth conditions + chart entries → open the patient profile → Playwright screenshots of `#odontogram-card` in light/dark and EN/AR (toggle via `data-theme` / language). Save to a scratch dir (git-ignored).

- [ ] **Step 2: Record findings**

Write 2-4 bullet notes in the PR/commit body: exactly what reads wrong (shape legibility, number placement, RTL mirroring, upper/lower alignment). These drive the geometry in 3.2-3.3. No code change here.

---

### Task 3.2: Redraw tooth shapes + lock arch to LTR

**Files:**
- Modify: `templates.py` — `TOOTH_PATHS` (~6307), `buildToothRowSvg` (~6315), `buildToothArchSvg` (~6337), `.arch` CSS (~1721 area)

- [ ] **Step 1: Replace `TOOTH_PATHS` with clearer, distinct silhouettes**

In `templates.py`, replace the `TOOTH_PATHS` object. Crowns differ by class (molar widest/multi-cusp, premolar two cusps, canine pointed, incisor flat blade) over a 40×56 drawing box:

```javascript
        const TOOTH_PATHS = {
          // crown on top (y small), root tapering toward y=56
          molar:    'M5,16 Q5,9 10,9 Q12,5 15,9 Q20,5 25,9 Q28,5 30,9 Q35,9 35,16 Q37,24 33,30 L33,40 Q33,50 28,54 Q24,56 22,52 Q20,56 16,54 Q11,50 11,40 L11,30 Q3,24 5,16 Z',
          premolar: 'M9,16 Q9,9 15,9 Q17,5 20,9 Q23,5 25,9 Q31,9 31,16 Q33,23 29,29 L29,40 Q29,50 24,54 Q20,56 16,52 Q11,50 11,40 L11,29 Q7,23 9,16 Z',
          canine:   'M20,4 Q25,10 27,18 Q29,24 26,30 L26,42 Q26,52 22,55 Q20,56 18,54 Q14,52 14,42 L14,30 Q11,24 13,18 Q15,10 20,4 Z',
          incisor:  'M12,8 Q12,6 20,6 Q28,6 28,8 Q30,16 27,26 L26,42 Q26,52 22,55 Q20,56 18,54 Q14,52 14,42 L13,26 Q10,16 12,8 Z',
        };
```

- [ ] **Step 2: Lock the arch container to LTR**

In the `.arch` / `.odontogram-card` CSS block (near line 1721), add `direction: ltr;` to the arch rows so Arabic RTL never mirrors the anatomical tooth order:

```css
        .odontogram-card .arch { direction: ltr; }
```

(If `.arch` has no rule yet, add one.)

- [ ] **Step 3: Add a quadrant midline separator**

In `buildToothRowSvg`, after the cells loop, draw a faint vertical divider at the arch midline (between index 7 and 8 of the 16-tooth row). Insert before building the `<svg>`:

```javascript
          const midX = 8 * cellW + pad;  // between tooth 8 and 9 of the row
          const midline = `<line x1="${midX}" y1="2" x2="${midX}" y2="${cellH-2}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3 3"/>`;
          const w = fdiList.length * cellW + pad * 2;
          return `<svg viewBox="0 0 ${w} ${cellH}" width="100%" preserveAspectRatio="xMidYMid meet" class="tooth-row">${midline}${cells}</svg>`;
```

(Remove the old `const w = ...; return ...` lines this replaces.)

- [ ] **Step 4: Render + visually verify**

Re-run the screenshot recipe from 3.1. Confirm: four classes look distinct, numbers legible, EN and AR identical arch order, 18 above 48 … 28 above 38. Nudge path coordinates if a class still reads wrong.

- [ ] **Step 5: `node --check` the inline JS, then commit**

Run a render sweep (Task 6.2 command). Then:

```bash
git add templates.py
git commit -m "fix(odontogram): redraw distinct tooth shapes, midline separator, LTR-locked arch"
```

---

### Task 3.3: Banded multi-condition fill (desktop SVG)

**Files:**
- Modify: `templates.py` — `buildToothRowSvg` (~6315)

- [ ] **Step 1: Replace single-fill with clipped color bands**

Rewrite the per-tooth body of `buildToothRowSvg` so it reads `entry.conditions` (the new shape) and paints one horizontal band per condition, clipped to the tooth path. Replace the `fill`/`stroke`/`path` lines inside the `forEach`:

```javascript
          fdiList.forEach((fdi, i) => {
            const x = i * cellW + pad;
            const entry = (chart.teeth || {})[fdi];
            const conds = (entry && entry.conditions) ? entry.conditions : [];
            const ty = isLower ? 6 : 14;
            const xform = `translate(${x},${ty}) ${isLower ? 'rotate(180 20 28)' : ''}`;
            const pathD = TOOTH_PATHS[fdiToothClass(fdi)];
            const stroke = conds.length ? '#334155' : '#94a3b8';

            let fillSvg;
            if (conds.length === 0) {
              fillSvg = `<path d="${pathD}" transform="${xform}" fill="transparent" stroke="${stroke}" stroke-width="1.5"/>`;
            } else {
              const clipId = `tc-${fdi}-${isLower ? 'l' : 'u'}`;
              const bandH = 56 / conds.length;
              const bands = conds.map((c, bi) =>
                `<rect x="0" y="${bi * bandH}" width="40" height="${bandH}" fill="${c.color || '#cbd5e1'}"/>`
              ).join('');
              fillSvg =
                `<clipPath id="${clipId}"><path d="${pathD}"/></clipPath>` +
                `<g transform="${xform}"><g clip-path="url(#${clipId})">${bands}</g>` +
                `<path d="${pathD}" fill="none" stroke="${stroke}" stroke-width="1.5"/></g>`;
            }

            const dot = entry && entry.has_plan
              ? `<circle cx="${x+34}" cy="6" r="4" fill="#7c3aed"><title>${t('has_plan','Has plan')}</title></circle>` : '';
            const warn = entry && entry.unpaid_balance > 0
              ? `<circle cx="${x+34}" cy="${cellH-8}" r="4" fill="#f59e0b"><title>${t('unpaid','Unpaid')}: ₪ ${entry.unpaid_balance.toFixed(2)}</title></circle>` : '';
            const label = `<text x="${x+20}" y="${isLower ? cellH-1 : 10}" text-anchor="middle" class="tooth-num">${fdi}</text>`;
            const titleNames = conds.map(c => c.condition_name).filter(Boolean).join(', ');
            const titleTag = titleNames ? `<title>${fdi}: ${titleNames}</title>` : '';
            cells += `<g class="tooth" data-fdi="${fdi}" tabindex="0" role="button" aria-label="${t('tooth','Tooth')} ${fdi}">${titleTag}${fillSvg}${label}${dot}${warn}</g>`;
          });
```

Note: the clip path is defined inside the transformed `<g>`, so the clip path coordinates are the untransformed tooth path (correct — `clipPath` without `clipPathUnits` uses userSpace at reference time; defining it inside the same `<g transform>` keeps clip + bands + outline in one transformed space).

- [ ] **Step 2: Verify single + multi rendering**

Screenshot a tooth with 1 condition (solid fill) and a tooth with 2-3 (equal horizontal bands). Confirm the outline sits on top and the lower-arch rotation still bands top→bottom acceptably (bands rotate with the tooth — acceptable; if it reads oddly, drop the `rotate(180)` and instead flip only the silhouette by using a separate lower path — keep simple unless the screenshot demands it).

- [ ] **Step 3: `node --check` + commit**

```bash
git add templates.py
git commit -m "feat(odontogram): banded multi-condition fill on the web chart"
```

---

### Task 3.4: Multi-select tooth popup (desktop)

**Files:**
- Modify: `templates.py` — `#tooth-popup` markup (near the odontogram card / popup block), `openToothPopup` (~6410), the save handler (~6430)

- [ ] **Step 1: Locate and replace the popup body markup**

Find the `#tooth-popup` element (contains `#tooth-popup-title`, `#tooth-popup-condition`, `#tooth-popup-note`, `#tooth-popup-save`, `#tooth-popup-log`, `#tooth-popup-close`). Replace the single condition `<select>` and single note `<input>` with a chips container + a per-condition notes container:

```html
                <div id="tooth-popup-conditions" class="tooth-chip-row"></div>
                <div id="tooth-popup-notes"></div>
```

Add CSS near the odontogram styles:

```css
        .tooth-chip-row { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; }
        .tooth-chip { display:inline-flex; align-items:center; gap:6px; padding:6px 10px;
            border-radius:999px; border:1.5px solid var(--border,#cbd5e1); cursor:pointer;
            font-size:0.86em; user-select:none; }
        .tooth-chip i { width:12px; height:12px; border-radius:3px; display:inline-block; }
        .tooth-chip.selected { border-color:#334155; font-weight:600; }
        .tooth-note-row { display:flex; align-items:center; gap:8px; margin:6px 0; }
        .tooth-note-row label { font-size:0.8em; min-width:90px; color:var(--muted); }
```

- [ ] **Step 2: Rewrite `openToothPopup` to render chips + notes**

```javascript
        let _popupSel = {};   // {condition_id: note}

        function _renderToothNotes() {
          const wrap = document.getElementById('tooth-popup-notes');
          wrap.innerHTML = Object.keys(_popupSel).map(cid => {
            const c = currentChartConditions.find(x => String(x.id) === String(cid));
            const nm = c ? ((currentLanguage==='ar' && c.name_ar) ? c.name_ar : c.name) : cid;
            const val = (_popupSel[cid] || '').replace(/"/g, '&quot;');
            return `<div class="tooth-note-row"><label>${nm}</label>`
                 + `<input type="text" data-note-for="${cid}" value="${val}" `
                 + `placeholder="${t('note','Note')}" style="flex:1;"></div>`;
          }).join('');
          wrap.querySelectorAll('input[data-note-for]').forEach(inp => {
            inp.addEventListener('input', e => { _popupSel[e.target.dataset.noteFor] = e.target.value; });
          });
        }

        function openToothPopup(patientId, fdi, chart) {
          _popupPatientId = patientId; _popupFdi = fdi;
          const entry = (chart.teeth || {})[fdi] || {};
          document.getElementById('tooth-popup-title').textContent = `${t('tooth','Tooth')} ${fdi}`;
          _popupSel = {};
          (entry.conditions || []).forEach(c => { _popupSel[c.condition_id] = c.note || ''; });
          const row = document.getElementById('tooth-popup-conditions');
          row.innerHTML = currentChartConditions
            .filter(c => c.name !== 'Healthy')
            .map(c => {
              const nm = (currentLanguage==='ar' && c.name_ar) ? c.name_ar : c.name;
              const on = Object.prototype.hasOwnProperty.call(_popupSel, String(c.id)) ||
                         Object.prototype.hasOwnProperty.call(_popupSel, c.id);
              return `<span class="tooth-chip${on ? ' selected' : ''}" data-cid="${c.id}">`
                   + `<i style="background:${c.color}"></i>${nm}</span>`;
            }).join('');
          row.querySelectorAll('.tooth-chip').forEach(chip => {
            chip.addEventListener('click', () => {
              const cid = chip.dataset.cid;
              if (Object.prototype.hasOwnProperty.call(_popupSel, cid)) { delete _popupSel[cid]; chip.classList.remove('selected'); }
              else { _popupSel[cid] = ''; chip.classList.add('selected'); }
              _renderToothNotes();
            });
          });
          _renderToothNotes();
          document.getElementById('tooth-popup').style.display = 'flex';
        }
```

- [ ] **Step 3: Rewrite the save handler to POST `conditions[]`**

```javascript
        document.getElementById('tooth-popup-save').addEventListener('click', async () => {
          const conditions = Object.keys(_popupSel).map(cid => ({
            condition_id: parseInt(cid, 10),
            note: (_popupSel[cid] || '').trim() || null,
          }));
          await fetch(`/api/patients/${_popupPatientId}/tooth-chart`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tooth_no: _popupFdi, conditions }),
          });
          closeToothPopup();
          renderOdontogram(_popupPatientId);
        });
```

Add an `note: 'Note'` / `note: 'ملاحظة'` key to the EN and AR `translations` objects in `templates.py` (search the existing `tooth_no:` key to find both objects).

- [ ] **Step 4: `node --check` render sweep + manual click-through**

Screenshot: open a tooth, toggle two chips, type notes, save, reopen — selections + notes persist; deselect all + save clears the tooth.

- [ ] **Step 5: Commit**

```bash
git add templates.py
git commit -m "feat(odontogram): multi-select tooth popup with per-condition notes (web)"
```

---

# Phase 4 — Mobile parity

### Task 4.1: `ToothChartEntry` holds a `conditions` list

**Files:**
- Modify: `clinic_mobile_app/lib/models/tooth_chart_entry.dart`
- Test: `clinic_mobile_app/test/tooth_chart_service_test.dart` (create if absent)

- [ ] **Step 1: Write the failing parse test**

Create/extend `clinic_mobile_app/test/tooth_chart_service_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/tooth_chart_service.dart';

void main() {
  test('parses conditions[] per tooth', () {
    final chart = parseToothChart({
      'conditions': [
        {'id': 1, 'name': 'Decay', 'color': '#ef4444'},
        {'id': 2, 'name': 'Crown', 'color': '#a855f7'},
      ],
      'teeth': {
        '16': {
          'conditions': [
            {'condition_id': 1, 'condition_name': 'Decay', 'color': '#ef4444', 'note': 'distal'},
            {'condition_id': 2, 'condition_name': 'Crown', 'color': '#a855f7', 'note': null},
          ],
          'has_plan': true,
          'unpaid_balance': 120.0,
          'source': 'chart',
        },
      },
    });
    final t = chart.teeth['16']!;
    expect(t.conditions.length, 2);
    expect(t.conditions.first.name, 'Decay');
    expect(t.conditions.first.note, 'distal');
    expect(t.hasPlan, true);
    expect(t.unpaidBalance, 120.0);
  });

  test('legacy tooth with empty conditions still carries badges', () {
    final chart = parseToothChart({
      'conditions': [],
      'teeth': {'21': {'conditions': [], 'has_plan': false, 'unpaid_balance': 50.0, 'source': 'legacy'}},
    });
    expect(chart.teeth['21']!.conditions, isEmpty);
    expect(chart.teeth['21']!.unpaidBalance, 50.0);
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd clinic_mobile_app && flutter test test/tooth_chart_service_test.dart`
Expected: FAIL — `ToothChartEntry` has no `conditions`.

- [ ] **Step 3: Rewrite the model**

Replace `clinic_mobile_app/lib/models/tooth_chart_entry.dart`:

```dart
/// One condition tagged on a tooth (web GET shape: teeth[fdi].conditions[]).
class ToothConditionTag {
  final int conditionId;
  final String? conditionName;
  final String? color;
  final String? note;

  const ToothConditionTag({
    required this.conditionId,
    this.conditionName,
    this.color,
    this.note,
  });

  String get name => conditionName ?? '';

  factory ToothConditionTag.fromJson(Map<String, dynamic> j) => ToothConditionTag(
        conditionId: j['condition_id'] is int
            ? j['condition_id'] as int
            : int.tryParse('${j['condition_id']}') ?? 0,
        conditionName: j['condition_name']?.toString(),
        color: j['color']?.toString(),
        note: j['note']?.toString(),
      );
}

/// One tooth's state as returned by GET /api/patients/{id}/tooth-chart.
/// `hasPlan` / `unpaidBalance` are server-computed badges (never stored).
class ToothChartEntry {
  final String toothNo;
  final List<ToothConditionTag> conditions;
  final String source; // 'chart' | 'legacy'
  final bool hasPlan;
  final double unpaidBalance;

  const ToothChartEntry({
    required this.toothNo,
    this.conditions = const [],
    this.source = 'chart',
    this.hasPlan = false,
    this.unpaidBalance = 0,
  });

  bool get hasConditions => conditions.isNotEmpty;

  factory ToothChartEntry.fromJson(String toothNo, Map<String, dynamic> j) =>
      ToothChartEntry(
        toothNo: toothNo,
        conditions: ((j['conditions'] as List?) ?? const [])
            .map((c) => ToothConditionTag.fromJson(Map<String, dynamic>.from(c as Map)))
            .toList(),
        source: (j['source'] ?? 'chart').toString(),
        hasPlan: j['has_plan'] == true || j['has_plan'] == 1,
        unpaidBalance: _num(j['unpaid_balance']),
      );

  static double _num(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd clinic_mobile_app && flutter test test/tooth_chart_service_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clinic_mobile_app/lib/models/tooth_chart_entry.dart clinic_mobile_app/test/tooth_chart_service_test.dart
git commit -m "feat(mobile/odontogram): ToothChartEntry holds a conditions list"
```

---

### Task 4.2: Service writes a `conditions[]` replace-set

**Files:**
- Modify: `clinic_mobile_app/lib/services/tooth_chart_service.dart`

- [ ] **Step 1: Replace `setTooth` with `setToothConditions`**

```dart
  /// Replace a tooth's full condition set. Empty list clears the tooth.
  Future<void> setToothConditions(
    int patientId,
    String toothNo,
    List<({int conditionId, String? note})> conditions,
  ) async {
    await _api.post('/api/patients/$patientId/tooth-chart', body: {
      'tooth_no': toothNo,
      'conditions': [
        for (final c in conditions)
          {'condition_id': c.conditionId, 'note': c.note},
      ],
    });
  }
```

Keep `clearTooth` (it can also be expressed as `setToothConditions(pid, t, [])`, but the DELETE endpoint is fine). Remove the old single-condition `setTooth`.

- [ ] **Step 2: Update the abstract `ToothChartReader` + `_RealChartReader` in `odontogram_view.dart`**

Replace the `setTooth(...)` member on both with:

```dart
  Future<void> setToothConditions(int patientId, String toothNo,
      List<({int conditionId, String? note})> conditions);
```

and the real impl delegates to `_svc.setToothConditions(...)`.

- [ ] **Step 3: Analyze**

Run: `cd clinic_mobile_app && dart analyze` — expect errors only in `odontogram_view.dart` (the sheet still calls the old API); those are fixed in 4.4. Commit after 4.4 compiles; for now:

```bash
cd clinic_mobile_app && dart format lib/services/tooth_chart_service.dart
```

(No commit yet — bundle with 4.3/4.4 so the app compiles.)

---

### Task 4.3: Banded `_ToothPainter` + redrawn shapes (mobile)

**Files:**
- Modify: `clinic_mobile_app/lib/screens/odontogram_view.dart` — `_ToothCell`, `_ToothPainter`

- [ ] **Step 1: Pass conditions to the painter and paint bands**

Update `_ToothCell.build` to compute the band colors and lock the row to LTR (in `_ArchRow`, wrap the `Row` in `Directionality(textDirection: TextDirection.ltr, child: ...)`). Replace the `CustomPaint` painter args:

```dart
            CustomPaint(
              size: const Size(18, 24),
              painter: _ToothPainter(
                toothClass: _fdiClass(fdi),
                bandColors: [
                  for (final c in (entry?.conditions ?? const []))
                    _colorFromHex(c.color),
                ],
                outlineColor: (entry?.hasConditions ?? false)
                    ? const Color(0xFF334155)
                    : scheme.outlineVariant,
              ),
            ),
```

Remove the now-unused `fillColor`/`hasFill` locals.

- [ ] **Step 2: Rewrite `_ToothPainter` to clip + band**

```dart
class _ToothPainter extends CustomPainter {
  final String toothClass;
  final List<Color> bandColors;
  final Color outlineColor;

  const _ToothPainter({
    required this.toothClass,
    required this.bandColors,
    required this.outlineColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final path = _buildPath(size);
    if (bandColors.isNotEmpty) {
      canvas.save();
      canvas.clipPath(path);
      final bandH = size.height / bandColors.length;
      for (var i = 0; i < bandColors.length; i++) {
        final r = Rect.fromLTWH(0, i * bandH, size.width, bandH);
        canvas.drawRect(r, Paint()..color = bandColors[i]);
      }
      canvas.restore();
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = outlineColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );
  }

  Path _buildPath(Size s) {
    final w = s.width;
    final h = s.height;
    final path = Path();
    switch (toothClass) {
      case 'molar':
        path.addRRect(RRect.fromRectAndRadius(
            Rect.fromLTWH(1, 2, w - 2, h - 3), const Radius.circular(4)));
      case 'premolar':
        path.addRRect(RRect.fromRectAndRadius(
            Rect.fromLTWH(2, 3, w - 4, h - 4), const Radius.circular(4)));
      case 'canine':
        path
          ..moveTo(w / 2, 1)
          ..lineTo(w - 2, 6)
          ..lineTo(w - 2.5, h - 3)
          ..arcToPoint(Offset(2.5, h - 3), radius: const Radius.circular(3))
          ..lineTo(2, 6)
          ..close();
      default: // incisor — flat blade
        path.addRRect(RRect.fromRectAndRadius(
            Rect.fromLTWH(2.5, 3, w - 5, h - 4), const Radius.circular(2)));
    }
    return path;
  }

  @override
  bool shouldRepaint(_ToothPainter old) =>
      old.toothClass != toothClass ||
      old.outlineColor != outlineColor ||
      !_sameColors(old.bandColors, bandColors);

  static bool _sameColors(List<Color> a, List<Color> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}
```

- [ ] **Step 3: Bundle compile check (with 4.4)** — proceed to 4.4 before analyzing.

---

### Task 4.4: Multi-select tooth sheet (mobile)

**Files:**
- Modify: `clinic_mobile_app/lib/screens/odontogram_view.dart` — `_ToothSheet`

- [ ] **Step 1: Rewrite `_ToothSheetState` for multi-select chips + per-condition notes**

```dart
class _ToothSheetState extends State<_ToothSheet> {
  // condition_id -> note controller
  final Map<int, TextEditingController> _notes = {};
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    for (final c in (widget.entry?.conditions ?? const [])) {
      _notes[c.conditionId] = TextEditingController(text: c.note ?? '');
    }
  }

  @override
  void dispose() {
    for (final c in _notes.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _toggle(int conditionId) {
    setState(() {
      if (_notes.containsKey(conditionId)) {
        _notes.remove(conditionId)!.dispose();
      } else {
        _notes[conditionId] = TextEditingController();
      }
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final list = <({int conditionId, String? note})>[
        for (final e in _notes.entries)
          (
            conditionId: e.key,
            note: e.value.text.trim().isEmpty ? null : e.value.text.trim(),
          ),
      ];
      await widget.reader.setToothConditions(widget.patientId, widget.fdi, list);
      if (mounted) Navigator.pop(context);
      widget.onSaved();
    } on Exception catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    final scheme = Theme.of(context).colorScheme;

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: scheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                Text('${isArabic ? 'السن' : 'Tooth'} #${widget.fdi}',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: widget.conditions
                      .where((c) => c.name != 'Healthy')
                      .map((c) {
                    final selected = _notes.containsKey(c.id);
                    return FilterChip(
                      label: Text(isArabic && c.nameAr != null ? c.nameAr! : c.name),
                      avatar: CircleAvatar(
                          backgroundColor: _colorFromHex(c.color), radius: 7),
                      selected: selected,
                      onSelected: (_) => _toggle(c.id!),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 12),
                for (final e in _notes.entries) ...[
                  TextField(
                    controller: e.value,
                    decoration: InputDecoration(
                      isDense: true,
                      labelText: _condName(e.key, isArabic),
                      border: const OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                const SizedBox(height: 4),
                FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: const Icon(Icons.save_outlined),
                  label: Text(isArabic ? 'حفظ' : 'Save'),
                ),
                const SizedBox(height: 8),
                if (widget.onLogTreatment != null)
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onLogTreatment!(widget.fdi);
                    },
                    icon: const Icon(Icons.add_circle_outline),
                    label: Text(isArabic ? '+ تسجيل علاج' : '+ Log treatment'),
                  ),
                if (widget.onAddToPlan != null) ...[
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onAddToPlan!(widget.fdi);
                    },
                    icon: const Icon(Icons.playlist_add_outlined),
                    label: Text(isArabic ? '+ إضافة للخطة' : '+ Add to plan'),
                  ),
                ],
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _condName(int id, bool isArabic) {
    final c = widget.conditions.where((x) => x.id == id);
    if (c.isEmpty) return '#$id';
    final cc = c.first;
    return isArabic && cc.nameAr != null ? cc.nameAr! : cc.name;
  }
}
```

- [ ] **Step 2: Analyze + format**

Run: `cd clinic_mobile_app && dart analyze && dart format .`
Expected: no errors. Fix any leftover references to the removed `setTooth` / `conditionId` field.

- [ ] **Step 3: Run the widget test**

Run: `cd clinic_mobile_app && flutter test test/odontogram_view_test.dart` (if it exists; otherwise the service test from 4.1 is the gate). If a widget test injects a fake `ToothChartReader`, update its `setTooth` override to `setToothConditions`. Make it PASS.

- [ ] **Step 4: Commit the mobile bundle (4.2-4.4)**

```bash
git add clinic_mobile_app/lib clinic_mobile_app/test
git commit -m "feat(mobile/odontogram): multi-condition model, banded painter, multi-select sheet"
```

---

# Phase 5 — Settings regroup + foldable Audit Log

### Task 5.1: Regroup the `#support` tab and fold the Audit Log

**Files:**
- Modify: `templates.py:2609-2690` (`#support` tab) + audit-log loader (~5607) + i18n objects

- [ ] **Step 1: Restructure the `#support` markup into four groups**

Reorder/group the existing blocks under labelled group headings (keep every existing form/card/button and its IDs and `onclick`s intact — only the wrapping/order/headings change):

```html
            <div id="support" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="settings">Settings</h2>
                </div>

                <!-- Group: Account -->
                <h3 class="settings-group" data-i18n="account">Account</h3>
                <!-- ...existing Account section-card unchanged... -->

                <!-- Group: Sync & Connectivity -->
                <h3 class="settings-group" data-en="Sync & Connectivity" data-ar="المزامنة والاتصال">Sync & Connectivity</h3>
                <!-- ...existing Cloud Sync section-card unchanged... -->
                <!-- ...existing Bluetooth sync section-card unchanged... -->

                <!-- Group: Data -->
                <h3 class="settings-group" data-en="Data" data-ar="البيانات">Data</h3>
                <!-- ...existing Data Tools section-card — plus the Clear-catalogs button from Task 5.2... -->

                <details class="form-panel" id="audit-log-panel">
                  <summary>🧾 <span data-i18n="audit_log">Audit Log</span></summary>
                  <div class="form-panel-body">
                    <div class="table-container">
                      <table>
                        <thead><tr>
                          <th>ID</th>
                          <th data-i18n="date_time">Date and Time</th>
                          <th data-i18n="action">Action</th>
                          <th data-i18n="entity">Entity</th>
                          <th data-i18n="details">Details</th>
                        </tr></thead>
                        <tbody id="audit-logs-body"><tr><td colspan="5" data-i18n="no_data">No data</td></tr></tbody>
                      </table>
                    </div>
                  </div>
                </details>

                <!-- Group: Help -->
                <h3 class="settings-group" data-en="Help" data-ar="المساعدة">Help</h3>
                <div id="support-content"></div>
                <div style="margin-top:20px;">
                    <button class="btn btn-primary" onclick="loadSupportSection()" data-i18n="refresh_help">Refresh Help</button>
                </div>
            </div>
```

Add CSS for the group heading near the other settings styles:

```css
        .settings-group { margin:26px 0 10px; padding-bottom:6px; font-size:1.05em;
            border-bottom:1px solid var(--border,#e2e8f0); color:var(--text); }
        .settings-group:first-of-type { margin-top:8px; }
```

- [ ] **Step 2: Load the audit log lazily on first expand**

Find where `audit-logs-body` is populated (~5607, the `fetch('/api/audit-logs?limit=200')` block, likely inside a `loadSupportSection` / settings-tab loader). Move that fetch into a one-shot triggered by opening the panel:

```javascript
        (function(){
          const panel = document.getElementById('audit-log-panel');
          if (!panel) return;
          let loaded = false;
          panel.addEventListener('toggle', () => {
            if (panel.open && !loaded) { loaded = true; loadAuditLogs(); }
          });
        })();
```

Wrap the existing audit-fetch code in `async function loadAuditLogs() { ... }` if it isn't already a named function, and remove its call from the eager settings loader.

- [ ] **Step 3: `node --check` render sweep (Task 6.2) + screenshot**

Confirm: four labelled groups, even spacing, Audit Log collapsed by default and loads its rows on expand, EN + AR headings, dark mode intact.

- [ ] **Step 4: Commit**

```bash
git add templates.py
git commit -m "feat(settings): regroup into Account/Sync/Data/Help; foldable lazy Audit Log"
```

---

### Task 5.2: "Clear catalogs" button in Data Tools

**Files:**
- Modify: `templates.py` — Data Tools `section-card` (~2658) + a `clearCatalogs()` JS function + i18n

- [ ] **Step 1: Add the button to the Data Tools actions row**

Inside `.data-tools-actions` (after the Replace input):

```html
                    <button class="btn btn-danger" type="button" onclick="clearCatalogs()" data-en="🧹 Clear catalogs" data-ar="🧹 إفراغ القوائم">🧹 Clear catalogs</button>
```

- [ ] **Step 2: Add the handler**

Near `exportBundle` / `startDataImport` in the inline JS:

```javascript
        async function clearCatalogs() {
          const msg = (currentLanguage === 'ar')
            ? 'سيتم إفراغ كل الإجراءات وحالات الأسنان من القوائم (تبقى بيانات المرضى كما هي). متابعة؟'
            : 'This empties every procedure and tooth condition from the catalogs (patient data is kept). Continue?';
          if (!confirm(msg)) return;
          const out = document.getElementById('data-tools-result');
          out.textContent = (currentLanguage === 'ar') ? 'جارٍ الإفراغ…' : 'Clearing…';
          try {
            const r = await fetch('/api/data/clear-catalogs', { method: 'POST' });
            const b = await r.json();
            if (!r.ok) throw new Error(b.error || 'failed');
            out.textContent = (currentLanguage === 'ar')
              ? `تم إفراغ ${b.procedures_cleared} إجراء و ${b.conditions_cleared} حالة.`
              : `Cleared ${b.procedures_cleared} procedures and ${b.conditions_cleared} conditions.`;
          } catch (e) {
            out.textContent = ((currentLanguage === 'ar') ? 'فشل الإفراغ: ' : 'Clear failed: ') + e.message;
          }
        }
```

- [ ] **Step 3: `node --check` render sweep + manual click**

With a seeded procedure/condition present, click → confirm → result line shows counts; the procedure picker + odontogram conditions go empty.

- [ ] **Step 4: Commit**

```bash
git add templates.py
git commit -m "feat(settings): Clear catalogs button wired to /api/data/clear-catalogs"
```

---

# Phase 6 — Full verification

### Task 6.1: Backend + analyzer + format sweep

- [ ] **Step 1: Python**

Run: `python -m pytest tests/ -q`; check `$LASTEXITCODE` is 0. Fix any straggler reading the old chart shape.

- [ ] **Step 2: Lint**

Run: `ruff check dental_clinic.py db_merge.py db_import.py` → clean.

- [ ] **Step 3: Flutter**

Run: `cd clinic_mobile_app && flutter test && dart analyze && dart format --set-exit-if-changed .` → all clean.

- [ ] **Step 4: Commit any formatting**

```bash
git add -A && git commit -m "chore: format + lint pass" || echo "nothing to format"
```

---

### Task 6.2: Inline-JS render sweep (`templates.py`)

- [ ] **Step 1: Render + `node --check` every portal HTML**

This catches the `'\n'`-collapses-to-newline trap and any JS syntax error across the whole inline script:

```bash
python -c "import templates, re, subprocess, tempfile, os, pathlib; \
import dental_clinic as dc; \
html = dc.app.jinja_env.from_string(templates.HTML_TEMPLATE).render(**templates.template_context()) if hasattr(templates,'template_context') else templates.HTML_TEMPLATE; \
print('rendered', len(html))"
```

If a `template_context` helper isn't available, instead start the server (`CLINIC_HEADLESS=1 python dental_clinic.py`), `curl -s localhost:5000/login` and the portal, extract each `<script>` block, and `node --check` it. The reference recipe is in memory `reference_templates_js_escaping` / `reference_web_visual_smoke`.

- [ ] **Step 2: Visual smoke**

Screenshots (light/dark, EN/AR): redesigned Settings with folded Audit Log; chart with single + multi-condition teeth; tooth popup multi-select. Confirm no console errors.

---

### Task 6.3: Update README + run the catalog clear on the live DB

**Files:**
- Modify: `README.md` (Odontogram + Data Tools + Settings bullets), test-count note if it changed

- [ ] **Step 1: Update README**

- Odontogram bullet: a tooth now carries **multiple conditions** (each with its own note); chart shows stacked color bands.
- Data Tools bullet: add **Clear catalogs** (soft-delete + tombstone, syncs, cloud-disabled).
- Note fresh installs ship with **empty catalogs** (no demo seed).
- Update the Tests-section suite/count if it shifted.

- [ ] **Step 2: Commit docs**

```bash
git add README.md
git commit -m "docs: multi-condition odontogram, Clear catalogs, empty-seed install"
```

- [ ] **Step 3: Clear the user's live catalogs (one-time, user-confirmed)**

With the desktop server running on the real `dental_clinic.db`, the user clicks **Settings → Data → Clear catalogs** (or `curl -X POST localhost:5000/api/data/clear-catalogs` with a logged-in session). The wipe tombstones and propagates to cloud + phone on the next sync. **Do not** run a raw `DELETE` against the DB outside the app — that skips tombstones and the deletion won't sync.

---

## Self-Review

**Spec coverage:**
- §1 Settings regroup + foldable Audit Log → Task 5.1 ✓
- §2 Chart numbering/shapes fix + LTR lock → Tasks 3.1, 3.2 ✓
- §3 Multi-condition model (one-table-multi-row), API GET/POST, banded display, multi-select popup, both platforms → Tasks 2.1, 2.2, 3.3, 3.4, 4.1-4.4 ✓
- §4 Empty catalogs (remove seeds + clear endpoint + button) → Tasks 1.1, 1.2, 5.2, 6.3 ✓
- Testing (py + flutter + visual) → Tasks 2.x, 4.1, 6.1, 6.2 ✓

**Type/name consistency:** `setToothConditions` used in 4.2 (service), 4.2 (reader interface), 4.4 (sheet) — consistent. `conditions[]` shape: Python GET (2.1) emits `{condition_id, condition_name, color, note}`; Dart `ToothConditionTag.fromJson` (4.1) reads the same keys; web `openToothPopup` (3.4) reads `c.condition_id` / `c.note` — consistent. `/api/data/clear-catalogs` response `{procedures_cleared, conditions_cleared}` used in test (1.2) and JS (5.2) — consistent.

**Placeholder scan:** No TBD/TODO; every code step carries full code. The two "visual nudge" steps (3.2.4, 3.3.2) are verification/tuning steps on concrete code, not missing implementation.
