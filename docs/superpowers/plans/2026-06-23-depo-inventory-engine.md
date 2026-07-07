# Depo (Inventory) — Engine + API + Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the inventory ("Depo") engine — a stock-movement ledger with auto-deduction on procedure record, weighted-average costing, and sync durability — exposed via authed desktop API endpoints, with the full pytest suite green.

**Architecture:** A pure, Flask-free module `inventory.py` owns all stock logic (single `post_movement` write choke-point; the append-only `stock_movements` ledger is the source of truth; `inventory_items.quantity`/`cost_per_unit` are denormalized caches). Thin Flask handlers in `dental_clinic.py` call the module inside the caller's transaction, mirroring the existing follow-up → lab-expense auto-insert. The 3 new tables join `SYNC_TABLES` so they replicate desktop↔cloud↔mobile.

**Tech Stack:** Python 3.10–3.12, Flask, SQLite (`sqlite3`), pytest. No new dependencies.

**Scope of THIS plan:** data model, the `inventory.py` engine, the desktop JSON API, follow-up deduction wiring, and sync/replace-DB durability. **Out of this plan (follow-on plans, write after this lands):** desktop UI in `templates.py`/`web_assets.py`, and the Flutter read-only Depo screen. The API contract this plan produces is the input to those plans.

## Global Constraints

- **Source of truth:** `inventory_items.quantity == SUM(stock_movements.change_qty)` per item, always. `quantity`/`cost_per_unit` are caches; only `post_movement` mutates them.
- **Insight-only money:** no Depo operation may write `clinic_profit` or rows in the `expenses` table. Material cost is reporting only.
- **Never block clinical records:** low/zero/negative stock returns a warning flag; it never raises or rejects a follow-up.
- **Idempotent deduction:** consumption keyed on `(source_type='followup', source_id=followup_id)`; re-applying must not double-deduct.
- **Base units:** all `change_qty`, `default_qty`, `low_stock_threshold`, and `unit_cost` are stored in the item's `base_unit`. Packs are display-only (`quantity / pack_size`).
- **Bilingual:** items carry `name` + `name_ar` (app is EN/AR). (UI consumes this in the follow-on plan.)
- **Transactions:** every read-modify-write happens inside one connection/transaction. Never compute a new weighted-average from a value read in an earlier transaction.
- **Soft-delete:** items use `active=0`; block hard-delete when movements exist.
- **Auth:** all inventory routes are gated (logged-in staff). Tests authenticate via `sess['uid']=1`.
- **Style:** PEP 8, type annotations on signatures, `ruff`-clean. Tests first (TDD), small commits.

## File Structure

| File | Responsibility |
|---|---|
| `inventory.py` (**create**) | Pure engine: `post_movement`, `recompute_item_quantity`, `weighted_average`, `apply_followup_consumption`, `reverse_followup_consumption`, validation. No Flask. Mirrors `patient_import.py`. |
| `dental_clinic.py` (**modify**) | 3 `CREATE TABLE` blocks after `treatment_procedures` (~`:866`); add 3 names to `SYNC_TABLES` (`:527`); add `/api/inventory/` to `_AUTH_REQUIRED_PREFIXES` (`:1994`); inventory route handlers; follow-up POST/PUT/DELETE deduction calls (`:2887`, `:2935`, `:3007`). |
| `db_merge.py`, `db_import.py` (**verify/modify**) | Confirm the 3 tables are covered by the additive-merge and replace paths (driven off `SYNC_TABLES` where possible). |
| `tests/test_inventory.py` (**create**) | Unit tests for the pure engine. |
| `tests/test_inventory_api.py` (**create**) | Integration tests for the API + follow-up deduction. |
| `tests/test_inventory_sync.py` (**create**) | Sync regression: tables in `SYNC_TABLES`, replace-DB preserves inventory, insight-only guard. |

**Anchors verified against current `main` (`5899a1c`):** `SYNC_TABLES`=`:527`; `ensure_table_column`=`:560`; `treatment_procedures` CREATE=`:857-866`; `_AUTH_REQUIRED_EXACT`=`:1986`, `_AUTH_REQUIRED_PREFIXES`=`:1994`, auth gate=`:2017`; follow-up POST=`:2754`, lab-expense insert=`:2899`, `followup_id`=`:2887`; follow-up PUT/DELETE=`:2929`. Re-grep before editing in case later tasks shift line numbers.

---

### Task 1: Schema — 3 tables + sync registration

**Files:**
- Modify: `dental_clinic.py` (insert after `treatment_procedures` CREATE, ~`:866`; edit `SYNC_TABLES` ~`:527`)
- Test: `tests/test_inventory_sync.py`

