"""Baseline security hardening.

Every response carries baseline browser-hardening headers (nosniff,
X-Frame-Options, Referrer-Policy, Permissions-Policy), with HSTS emitted only
over HTTPS so a cached max-age can't lock a clinic out of its own plain-HTTP
LAN server.
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


# ── baseline security headers ───────────────────────────────────────────────

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


def test_csp_header_present_and_locked_down(local_client):
    r = local_client.get('/healthz')
    csp = r.headers.get('Content-Security-Policy')
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data:" in csp
    assert "font-src 'self' data:" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
