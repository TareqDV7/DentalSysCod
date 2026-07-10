import sqlite3
import pytest
import inventory
import dental_clinic


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


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    path = tmp_path / 'inv.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(path))
    dental_clinic.init_database()
    c = dental_clinic.get_db_connection(with_row_factory=True)
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
    conn.commit()
    return cur.lastrowid


def test_post_movement_updates_cache_and_ledger_match(conn):
    item = _new_item(conn)
    res = inventory.post_movement(conn.cursor(), item, 30, 'restock', unit_cost=2.0)
    assert isinstance(res['movement_id'], int) and res['movement_id'] > 0
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