**Interfaces:**
- Produces: tables `inventory_items`, `procedure_materials`, `stock_movements` (columns per spec §4); `SYNC_TABLES` now includes all three. Consumed by every later task.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory_sync.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(path))
    dental_clinic.init_database()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _columns(conn, table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def test_inventory_tables_exist_with_expected_columns(db):
    items = _columns(db, 'inventory_items')
    assert {'id', 'name', 'name_ar', 'base_unit', 'pack_size', 'quantity',
            'cost_per_unit', 'low_stock_threshold', 'track_expiry',
            'earliest_expiry', 'active'} <= items
    links = _columns(db, 'procedure_materials')
    assert {'procedure_id', 'item_id', 'default_qty', 'active'} <= links
    moves = _columns(db, 'stock_movements')
    assert {'item_id', 'change_qty', 'reason', 'unit_cost',
            'source_type', 'source_id', 'expiry_date'} <= moves


def test_three_tables_registered_for_sync():
    for t in ('inventory_items', 'procedure_materials', 'stock_movements'):
        assert t in dental_clinic.SYNC_TABLES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_inventory_sync.py -q`
Expected: FAIL — `no such table: inventory_items` (and the SYNC_TABLES assertion fails).

- [ ] **Step 3: Add the three CREATE TABLE blocks**

Insert immediately after the `treatment_procedures` CREATE block (after `:866`) in `init_database`:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_ar TEXT,
            category TEXT,
            base_unit TEXT NOT NULL DEFAULT 'piece',
            pack_unit TEXT,
            pack_size REAL NOT NULL DEFAULT 1,
            quantity REAL NOT NULL DEFAULT 0,
            cost_per_unit REAL NOT NULL DEFAULT 0,
            low_stock_threshold REAL NOT NULL DEFAULT 0,
            reorder_qty REAL,
            supplier TEXT,
            location TEXT,
            track_expiry INTEGER NOT NULL DEFAULT 0,
            earliest_expiry TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS procedure_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            procedure_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            default_qty REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(procedure_id, item_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            change_qty REAL NOT NULL,
            reason TEXT NOT NULL,
            unit_cost REAL,
            source_type TEXT,
            source_id INTEGER,
            expiry_date TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_mv_item ON stock_movements(item_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_mv_source ON stock_movements(source_type, source_id)')
    # Future column additions to these tables go through ensure_table_column(...).
```

- [ ] **Step 4: Register the tables for sync**

In `SYNC_TABLES` (`:527`), add the three names after `'treatment_procedures'`:

```python
    'treatment_procedures',
    'inventory_items',
    'procedure_materials',
    'stock_movements',
    'patient_followups',
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory_sync.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_inventory_sync.py
git commit -m "feat(depo): inventory schema (3 tables) + SYNC_TABLES registration"
```

---

### Task 2: `weighted_average` pure function

**Files:**
- Create: `inventory.py`
- Test: `tests/test_inventory.py`

**Interfaces:**
- Produces: `weighted_average(on_hand: float, current_cost: float, add_qty: float, received_unit_cost: float) -> float`. Consumed by `post_movement` (Task 3).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory.py
import inventory


def test_weighted_average_canonical_575():
    # 10 @ 5.00 then 10 @ 6.50 -> (50 + 65) / 20 = 5.75
    after_first = inventory.weighted_average(0, 0.0, 10, 5.00)
    assert after_first == 5.00
    after_second = inventory.weighted_average(10, 5.00, 10, 6.50)
    assert round(after_second, 4) == 5.75


def test_weighted_average_zero_on_hand_takes_receipt_cost():
    assert inventory.weighted_average(0, 9.99, 5, 2.00) == 2.00


def test_weighted_average_negative_on_hand_resets_to_receipt_cost():
    # Guard: never blend into a negative base.
    assert inventory.weighted_average(-3, 4.00, 5, 2.00) == 2.00


def test_weighted_average_zero_total_keeps_current_cost():
    assert inventory.weighted_average(0, 4.00, 0, 0.0) == 4.00
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_inventory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'inventory'`.

- [ ] **Step 3: Create `inventory.py` with the function**

```python
"""Pure inventory engine for the Depo feature: stock-movement ledger, weighted-
average costing, and follow-up auto-deduction. No Flask — every function takes a
sqlite3 cursor and plain values; the caller owns the transaction. Mirrors
patient_import.py / patient_dedupe.py.

Invariant: inventory_items.quantity == SUM(stock_movements.change_qty) per item.
Only post_movement mutates quantity / cost_per_unit.
"""
from __future__ import annotations

VALID_REASONS = {'restock', 'consumption', 'adjustment', 'writeoff', 'reversal'}


def weighted_average(on_hand: float, current_cost: float,
                     add_qty: float, received_unit_cost: float) -> float:
    """New average base-unit cost after a restock. Receipt cost is per base unit.

    Guards: if on-hand <= 0, the blend would corrupt against a non-positive base,
    so take the receipt's unit cost outright; if nothing is on hand and nothing is
    received, keep the last known cost.
    """
    base = on_hand if on_hand > 0 else 0.0
    denom = base + add_qty
    if denom <= 0:
        return current_cost
    if on_hand <= 0:
        return received_unit_cost
    return (base * current_cost + add_qty * received_unit_cost) / denom
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add inventory.py tests/test_inventory.py
git commit -m "feat(depo): weighted-average costing helper"
```

---

### Task 3: `post_movement` + `recompute_item_quantity`

**Files:**
- Modify: `inventory.py`
- Test: `tests/test_inventory.py`

**Interfaces:**
- Consumes: `weighted_average` (Task 2).
- Produces:
  - `post_movement(cursor, item_id, change_qty, reason, *, unit_cost=None, source_type=None, source_id=None, expiry_date=None, note=None) -> dict` returning `{'movement_id': int, 'quantity': float, 'low_stock': bool, 'negative': bool}`.
  - `recompute_item_quantity(cursor, item_id) -> float`.
  - Consumed by Tasks 4, 5, 6.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_inventory.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    path = tmp_path / 'inv.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(path))
    dental_clinic.init_database()
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _new_item(conn, **kw):
    cols = {'name': 'Composite', 'base_unit': 'compule', 'pack_size': 20,
            'low_stock_threshold': 5}
    cols.update(kw)
    keys = ','.join(cols)
    qs = ','.join('?' for _ in cols)
    cur = conn.execute(f'INSERT INTO inventory_items ({keys}) VALUES ({qs})',
                       tuple(cols.values()))
    return cur.lastrowid


def test_post_movement_updates_cache_and_ledger_match(conn):
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 30, 'restock', unit_cost=2.0)
    inventory.post_movement(conn.cursor(), item, -4, 'consumption')
    row = conn.execute('SELECT quantity FROM inventory_items WHERE id=?', (item,)).fetchone()
    assert row['quantity'] == 26
    assert inventory.recompute_item_quantity(conn.cursor(), item) == 26


def test_restock_sets_weighted_average_cost(conn):
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=5.0)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=6.5)
    row = conn.execute('SELECT cost_per_unit FROM inventory_items WHERE id=?', (item,)).fetchone()
    assert round(row['cost_per_unit'], 4) == 5.75


def test_consumption_does_not_change_average(conn):
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=5.0)
    inventory.post_movement(conn.cursor(), item, -3, 'consumption')
    row = conn.execute('SELECT cost_per_unit FROM inventory_items WHERE id=?', (item,)).fetchone()
    assert row['cost_per_unit'] == 5.0


def test_low_stock_and_negative_flags(conn):
    item = _new_item(conn, low_stock_threshold=5)
    r1 = inventory.post_movement(conn.cursor(), item, 6, 'restock', unit_cost=1.0)
    assert r1['low_stock'] is False and r1['negative'] is False
    r2 = inventory.post_movement(conn.cursor(), item, -2, 'consumption')  # -> 4 <= 5
    assert r2['low_stock'] is True and r2['negative'] is False
    r3 = inventory.post_movement(conn.cursor(), item, -10, 'consumption')  # -> -6
    assert r3['negative'] is True


def test_restock_with_expiry_sets_earliest_expiry(conn):
    item = _new_item(conn, track_expiry=1)
    inventory.post_movement(conn.cursor(), item, 5, 'restock', unit_cost=1.0, expiry_date='2027-01-01')
    inventory.post_movement(conn.cursor(), item, 5, 'restock', unit_cost=1.0, expiry_date='2026-09-01')
    row = conn.execute('SELECT earliest_expiry FROM inventory_items WHERE id=?', (item,)).fetchone()
    assert row['earliest_expiry'] == '2026-09-01'


def test_invalid_reason_raises(conn):
    item = _new_item(conn)
    with pytest.raises(ValueError):
        inventory.post_movement(conn.cursor(), item, 1, 'bogus')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inventory.py -q`
Expected: FAIL — `AttributeError: module 'inventory' has no attribute 'post_movement'`.

- [ ] **Step 3: Implement `post_movement` + `recompute_item_quantity`**

```python
# append to inventory.py

def recompute_item_quantity(cursor, item_id: int) -> float:
    row = cursor.execute(
        'SELECT COALESCE(SUM(change_qty), 0) FROM stock_movements WHERE item_id=?',
        (item_id,)).fetchone()
    return float(row[0])


def post_movement(cursor, item_id: int, change_qty: float, reason: str, *,
                  unit_cost: float | None = None, source_type: str | None = None,
                  source_id: int | None = None, expiry_date: str | None = None,
                  note: str | None = None) -> dict:
    """The ONLY writer of stock_movements / mutator of quantity & cost_per_unit.

    Atomically (within the caller's transaction): insert the ledger row, update
    the cached quantity, recompute weighted-average on restock, refresh
    earliest_expiry, and return low/negative-stock flags.
    """
    if reason not in VALID_REASONS:
        raise ValueError(f'invalid reason: {reason!r}')

    item = cursor.execute(
        'SELECT quantity, cost_per_unit, low_stock_threshold, track_expiry '
        'FROM inventory_items WHERE id=?', (item_id,)).fetchone()
    if item is None:
        raise ValueError(f'no such inventory item: {item_id}')
    on_hand, current_cost, threshold, track_expiry = (
        float(item[0]), float(item[1]), float(item[2]), int(item[3]))

    cursor.execute(
        'INSERT INTO stock_movements '
        '(item_id, change_qty, reason, unit_cost, source_type, source_id, expiry_date, note) '
        'VALUES (?,?,?,?,?,?,?,?)',
        (item_id, change_qty, reason, unit_cost, source_type, source_id, expiry_date, note))
    movement_id = cursor.lastrowid

    new_qty = on_hand + change_qty
    new_cost = current_cost
    if reason == 'restock' and unit_cost is not None:
        new_cost = weighted_average(on_hand, current_cost, change_qty, unit_cost)

    cursor.execute(
        'UPDATE inventory_items SET quantity=?, cost_per_unit=?, '
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_qty, new_cost, item_id))

    if track_expiry and reason == 'restock' and expiry_date:
        row = cursor.execute(
            'SELECT MIN(expiry_date) FROM stock_movements '
            "WHERE item_id=? AND reason='restock' AND expiry_date IS NOT NULL "
            'AND change_qty > 0', (item_id,)).fetchone()
        cursor.execute('UPDATE inventory_items SET earliest_expiry=? WHERE id=?',
                       (row[0], item_id))

    return {'movement_id': movement_id, 'quantity': new_qty,
            'low_stock': new_qty <= threshold, 'negative': new_qty < 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory.py -q`
Expected: PASS (all engine tests).

- [ ] **Step 5: Commit**

```bash
git add inventory.py tests/test_inventory.py
git commit -m "feat(depo): post_movement write choke-point + quantity reconcile"
```

---

### Task 4: Follow-up consumption — apply + reverse (idempotent)

**Files:**
- Modify: `inventory.py`
- Test: `tests/test_inventory.py`

**Interfaces:**
- Consumes: `post_movement` (Task 3).
- Produces:
  - `apply_followup_consumption(cursor, followup_id, procedure_id, overrides=None) -> list[dict]` — `overrides` is `{item_id: qty}`; returns a list of warning dicts `{'item_id', 'name', 'quantity', 'low_stock', 'negative'}` for items that crossed threshold / went negative. Idempotent on the follow-up's current net stock effect.
  - `reverse_followup_consumption(cursor, followup_id) -> None` — posts compensating `reversal` movements so the follow-up's net stock effect returns to zero.
  - Consumed by Task 6 (follow-up endpoints) and Task 7 (sync hook).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_inventory.py

def _link(conn, procedure_id, item_id, default_qty):
    conn.execute('INSERT INTO procedure_materials (procedure_id, item_id, default_qty) '
                 'VALUES (?,?,?)', (procedure_id, item_id, default_qty))


def _proc(conn, name='Filling'):
    cur = conn.execute('INSERT INTO treatment_procedures (name) VALUES (?)', (name,))
    return cur.lastrowid


def _qty(conn, item):
    return conn.execute('SELECT quantity FROM inventory_items WHERE id=?', (item,)).fetchone()[0]


def test_apply_consumption_uses_default_qty(conn):
    proc = _proc(conn)
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=1.0)
    _link(conn, proc, item, 2)
    inventory.apply_followup_consumption(conn.cursor(), followup_id=101, procedure_id=proc)
    assert _qty(conn, item) == 8


