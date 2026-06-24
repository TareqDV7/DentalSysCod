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
    The cursor's connection must read its own uncommitted writes (true for sqlite3); the caller owns the transaction and commit.
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
