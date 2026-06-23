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
