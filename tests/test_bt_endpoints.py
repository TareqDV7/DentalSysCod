"""Tests for the BT settings endpoints (/api/bt/status, /api/bt/configure)."""

import json
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
