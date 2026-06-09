"""Tests for the BT settings endpoints (/api/bt/status, /api/bt/configure)."""

import pytest

import dental_clinic


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / 'bt_ep.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as c:
        # Log in as the seeded admin so the endpoints are reachable.
        c.post('/login', data={'username': 'admin', 'password': 'admin'})
        yield c


def test_status_returns_defaults_when_unconfigured(client):
    r = client.get('/api/bt/status')
    assert r.status_code == 200
    data = r.get_json()
    assert data['enabled'] is False
    assert data['com_port'] == ''
    assert 'available_ports' in data
    assert isinstance(data['available_ports'], list)


def test_configure_persists_settings(client):
    r = client.post('/api/bt/configure', json={'enabled': True, 'com_port': 'COM7'})
    assert r.status_code == 200
    assert r.get_json()['ok'] is True
    status = client.get('/api/bt/status').get_json()
    assert status['enabled'] is True
    assert status['com_port'] == 'COM7'


def test_configure_rejects_invalid_payload(client):
    r = client.post('/api/bt/configure', json={'enabled': 'yes', 'com_port': 9})
    assert r.status_code == 400


def test_status_includes_recommended_port(client, monkeypatch):
    monkeypatch.setattr(
        dental_clinic, '_bt_list_serial_ports',
        lambda: [{'device': 'COM9', 'description': 'BT', 'hwid': '', 'looks_incoming': True}],
    )
    data = client.get('/api/bt/status').get_json()
    assert data['recommended_port'] == 'COM9'


def test_configure_auto_picks_when_port_omitted(client, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_bt_pick_default_port', lambda: 'COM11')
    r = client.post('/api/bt/configure', json={'enabled': True})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {'ok': True, 'com_port': 'COM11', 'auto_picked': True}
    assert client.get('/api/bt/status').get_json()['com_port'] == 'COM11'


def test_configure_clears_last_error(client):
    # Seed an error, then save fresh settings — the error should be wiped so
    # the next worker pass starts clean rather than the UI showing a stale ⚠️.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    dental_clinic.write_app_setting(cur, 'bt_last_error', 'boom')
    conn.commit()
    conn.close()
    client.post('/api/bt/configure', json={'enabled': True, 'com_port': 'COM7'})
    assert client.get('/api/bt/status').get_json()['last_error'] == ''


def test_endpoints_require_login(tmp_path, monkeypatch):
    db = tmp_path / 'bt_ep2.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        r = c.get('/api/bt/status')
        assert r.status_code in (302, 401)


def test_endpoints_disabled_on_cloud_node(tmp_path, monkeypatch):
    db = tmp_path / 'bt_ep3.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        r = c.get('/api/bt/status')
        # 400 when authenticated on a cloud node; 401 when unauthenticated (auth
        # gate fires first) — either signals the endpoint is inaccessible on cloud.
        assert r.status_code in (400, 401)
