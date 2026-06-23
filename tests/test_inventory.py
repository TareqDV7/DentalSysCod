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
