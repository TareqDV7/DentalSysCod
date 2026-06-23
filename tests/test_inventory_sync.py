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