def test_apply_consumption_override_beats_default(conn):
    proc = _proc(conn)
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=1.0)
    _link(conn, proc, item, 2)
    inventory.apply_followup_consumption(conn.cursor(), 102, proc, overrides={item: 5})
    assert _qty(conn, item) == 5


def test_apply_is_idempotent(conn):
    proc = _proc(conn)
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=1.0)
    _link(conn, proc, item, 2)
    inventory.apply_followup_consumption(conn.cursor(), 103, proc)
    inventory.apply_followup_consumption(conn.cursor(), 103, proc)  # re-run
    assert _qty(conn, item) == 8  # not 6


def test_no_links_means_no_movement(conn):
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=1.0)
    warnings = inventory.apply_followup_consumption(conn.cursor(), 104, procedure_id=999)
    assert warnings == []
    assert _qty(conn, item) == 10


def test_reverse_restores_stock(conn):
    proc = _proc(conn)
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=1.0)
    _link(conn, proc, item, 3)
    inventory.apply_followup_consumption(conn.cursor(), 105, proc)
    assert _qty(conn, item) == 7
    inventory.reverse_followup_consumption(conn.cursor(), 105)
    assert _qty(conn, item) == 10
    # Net effect of this follow-up is now zero across the ledger.
    net = conn.execute("SELECT COALESCE(SUM(change_qty),0) FROM stock_movements "
                       "WHERE source_type='followup' AND source_id=105").fetchone()[0]
    assert net == 0


