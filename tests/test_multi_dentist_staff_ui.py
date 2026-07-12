"""Manage Staff: is_dentist is settable at account creation and via update,
and shows up in the account list. Mirrors the existing is_active handling in
staff_account_update()'s sets/vals pattern."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_staffui_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _login_as_admin(client):
    conn = dental_clinic.get_db_connection()
    uid = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    conn.close()
    with client.session_transaction() as sess:
        sess['uid'] = uid


def test_create_staff_with_is_dentist_true(client):
    r = client.post('/api/staff', json={
        'username': 'dr2', 'password': 'pw123456', 'display_name': 'Dr. Two', 'is_dentist': True,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get('/api/staff').get_json()
    dr2 = next(u for u in rows if u['username'] == 'dr2')
    assert dr2['is_dentist'] == 1


def test_create_staff_defaults_is_dentist_false(client):
    client.post('/api/staff', json={'username': 'fd2', 'password': 'pw123456'})
    rows = client.get('/api/staff').get_json()
    fd2 = next(u for u in rows if u['username'] == 'fd2')
    assert fd2['is_dentist'] == 0


def test_update_staff_toggles_is_dentist(client):
    client.post('/api/staff', json={'username': 'dr3', 'password': 'pw123456'})
    rows = client.get('/api/staff').get_json()
    dr3_id = next(u for u in rows if u['username'] == 'dr3')['id']

    r = client.put(f'/api/staff/{dr3_id}', json={'is_dentist': True})
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = client.get('/api/staff').get_json()
    assert next(u for u in rows if u['id'] == dr3_id)['is_dentist'] == 1


def test_reminders_panel_markup_unaffected():
    # Regression guard: templates.py must still parse/import cleanly.
    from templates import HTML_TEMPLATE
    assert 'id="staff-accounts-body"' in HTML_TEMPLATE
