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
