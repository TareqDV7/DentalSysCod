"""Baseline security hardening.

Covers two easy-but-real fixes:
  1. The destructive ``/api/data/clear-billing`` endpoint must require a staff
     login like its sibling data-tools routes — it was silently open, so any
     unauthenticated client on the LAN could wipe every billing row.
  2. Every response carries baseline browser-hardening headers (nosniff,
     X-Frame-Options, Referrer-Policy, Permissions-Policy), with HSTS emitted
     only over HTTPS so a cached max-age can't lock a clinic out of its own
     plain-HTTP LAN server.
"""
import pytest

import dental_clinic


@pytest.fixture()
def local_client(tmp_path, monkeypatch):
    db = tmp_path / 'sec_local.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'admin'


# ── 1. clear-billing auth gate ──────────────────────────────────────────────

def test_clear_billing_requires_login(local_client):
    # Unauthenticated POST must be rejected, never silently wipe billing.
    r = local_client.post('/api/data/clear-billing')
    assert r.status_code == 401


def test_clear_billing_allowed_when_logged_in(local_client):
    _login(local_client)
    r = local_client.post('/api/data/clear-billing')
    assert r.status_code == 200
    assert r.get_json()['success'] is True


# ── 2. baseline security headers ────────────────────────────────────────────

def test_security_headers_present(local_client):
    r = local_client.get('/healthz')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'DENY'
    assert r.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    assert 'Permissions-Policy' in r.headers


def test_hsts_only_over_https(local_client):
    # Plain HTTP: no HSTS (a cached max-age would lock the clinic out of its own
    # http:// LAN server).
    r = local_client.get('/healthz')
    assert 'Strict-Transport-Security' not in r.headers
    # HTTPS: HSTS present.
    r2 = local_client.get('/healthz', base_url='https://localhost')
    assert 'Strict-Transport-Security' in r2.headers
