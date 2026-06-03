"""Tests for the one-tap phone-pairing QR endpoint (/api/cloud/pairing-qr).

The local server renders the cloud-pairing payload {"v":1,"u":<url>,"t":<token>}
as an SVG QR so a phone can scan it and link without re-typing the URL/serial.
The route is gated behind the staff portal login (session['uid']) and is only
available on the local server (404 on the cloud node), like the other
/api/cloud/* routes.
"""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / 'pairing_qr.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    """Satisfy the portal login gate the same way the other authed-route tests
    do — a truthy session uid is all `_require_login_for_portal` checks."""
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def _pair(db_path, url='https://cloud.example', token='TOK-abc-123'):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    dental_clinic.write_app_setting(cur, 'cloud_url', url)
    dental_clinic.write_app_setting(cur, 'cloud_clinic_token', token)
    conn.commit()
    conn.close()


def test_requires_session(client):
    # No session → the portal gate rejects with 401 before the handler runs.
    r = client.get('/api/cloud/pairing-qr')
    assert r.status_code == 401


def test_400_when_unpaired(client):
    _login(client)
    r = client.get('/api/cloud/pairing-qr')
    assert r.status_code == 400
    assert 'pair' in r.get_json()['error'].lower()


def test_returns_svg_when_paired(client, tmp_path):
    _login(client)
    _pair(str(tmp_path / 'pairing_qr.db'))
    r = client.get('/api/cloud/pairing-qr')
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('image/svg+xml')
    body = r.get_data(as_text=True)
    assert '<svg' in body
    # The QR must not be cached (it carries the clinic token).
    assert 'no-store' in (r.headers.get('Cache-Control') or '')


def test_payload_encodes_url_and_token(client, tmp_path, monkeypatch):
    # The handler builds the compact v1 payload from the configured cloud_url +
    # token. Capture what it hands to the QR factory to confirm the shape.
    _login(client)
    _pair(str(tmp_path / 'pairing_qr.db'), url='https://c.example', token='SECRET-TOKEN')

    captured = {}
    import qrcode
    real_qr_make = qrcode.make

    def fake_make(data, *args, **kwargs):
        captured['data'] = data
        return real_qr_make(data, *args, **kwargs)

    monkeypatch.setattr(qrcode, 'make', fake_make)

    r = client.get('/api/cloud/pairing-qr')
    assert r.status_code == 200
    import json
    payload = json.loads(captured['data'])
    assert payload == {'v': 1, 'u': 'https://c.example', 't': 'SECRET-TOKEN'}


def test_cloud_node_does_not_expose_pairing_qr(monkeypatch, tmp_path):
    # On the cloud node the portal-less tenant gate runs before the handler, so
    # an unauthenticated portal-style GET (no clinic token) never returns a QR.
    # This guards that the token-bearing QR is a local-server-only concept.
    data_dir = tmp_path / 'clouddata'
    data_dir.mkdir()
    master = str(data_dir / 'cloud_master.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', master)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', dental_clinic._DbPathProxy(master))
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()
    try:
        with dental_clinic.app.test_client() as c:
            r = c.get('/api/cloud/pairing-qr')
            # Tenant gate (no X-Clinic-Token) rejects before any SVG is built.
            assert r.status_code in (401, 404, 501)
            assert (r.headers.get('Content-Type') or '').startswith('image/svg+xml') is False
    finally:
        dental_clinic._set_request_db_path(None)
