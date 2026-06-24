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


def test_insight_only_no_expense_or_profit_writes(tmp_path, monkeypatch):
    db = tmp_path / 'guard.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        with c.session_transaction() as sess:
            sess['uid'] = 1
        item = c.post('/api/inventory/items', json={'name': 'C'}).get_json()['id']
        c.post(f'/api/inventory/items/{item}/restock', json={'base_qty': 10, 'unit_cost': 9.0})
        patient = c.post('/api/patients', json={'first_name': 'A', 'last_name': 'B'}).get_json()['id']
        raw = sqlite3.connect(str(db))
        pid = raw.execute('INSERT INTO treatment_procedures (name) VALUES (?)', ('P',)).lastrowid
        raw.execute('INSERT INTO procedure_materials (procedure_id, item_id, default_qty) '
                    'VALUES (?,?,?)', (pid, item, 2))
        raw.commit(); raw.close()
        c.post(f'/api/patients/{patient}/followups',
               json={'followup_date': '01/01/2026', 'procedure_id': pid, 'price': 0})
        # The follow-up deducted stock (item is now 8) but no Depo path wrote money.
        raw = sqlite3.connect(str(db))
        assert raw.execute('SELECT COUNT(*) FROM expenses').fetchone()[0] == 0
        assert raw.execute('SELECT quantity FROM inventory_items WHERE id=?', (item,)).fetchone()[0] == 8
        raw.close()


def _seed_inventory_db(path):
    """Init a fresh clinic DB at `path` and give it one stocked item."""
    prev = dental_clinic.DB_NAME
    dental_clinic.DB_NAME = str(path)
    try:
        dental_clinic.init_database()
    finally:
        dental_clinic.DB_NAME = prev
    sc = sqlite3.connect(str(path))
    sc.execute("INSERT INTO treatment_procedures (id, name) VALUES (1, 'Filling')")
    sc.execute("INSERT INTO inventory_items (id, name, quantity, cost_per_unit) "
               "VALUES (1, 'Composite', 12, 3)")
    sc.execute("INSERT INTO stock_movements (item_id, change_qty, reason, unit_cost) "
               "VALUES (1, 12, 'restock', 3)")
    sc.execute("INSERT INTO procedure_materials (procedure_id, item_id, default_qty) "
               "VALUES (1, 1, 2)")
    sc.commit(); sc.close()


def test_replace_db_preserves_inventory(tmp_path, monkeypatch):
    """A whole-DB replace must land the uploaded clinic's inventory (the 3 tables
    are not in the device-local preserve list, so they swap in wholesale)."""
    import io
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
    client = dental_clinic.app.test_client()
    with client.session_transaction() as sess:
        sess['uid'] = 1

    src = tmp_path / 'replacement.db'
    _seed_inventory_db(src)
    with open(src, 'rb') as fh:
        data = {'file': (io.BytesIO(fh.read()), 'replacement.db')}
        resp = client.post('/api/data/replace', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200

    raw = sqlite3.connect(str(dental_clinic.DB_NAME))
    items = [(r[0], r[1]) for r in raw.execute('SELECT name, quantity FROM inventory_items').fetchall()]
    moves = raw.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]
    raw.close()
    assert ('Composite', 12) in items
    assert moves == 1


def test_additive_merge_carries_inventory(tmp_path, monkeypatch):
    """The additive cross-clinic merge brings the source's inventory across,
    remapping item links/movements onto fresh ids."""
    import db_merge
    dst = tmp_path / 'dst.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(dst))
    dental_clinic.init_database()

    src = tmp_path / 'src.db'
    _seed_inventory_db(src)

    dconn = sqlite3.connect(str(dst))
    db_merge.merge_database(dconn, str(src))
    dconn.commit()
    items = [(r[0], r[1]) for r in dconn.execute('SELECT name, quantity FROM inventory_items').fetchall()]
    moves = dconn.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]
    links = dconn.execute('SELECT COUNT(*) FROM procedure_materials').fetchone()[0]
    dconn.close()
    assert ('Composite', 12) in items
    assert moves == 1
    assert links == 1