def test_edit_via_reverse_then_apply(conn):
    proc = _proc(conn)
    item = _new_item(conn)
    inventory.post_movement(conn.cursor(), item, 10, 'restock', unit_cost=1.0)
    _link(conn, proc, item, 3)
    inventory.apply_followup_consumption(conn.cursor(), 106, proc)        # -3 -> 7
    inventory.reverse_followup_consumption(conn.cursor(), 106)            # +3 -> 10
    inventory.apply_followup_consumption(conn.cursor(), 106, proc, overrides={item: 4})  # -4 -> 6
    assert _qty(conn, item) == 6


def test_warning_returned_on_low_stock(conn):
    proc = _proc(conn)
    item = _new_item(conn, low_stock_threshold=5)
    inventory.post_movement(conn.cursor(), item, 6, 'restock', unit_cost=1.0)
    _link(conn, proc, item, 3)  # 6 - 3 = 3 <= 5
    warnings = inventory.apply_followup_consumption(conn.cursor(), 107, proc)
    assert warnings and warnings[0]['low_stock'] is True
    assert warnings[0]['item_id'] == item
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inventory.py -q`
Expected: FAIL — `apply_followup_consumption` undefined.

- [ ] **Step 3: Implement apply + reverse**

```python
# append to inventory.py

def _followup_net(cursor, followup_id: int) -> float:
    row = cursor.execute(
        "SELECT COALESCE(SUM(change_qty), 0) FROM stock_movements "
        "WHERE source_type='followup' AND source_id=?", (followup_id,)).fetchone()
    return float(row[0])


def apply_followup_consumption(cursor, followup_id: int, procedure_id,
                               overrides: dict | None = None) -> list[dict]:
    """Deduct each linked material for procedure_id against this follow-up.

    Idempotent: if the follow-up already has a non-zero (still-applied) net stock
    effect, do nothing. Returns warnings for items that hit threshold / negative.
    """
    if procedure_id in (None, ''):
        return []
    if _followup_net(cursor, followup_id) < 0:   # already deducted, not reversed
        return []

    links = cursor.execute(
        'SELECT pm.item_id, pm.default_qty, i.name '
        'FROM procedure_materials pm JOIN inventory_items i ON i.id = pm.item_id '
        'WHERE pm.procedure_id=? AND pm.active=1 AND i.active=1',
        (procedure_id,)).fetchall()

    overrides = overrides or {}
    warnings: list[dict] = []
    for item_id, default_qty, name in links:
        qty = float(overrides.get(item_id, default_qty))
        if qty <= 0:
            continue
        res = post_movement(cursor, item_id, -qty, 'consumption',
                            source_type='followup', source_id=followup_id)
        if res['low_stock'] or res['negative']:
            warnings.append({'item_id': item_id, 'name': name,
                             'quantity': res['quantity'],
                             'low_stock': res['low_stock'], 'negative': res['negative']})
    return warnings


