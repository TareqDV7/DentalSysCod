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