def reverse_followup_consumption(cursor, followup_id: int) -> None:
    """Post compensating 'reversal' movements so this follow-up's net stock
    effect becomes zero. Append-only; safe to call when already reversed (no-op)."""
    rows = cursor.execute(
        "SELECT item_id, COALESCE(SUM(change_qty), 0) FROM stock_movements "
        "WHERE source_type='followup' AND source_id=? GROUP BY item_id",
        (followup_id,)).fetchall()
    for item_id, net in rows:
        if net:
            post_movement(cursor, item_id, -float(net), 'reversal',
                          source_type='followup', source_id=followup_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory.py -q`
Expected: PASS (all engine + consumption tests).

- [ ] **Step 5: Commit**

```bash
git add inventory.py tests/test_inventory.py
git commit -m "feat(depo): idempotent follow-up consumption apply/reverse"
```

---

### Task 5: Inventory API endpoints (items / restock / adjust / writeoff / report / materials)

**Files:**
- Modify: `dental_clinic.py` (add `'/api/inventory/'` to `_AUTH_REQUIRED_PREFIXES` `:1994`; add handlers near the other API routes)
- Test: `tests/test_inventory_api.py`

**Interfaces:**
- Consumes: `inventory.post_movement` (Task 3).
- Produces (all return JSON; all require `sess['uid']`):
  - `GET  /api/inventory/items?include_inactive=` → `[ {item...} ]` (adds `packs_remaining = quantity / pack_size`)
  - `POST /api/inventory/items` → `{item...}` (create)
  - `PUT  /api/inventory/items/<id>` → `{item...}` (edit / toggle active / toggle track_expiry)
  - `POST /api/inventory/items/<id>/restock` `{base_qty|pack_qty, unit_cost|pack_cost, expiry_date?, note?}` → `{quantity, cost_per_unit, low_stock}`
  - `POST /api/inventory/items/<id>/adjust` `{counted_qty, note?}` → `{quantity}`
  - `POST /api/inventory/items/<id>/writeoff` `{qty, note?}` → `{quantity}`
  - `GET  /api/inventory/report` → `{low_stock:[...], on_hand_value: float, expiring_soon:[...]}`
  - `GET/POST/DELETE /api/inventory/procedures/<procedure_id>/materials` → manage links (`{item_id, default_qty}`)
- **Path note (deliberate deviation from spec §6):** materials live under the `/api/inventory/` prefix rather than `/api/treatment-procedures/<id>/materials`, so a single prefix gates all inventory routes without touching the auth model of existing procedure routes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_inventory_api.py
import pytest
import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def test_items_endpoint_requires_login(client):
    assert client.get('/api/inventory/items').status_code == 401


def test_create_list_and_packs_remaining(client):
    _login(client)
    r = client.post('/api/inventory/items', json={
        'name': 'Anesthetic', 'base_unit': 'carpule', 'pack_unit': 'box',
        'pack_size': 50, 'low_stock_threshold': 10})
    assert r.status_code == 200
    item_id = r.get_json()['id']
    client.post(f'/api/inventory/items/{item_id}/restock',
                json={'base_qty': 100, 'unit_cost': 0.5})
    listed = client.get('/api/inventory/items').get_json()
    row = next(x for x in listed if x['id'] == item_id)
    assert row['quantity'] == 100
    assert row['packs_remaining'] == 2  # 100 / 50


def test_restock_weighted_average_via_api(client):
    _login(client)
    item_id = client.post('/api/inventory/items',
                          json={'name': 'Composite', 'base_unit': 'compule'}).get_json()['id']
    client.post(f'/api/inventory/items/{item_id}/restock', json={'base_qty': 10, 'unit_cost': 5.0})
    client.post(f'/api/inventory/items/{item_id}/restock', json={'base_qty': 10, 'unit_cost': 6.5})
    row = next(x for x in client.get('/api/inventory/items').get_json() if x['id'] == item_id)
    assert round(row['cost_per_unit'], 4) == 5.75


def test_adjust_recount_sets_absolute_quantity(client):
    _login(client)
    item_id = client.post('/api/inventory/items', json={'name': 'Gauze'}).get_json()['id']
    client.post(f'/api/inventory/items/{item_id}/restock', json={'base_qty': 20, 'unit_cost': 0.1})
    client.post(f'/api/inventory/items/{item_id}/adjust', json={'counted_qty': 18})
    row = next(x for x in client.get('/api/inventory/items').get_json() if x['id'] == item_id)
    assert row['quantity'] == 18


def test_writeoff_decrements(client):
    _login(client)
    item_id = client.post('/api/inventory/items', json={'name': 'Needle'}).get_json()['id']
    client.post(f'/api/inventory/items/{item_id}/restock', json={'base_qty': 10, 'unit_cost': 0.2})
    client.post(f'/api/inventory/items/{item_id}/writeoff', json={'qty': 3, 'note': 'bent'})
    row = next(x for x in client.get('/api/inventory/items').get_json() if x['id'] == item_id)
    assert row['quantity'] == 7


def test_report_low_stock_and_value(client):
    _login(client)
    a = client.post('/api/inventory/items',
                    json={'name': 'Low', 'low_stock_threshold': 5}).get_json()['id']
    client.post(f'/api/inventory/items/{a}/restock', json={'base_qty': 3, 'unit_cost': 2.0})
    rep = client.get('/api/inventory/report').get_json()
    assert any(x['id'] == a for x in rep['low_stock'])
    assert rep['on_hand_value'] == pytest.approx(6.0)  # 3 * 2.0


def test_materials_crud_and_unique(client):
    _login(client)
    item_id = client.post('/api/inventory/items', json={'name': 'X'}).get_json()['id']
    proc = dental_clinic.sqlite3.connect(dental_clinic.DB_NAME)
    pid = proc.execute('INSERT INTO treatment_procedures (name) VALUES (?)', ('Crown',)).lastrowid
    proc.commit(); proc.close()
    r = client.post(f'/api/inventory/procedures/{pid}/materials',
                    json={'item_id': item_id, 'default_qty': 2})
    assert r.status_code == 200
    links = client.get(f'/api/inventory/procedures/{pid}/materials').get_json()
    assert links[0]['item_id'] == item_id and links[0]['default_qty'] == 2
    client.delete(f'/api/inventory/procedures/{pid}/materials', json={'item_id': item_id})
    assert client.get(f'/api/inventory/procedures/{pid}/materials').get_json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inventory_api.py -q`
Expected: FAIL — 404s / login assertion fails (routes not registered).

- [ ] **Step 3: Gate the prefix**

In `_AUTH_REQUIRED_PREFIXES` (`:1994`):

```python
_AUTH_REQUIRED_PREFIXES = ('/invoice/', '/api/inventory/')
```

- [ ] **Step 4: Add the route handlers**

Add near the other API routes in `dental_clinic.py` (e.g. after the follow-up handlers, before `/api/appointments` at `:3038`). Thin handlers; engine does the work.

```python
import inventory  # near the other top-level imports


def _item_dict(row):
    d = dict(row)
    pack = d.get('pack_size') or 1
    d['packs_remaining'] = (d.get('quantity') or 0) / pack if pack else None
    return d


@app.route('/api/inventory/items', methods=['GET', 'POST'])
def inventory_items():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if request.method == 'GET':
        include_inactive = request.args.get('include_inactive')
        where = '' if include_inactive else 'WHERE active = 1'
        rows = cursor.execute(f'SELECT * FROM inventory_items {where} ORDER BY name').fetchall()
        conn.close()
        return jsonify([_item_dict(r) for r in rows])

    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        conn.close()
        return jsonify({'error': 'Name is required'}), 400
    cursor.execute(
        'INSERT INTO inventory_items '
        '(name, name_ar, category, base_unit, pack_unit, pack_size, '
        ' low_stock_threshold, reorder_qty, supplier, location, track_expiry) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (name, data.get('name_ar'), data.get('category'),
         data.get('base_unit') or 'piece', data.get('pack_unit'),
         float(data.get('pack_size') or 1), float(data.get('low_stock_threshold') or 0),
         data.get('reorder_qty'), data.get('supplier'), data.get('location'),
         1 if data.get('track_expiry') else 0))
    item_id = cursor.lastrowid
    append_audit_log(cursor, 'create', 'inventory_item', item_id, {'name': name})
    row = cursor.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
    conn.commit(); conn.close()
    return jsonify(_item_dict(row))


@app.route('/api/inventory/items/<int:item_id>', methods=['PUT'])
def inventory_item_update(item_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    data = request.json or {}
    fields = ['name', 'name_ar', 'category', 'base_unit', 'pack_unit', 'pack_size',
              'low_stock_threshold', 'reorder_qty', 'supplier', 'location',
              'track_expiry', 'active']
    sets, vals = [], []
    for f in fields:
        if f in data:
            sets.append(f'{f}=?')
            v = data[f]
            if f in ('track_expiry', 'active'):
                v = 1 if v else 0
            vals.append(v)
    if not sets:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    vals.append(item_id)
    cursor.execute(f"UPDATE inventory_items SET {','.join(sets)}, "
                   f"updated_at=CURRENT_TIMESTAMP WHERE id=?", vals)
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404
    row = cursor.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
    conn.commit(); conn.close()
    return jsonify(_item_dict(row))


@app.route('/api/inventory/items/<int:item_id>/restock', methods=['POST'])
def inventory_restock(item_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    data = request.json or {}
    item = cursor.execute('SELECT pack_size FROM inventory_items WHERE id=?', (item_id,)).fetchone()
    if item is None:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404
    pack_size = float(item['pack_size'] or 1)
    if data.get('base_qty') not in (None, ''):
        base_qty = float(data['base_qty'])
    else:
        base_qty = float(data.get('pack_qty') or 0) * pack_size
    if base_qty <= 0:
        conn.close()
        return jsonify({'error': 'Quantity must be positive'}), 400
    if data.get('unit_cost') not in (None, ''):
        unit_cost = float(data['unit_cost'])
    else:
        unit_cost = (float(data.get('pack_cost') or 0) / pack_size) if pack_size else 0.0
    if unit_cost < 0:
        conn.close()
        return jsonify({'error': 'Cost cannot be negative'}), 400
    res = inventory.post_movement(cursor, item_id, base_qty, 'restock',
                                  unit_cost=unit_cost, source_type='manual',
                                  expiry_date=data.get('expiry_date') or None,
                                  note=data.get('note'))
    row = cursor.execute('SELECT quantity, cost_per_unit FROM inventory_items WHERE id=?',
                         (item_id,)).fetchone()
    conn.commit(); conn.close()
    return jsonify({'quantity': row['quantity'], 'cost_per_unit': row['cost_per_unit'],
                    'low_stock': res['low_stock']})


@app.route('/api/inventory/items/<int:item_id>/adjust', methods=['POST'])
def inventory_adjust(item_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    data = request.json or {}
    counted = float(data.get('counted_qty') or 0)
    if counted < 0:
        conn.close()
        return jsonify({'error': 'Count cannot be negative'}), 400
    item = cursor.execute('SELECT quantity FROM inventory_items WHERE id=?', (item_id,)).fetchone()
    if item is None:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404
    delta = counted - float(item['quantity'])
    if delta != 0:
        inventory.post_movement(cursor, item_id, delta, 'adjustment',
                                source_type='count', note=data.get('note'))
    row = cursor.execute('SELECT quantity FROM inventory_items WHERE id=?', (item_id,)).fetchone()
    conn.commit(); conn.close()
    return jsonify({'quantity': row['quantity']})


@app.route('/api/inventory/items/<int:item_id>/writeoff', methods=['POST'])
def inventory_writeoff(item_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    data = request.json or {}
    qty = float(data.get('qty') or 0)
    if qty <= 0:
        conn.close()
        return jsonify({'error': 'Quantity must be positive'}), 400
    if cursor.execute('SELECT 1 FROM inventory_items WHERE id=?', (item_id,)).fetchone() is None:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404
    res = inventory.post_movement(cursor, item_id, -qty, 'writeoff',
                                  source_type='manual', note=data.get('note'))
    conn.commit(); conn.close()
    return jsonify({'quantity': res['quantity']})


@app.route('/api/inventory/report', methods=['GET'])
def inventory_report():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    low = cursor.execute(
        'SELECT * FROM inventory_items WHERE active=1 AND quantity <= low_stock_threshold '
        'ORDER BY name').fetchall()
    value_row = cursor.execute(
        'SELECT COALESCE(SUM(quantity * cost_per_unit), 0) FROM inventory_items '
        'WHERE active=1').fetchone()
    expiring = cursor.execute(
        "SELECT i.id, i.name, sm.expiry_date, sm.change_qty "
        "FROM stock_movements sm JOIN inventory_items i ON i.id = sm.item_id "
        "WHERE i.active=1 AND i.track_expiry=1 AND sm.reason='restock' "
        "AND sm.expiry_date IS NOT NULL "
        "AND date(sm.expiry_date) <= date('now', '+60 day') "
        "ORDER BY sm.expiry_date").fetchall()
    conn.close()
    return jsonify({'low_stock': [_item_dict(r) for r in low],
                    'on_hand_value': float(value_row[0]),
                    'expiring_soon': [dict(r) for r in expiring]})


@app.route('/api/inventory/procedures/<int:procedure_id>/materials',
           methods=['GET', 'POST', 'DELETE'])
def inventory_procedure_materials(procedure_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if request.method == 'GET':
        rows = cursor.execute(
            'SELECT pm.item_id, pm.default_qty, i.name, i.base_unit '
            'FROM procedure_materials pm JOIN inventory_items i ON i.id = pm.item_id '
            'WHERE pm.procedure_id=? AND pm.active=1', (procedure_id,)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    data = request.json or {}
    item_id = data.get('item_id')
    if not item_id:
        conn.close()
        return jsonify({'error': 'item_id is required'}), 400

    if request.method == 'DELETE':
        cursor.execute('DELETE FROM procedure_materials WHERE procedure_id=? AND item_id=?',
                       (procedure_id, item_id))
        conn.commit(); conn.close()
        return jsonify({'success': True})

    # POST = upsert link + default_qty
    cursor.execute(
        'INSERT INTO procedure_materials (procedure_id, item_id, default_qty) VALUES (?,?,?) '
        'ON CONFLICT(procedure_id, item_id) DO UPDATE SET default_qty=excluded.default_qty, active=1',
        (procedure_id, item_id, float(data.get('default_qty') or 0)))
    conn.commit(); conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory_api.py -q`
Expected: PASS (all API tests).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_inventory_api.py
git commit -m "feat(depo): inventory REST API (items/restock/adjust/writeoff/report/materials)"
```

---

### Task 6: Follow-up deduction wiring (POST / PUT / DELETE)

**Files:**
- Modify: `dental_clinic.py` (follow-up POST `:2887`+, PUT `:2991`+, DELETE `:2935`+)
- Test: `tests/test_inventory_api.py`

**Interfaces:**
- Consumes: `inventory.apply_followup_consumption`, `inventory.reverse_followup_consumption` (Task 4).
- Produces: POST response gains a `stock_warnings` array; recording / editing / deleting a follow-up keeps stock correct. The optional request field `materials` is `[{item_id, qty}]` (desktop point-of-use overrides).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_inventory_api.py

def _make_patient(client):
    return client.post('/api/patients', json={'first_name': 'P', 'last_name': 'Q'}).get_json()['id']


def _make_linked_proc(client, item_id, default_qty=2):
    import dental_clinic as dc
    c = dc.sqlite3.connect(dc.DB_NAME)
    pid = c.execute('INSERT INTO treatment_procedures (name) VALUES (?)', ('Filling',)).lastrowid
    c.execute('INSERT INTO procedure_materials (procedure_id, item_id, default_qty) VALUES (?,?,?)',
              (pid, item_id, default_qty))
    c.commit(); c.close()
    return pid


def test_followup_record_deducts_stock(client):
    _login(client)
    pid_patient = _make_patient(client)
    item = client.post('/api/inventory/items',
                       json={'name': 'Compule', 'base_unit': 'compule'}).get_json()['id']
    client.post(f'/api/inventory/items/{item}/restock', json={'base_qty': 10, 'unit_cost': 1.0})
    proc = _make_linked_proc(client, item, default_qty=2)
    r = client.post(f'/api/patients/{pid_patient}/followups', json={
        'followup_date': '01/01/2026', 'procedure_id': proc, 'price': 100})
    assert r.status_code == 200
    row = next(x for x in client.get('/api/inventory/items').get_json() if x['id'] == item)
    assert row['quantity'] == 8


def test_followup_delete_restores_stock(client):
    _login(client)
    patient = _make_patient(client)
    item = client.post('/api/inventory/items', json={'name': 'C'}).get_json()['id']
    client.post(f'/api/inventory/items/{item}/restock', json={'base_qty': 10, 'unit_cost': 1.0})
    proc = _make_linked_proc(client, item, default_qty=3)
    client.post(f'/api/patients/{patient}/followups',
                json={'followup_date': '01/01/2026', 'procedure_id': proc, 'price': 50})
    fid = client.get(f'/api/patients/{patient}/followups').get_json()[0]['id']
    client.delete(f'/api/patients/{patient}/followups/{fid}')
    row = next(x for x in client.get('/api/inventory/items').get_json() if x['id'] == item)
    assert row['quantity'] == 10


def test_followup_with_material_override(client):
    _login(client)
    patient = _make_patient(client)
    item = client.post('/api/inventory/items', json={'name': 'C'}).get_json()['id']
    client.post(f'/api/inventory/items/{item}/restock', json={'base_qty': 10, 'unit_cost': 1.0})
    proc = _make_linked_proc(client, item, default_qty=2)
    client.post(f'/api/patients/{patient}/followups', json={
        'followup_date': '01/01/2026', 'procedure_id': proc, 'price': 50,
        'materials': [{'item_id': item, 'qty': 5}]})
    row = next(x for x in client.get('/api/inventory/items').get_json() if x['id'] == item)
    assert row['quantity'] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inventory_api.py -k followup -q`
Expected: FAIL — quantities unchanged (deduction not wired).

- [ ] **Step 3: Wire POST**

In `patient_followups` POST, after the lab-expense block and before `_recompute_followup_balances` (around `:2924`), add:

```python
    overrides = None
    raw_materials = data.get('materials')
    if isinstance(raw_materials, list):
        overrides = {}
        for m in raw_materials:
            try:
                overrides[int(m['item_id'])] = float(m['qty'])
            except (KeyError, TypeError, ValueError):
                continue
    stock_warnings = inventory.apply_followup_consumption(
        cursor, followup_id, procedure_id, overrides=overrides)
```

Change the POST return (`:2927`) to surface warnings:

```python
    return jsonify({'success': True, 'stock_warnings': stock_warnings})
```

- [ ] **Step 4: Wire PUT and DELETE**

In `followup_detail` DELETE branch, after marking `is_deleted=1` and before `_recompute_followup_balances` (around `:2951`):

```python
        inventory.reverse_followup_consumption(cursor, followup_id)
```

In the PUT branch, after the UPDATE succeeds and the lab-expense re-sync, before `_recompute_followup_balances` (around `:3033`), reverse then re-apply with the edited procedure/overrides:

```python
    cursor.execute('SELECT procedure_id FROM patient_followups WHERE id=?', (followup_id,))
    prow = cursor.fetchone()
    edited_procedure_id = prow['procedure_id'] if prow else None
    overrides = None
    raw_materials = data.get('materials')
    if isinstance(raw_materials, list):
        overrides = {}
        for m in raw_materials:
            try:
                overrides[int(m['item_id'])] = float(m['qty'])
            except (KeyError, TypeError, ValueError):
                continue
    inventory.reverse_followup_consumption(cursor, followup_id)
    inventory.apply_followup_consumption(cursor, followup_id, edited_procedure_id, overrides=overrides)
```

> Note: the PUT handler currently does not persist `procedure_id` changes. This plan keys re-apply on the stored `procedure_id`, so editing money fields re-applies the same materials correctly. If a later change lets PUT change the procedure, this code already reads the post-update value.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_inventory_api.py -q`
Expected: PASS (all API + follow-up tests).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_inventory_api.py
git commit -m "feat(depo): auto-deduct stock on follow-up record/edit/delete"
```

---

### Task 7: Sync durability — replace-DB / merge coverage, insight-only guard, mobile-deduction decision

**Files:**
- Verify/modify: `db_merge.py`, `db_import.py` (and the `/api/data/replace` path)
- Test: `tests/test_inventory_sync.py`

**Interfaces:**
- Consumes: `SYNC_TABLES` (Task 1), the API (Task 5), follow-up deduction (Task 6).
- Produces: regression coverage proving the 3 tables survive replace/merge and that no Depo op touches money tables. Documents the mobile-deduction decision.

- [ ] **Step 1: Write the failing/guard tests**

```python
# append to tests/test_inventory_sync.py
import dental_clinic


def test_insight_only_no_expense_or_profit_writes(tmp_path, monkeypatch):
    db = tmp_path / 'guard.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        with c.session_transaction() as s:
            s['uid'] = 1
        item = c.post('/api/inventory/items', json={'name': 'C'}).get_json()['id']
        c.post(f'/api/inventory/items/{item}/restock', json={'base_qty': 10, 'unit_cost': 9.0})
        patient = c.post('/api/patients', json={'first_name': 'A', 'last_name': 'B'}).get_json()['id']
        import sqlite3
        raw = sqlite3.connect(str(db))
        pid = raw.execute('INSERT INTO treatment_procedures (name) VALUES (?)', ('P',)).lastrowid
        raw.execute('INSERT INTO procedure_materials (procedure_id, item_id, default_qty) '
                    'VALUES (?,?,?)', (pid, item, 2))
        raw.commit(); raw.close()
        c.post(f'/api/patients/{patient}/followups',
               json={'followup_date': '01/01/2026', 'procedure_id': pid, 'price': 0})
        raw = sqlite3.connect(str(db))
        # No Depo activity created an expenses row.
        assert raw.execute('SELECT COUNT(*) FROM expenses').fetchone()[0] == 0
        raw.close()


def test_replace_db_preserves_inventory(tmp_path, monkeypatch):
    """Build a DB with inventory, export a bundle, replace into a fresh DB, and
    confirm the 3 tables survived. Mirrors the existing replace-DB test setup in
    tests/test_data_tools_api.py — reuse its helpers/fixture shape."""
    # See tests/test_data_tools_api.py for the export-bundle/replace harness.
    # Assert after replace: inventory_items / stock_movements rows == pre-replace counts.
    ...
```

- [ ] **Step 2: Run the guard test to verify it passes (insight-only)**

Run: `python -m pytest tests/test_inventory_sync.py::test_insight_only_no_expense_or_profit_writes -q`
Expected: PASS (confirms no regression). If it FAILS, a Depo path is wrongly writing to `expenses` — fix before continuing.

- [ ] **Step 3: Verify replace/merge cover the 3 tables**

Read `db_merge.py` and `db_import.py`. Confirm both iterate `SYNC_TABLES` (or an equivalent table list) so the 3 new tables are included automatically. If either uses a hardcoded table list, add the 3 names there. Flesh out `test_replace_db_preserves_inventory` using the harness in `tests/test_data_tools_api.py` (export-bundle → replace), asserting `inventory_items` and `stock_movements` row counts survive.

Run: `python -m pytest tests/test_inventory_sync.py -q`
Expected: PASS.

- [ ] **Step 4: Decide mobile-created-follow-up deduction (id-stability)**

Per spec §8.3, mobile follow-ups arrive via the sync-apply path, not the POST endpoint, so deduction would not fire there. Verify whether `patient_followups.id` is stable across the snapshot/merge scheme (read the merge/replace code).

- **If ids are stable:** invoke the idempotent `inventory.apply_followup_consumption(cursor, followup_id, procedure_id)` from the sync-apply path after `patient_followups` rows merge in. Add a test: a synced-in follow-up deducts once; a second sync does not double-deduct.
- **If id stability is NOT confirmable for v1 (the safe default):** do NOT auto-deduct synced-in follow-ups. Document that mobile-recorded procedures reconcile via Recount, and leave a code comment + a line in the spec's §8.3. The idempotency guard already prevents harm if the hook is added later.

Record the decision in a one-line comment at the sync-apply site and proceed.

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS — prior ~660+ tests still green plus the new inventory tests. Investigate any red before committing.

- [ ] **Step 6: Lint + commit**

```bash
ruff check inventory.py dental_clinic.py tests/test_inventory*.py
git add dental_clinic.py db_merge.py db_import.py tests/test_inventory_sync.py
git commit -m "feat(depo): sync durability (replace/merge coverage) + insight-only guard + mobile-deduction decision"
```

---

## Self-Review

**Spec coverage check (spec §→task):**
- §4 data model (3 tables) → Task 1. ✅
- §5.1 single write choke-point → Task 3 (`post_movement`). ✅
- §5.2 weighted-average (canonical $5.75, zero reset, negative guard) → Task 2. ✅
- §5.3 deduction on procedure → Task 4 (`apply_followup_consumption`) + Task 6 (POST wiring). ✅
- §5.4 edit/delete reverse+repost → Task 4 + Task 6 (PUT/DELETE). ✅
- §5.5 recount/write-off → Task 5 (`/adjust`, `/writeoff`). ✅
- §5.6 restock (base/pack, weighted-average, earliest_expiry) → Task 3 + Task 5. ✅
- §5.7 expiry (track_expiry, earliest_expiry, expiring-soon report) → Task 3 + Task 5 (`/report`). ✅
- §6 endpoints → Task 5 (note: materials path moved under `/api/inventory/` prefix — documented). ✅
- §8 sync (SYNC_TABLES, replace/merge, mobile deduction, mobile-read-only) → Task 1 + Task 7. ✅
- §9 error handling (allow+warn negatives, validation, soft-delete) → Tasks 3/5. ⚠️ **Hard-delete block when movements exist** (§9): not given its own endpoint here — items are soft-deleted via `PUT active=0` (Task 5); there is no DELETE item route, so hard-delete is structurally impossible. Acceptable; note for the UI plan.
- §10 testing matrix → Tasks 1–7 tests; **ledger invariant** is covered by `recompute_item_quantity` assertions in Task 3 and the apply/reverse tests in Task 4. ✅
- §11 out-of-scope (lot/FEFO, PO, FIFO, barcode, mobile editing) → not built. ✅

**Placeholder scan:** Task 7 Step 1's `test_replace_db_preserves_inventory` body is intentionally a `...` stub pointing at the existing `tests/test_data_tools_api.py` harness, because the replace/export helpers live there and must be reused rather than reinvented — Step 3 fills it in against that concrete harness. All other steps contain complete code.

**Type/name consistency:** `post_movement` keyword args (`unit_cost/source_type/source_id/expiry_date/note`) are identical across the module, the endpoints, and the consumption helpers. `apply_followup_consumption(cursor, followup_id, procedure_id, overrides=None)` and `reverse_followup_consumption(cursor, followup_id)` signatures match between Task 4 (definition) and Task 6 (callers). Return dict keys (`movement_id/quantity/low_stock/negative`) are consistent.

## Follow-on plans (write after this lands)

1. **Desktop UI** (`templates.py` / `web_assets.py`): Depo section (item list, on-hand, packs-remaining, low-stock highlight, expiring-soon badge, stock value; item editor with Track-expiry checkbox; Add stock / Adjust / Write-off actions), materials sub-panel on the catalog editor, follow-up "issued from stock" editable rows, basic report panel. EN/AR. Behavioral Playwright smoke.
2. **Mobile read-only** (`clinic_mobile_app/`): Flutter Depo screen consuming `GET /api/inventory/items` + `/report` (list, low-stock highlight, packs-remaining, expiring-soon badge); EN/AR via `AppStrings`; `dart analyze` clean. No create/edit.

## Execution Handoff

Plan complete. Two execution options:
1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.
