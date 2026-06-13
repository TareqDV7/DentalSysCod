"""Vendor console: settings persistence, cloud ping/revoke proxies, and HTML/JS
sanity. The console is loopback-only and the signing seed never leaves the box."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error

import pytest

import serial_generator
import serial_admin
import serial_admin_ui


@pytest.fixture()
def vendor(tmp_path, monkeypatch):
    """serial_admin test client with an isolated temp key, ledger, and settings
    file (all derived from / overridden into tmp_path)."""
    priv, pub = serial_generator.generate_keypair()
    key_file = tmp_path / 'backend_ed25519_key.json'
    key_file.write_text(json.dumps({'alg': 'ed25519', 'private': priv}), encoding='utf-8')
    monkeypatch.setattr(serial_admin, 'KEY_FILE', str(key_file))
    monkeypatch.delenv(serial_admin.LEDGER_FILE_ENV, raising=False)
    # Literal env-var name (not serial_admin.SETTINGS_FILE_ENV) so the shared
    # fixture is stable in Task 1, before that constant exists. Task 2 adds the
    # constant equal to this same string.
    monkeypatch.setenv('CLINIC_CONSOLE_SETTINGS_FILE', str(tmp_path / 'console_settings.json'))
    with serial_admin.app.test_client() as c:
        c.pub_b64 = pub
        c.priv_b64 = priv
        c.settings_path = tmp_path / 'console_settings.json'
        yield c


def test_index_renders_with_four_views(vendor):
    resp = vendor.get('/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for marker in ('id="view-dashboard"', 'id="view-issue"',
                   'id="view-licenses"', 'id="view-settings"'):
        assert marker in html


def test_inline_script_is_valid_js():
    """Guards the templates.py escaping trap: a stray real newline inside a JS
    string literal is a syntax error that node --check catches. Skips when node
    is absent or can't be spawned in this environment."""
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    m = re.search(r'<script>(.*)</script>', serial_admin_ui.INDEX_TEMPLATE, re.S)
    assert m, 'no <script> block found in INDEX_TEMPLATE'
    fd, path = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(m.group(1))
        try:
            res = subprocess.run([node, '--check', path], capture_output=True, text=True)
        except OSError as exc:
            pytest.skip(f'node could not be spawned: {exc}')
        assert res.returncode == 0, res.stderr
    finally:
        os.unlink(path)


def test_get_settings_default_when_no_file(vendor):
    body = vendor.get('/api/settings').get_json()
    assert body['cloud_url'] == serial_admin._BAKED_CLOUD_URL
    assert body['remember'] is False
    assert 'admin_token' not in body


def test_post_settings_remember_persists_token(vendor):
    r = vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': True})
    assert r.get_json()['success'] is True
    saved = json.loads(vendor.settings_path.read_text(encoding='utf-8'))
    assert saved == {'cloud_url': 'https://cloud.test', 'remember': True, 'admin_token': 'sek'}
    got = vendor.get('/api/settings').get_json()
    assert got['admin_token'] == 'sek' and got['remember'] is True


def test_post_settings_no_remember_strips_token(vendor):
    vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': True})
    vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': False})
    saved = json.loads(vendor.settings_path.read_text(encoding='utf-8'))
    assert saved == {'cloud_url': 'https://cloud.test', 'remember': False}
    got = vendor.get('/api/settings').get_json()
    assert 'admin_token' not in got


def test_post_settings_chmod_0600(vendor, monkeypatch):
    """The settings file holds the admin token when remembered, so it must be
    written 0600. (chmod is a no-op on Windows, so assert the call, not the bits.)"""
    seen = {}
    real_chmod = os.chmod
    monkeypatch.setattr(serial_admin.os, 'chmod',
                        lambda p, m: seen.update(mode=m) or real_chmod(p, m))
    vendor.post('/api/settings', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek', 'remember': True})
    assert seen.get('mode') == 0o600


def test_get_settings_unreadable_file_returns_default(vendor):
    vendor.settings_path.write_text('not valid json {{{', encoding='utf-8')
    body = vendor.get('/api/settings').get_json()
    assert body['cloud_url'] == serial_admin._BAKED_CLOUD_URL
    assert body['remember'] is False


def test_settings_loopback_guarded(vendor):
    assert vendor.get('/api/settings',
                      environ_overrides={'REMOTE_ADDR': '203.0.113.9'}).status_code == 403
    assert vendor.post('/api/settings', json={'cloud_url': 'x', 'remember': False},
                       environ_overrides={'REMOTE_ADDR': '203.0.113.9'}).status_code == 403


def test_post_settings_write_failure_surfaces_error(vendor, monkeypatch):
    """A failed persist returns 200 + {success:false, error} (best-effort, never 500)."""
    monkeypatch.setattr(serial_admin, '_write_settings', lambda *a: (False, 'disk full'))
    r = vendor.post('/api/settings', json={'cloud_url': 'x', 'remember': False})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is False
    assert 'disk full' in body['error']


# ── /api/cloud/ping ───────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, body): self._b = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._b


def test_cloud_ping_authorized(vendor, monkeypatch):
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen',
                        lambda req, timeout=15: _Resp(b'{"serials": [], "count": 4}'))
    body = vendor.post('/api/cloud/ping',
                       json={'cloud_url': 'https://cloud.test', 'admin_token': 'sek'}).get_json()
    assert body == {'reachable': True, 'authorized': True, 'count': 4}


def test_cloud_ping_unauthorized(vendor, monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    body = vendor.post('/api/cloud/ping',
                       json={'cloud_url': 'https://cloud.test', 'admin_token': 'bad'}).get_json()
    assert body['reachable'] is True and body['authorized'] is False


def test_cloud_ping_unreachable(vendor, monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.URLError('no route to host')
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    body = vendor.post('/api/cloud/ping',
                       json={'cloud_url': 'https://cloud.test', 'admin_token': 'sek'}).get_json()
    assert body['reachable'] is False and body['authorized'] is False


def test_cloud_ping_requires_url(vendor):
    assert vendor.post('/api/cloud/ping', json={'admin_token': 'sek'}).status_code == 400


def test_cloud_ping_loopback_guarded(vendor):
    r = vendor.post('/api/cloud/ping', json={'cloud_url': 'x', 'admin_token': 't'},
                    environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403


# ── /api/cloud/revoke ─────────────────────────────────────────────────────────

def test_cloud_revoke_success(vendor, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=15):
        seen['url'] = req.full_url
        seen['admin'] = req.headers.get('X-admin-token')
        seen['body'] = json.loads(req.data.decode('utf-8'))
        return _Resp(b'{"success": true}')

    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', fake_urlopen)
    body = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'https://cloud.test/', 'admin_token': 'sek',
        'serial': 'dental-khk-clini-00001', 'status': 'revoked'}).get_json()
    assert body['success'] is True
    assert seen['url'] == 'https://cloud.test/api/license/admin/revoke'
    assert seen['admin'] == 'sek'
    assert seen['body'] == {'serial': 'DENTAL-KHK-CLINI-00001', 'status': 'revoked'}


def test_cloud_revoke_maps_401(vendor, monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    body = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'bad',
        'serial': 'DENTAL-X-0001', 'status': 'revoked'}).get_json()
    assert body['success'] is False
    assert body['error'] == 'admin token rejected'


def test_cloud_revoke_validates_fields(vendor):
    assert vendor.post('/api/cloud/revoke', json={
        'admin_token': 't', 'serial': 'DENTAL-X-0001', 'status': 'revoked'}).status_code == 400
    assert vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'serial': 'DENTAL-X-0001', 'status': 'revoked'}).status_code == 400
    assert vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'admin_token': 't', 'status': 'revoked'}).status_code == 400
    assert vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'admin_token': 't', 'serial': 'DENTAL-X-0001',
        'status': 'nonsense'}).status_code == 400


def test_cloud_revoke_loopback_guarded(vendor):
    r = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'x', 'admin_token': 't', 'serial': 'DENTAL-X-0001', 'status': 'revoked'},
        environ_overrides={'REMOTE_ADDR': '203.0.113.9'})
    assert r.status_code == 403


def test_cloud_revoke_non_401_http_error_without_body(vendor, monkeypatch):
    """A non-401 HTTPError with no response body (fp=None) must yield a clean
    verdict, never an AttributeError/500 from calling .read() on a None body."""
    def boom(req, timeout=15):
        raise urllib.error.HTTPError('u', 500, 'Server Error', {}, None)
    monkeypatch.setattr(serial_admin.urllib.request, 'urlopen', boom)
    r = vendor.post('/api/cloud/revoke', json={
        'cloud_url': 'https://cloud.test', 'admin_token': 'sek',
        'serial': 'DENTAL-X-0001', 'status': 'revoked'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is False
    assert body['error'] == 'HTTP 500'


# ── Task 6: Dashboard + Issue markup marker ───────────────────────────────────

def test_issue_and_dashboard_markup_present(vendor):
    html = vendor.get('/').get_data(as_text=True)
    # Issue form field ids the JS builds against must exist in the served template
    # OR be created by JS we can't run here — so assert the loader functions exist.
    for fn in ('function loadDashboard', 'function loadIssue', 'function mint(',
               'function publishAll(', 'function downloadCsv(', 'function validateIssue('):
        assert fn in html


def test_jsarg_html_escapes_for_attribute_context():
    """jsArg() output is spliced into double-quoted onclick="..." attributes (mint
    results + licenses Copy/Publish/Revoke buttons). Its JSON quotes must be HTML-
    escaped to &quot; or the attribute closes early and the handler loses its arg.
    Regression guard for that quoting bug."""
    m = re.search(r'function jsArg\(s\)\{(.*?)\}', serial_admin_ui.INDEX_TEMPLATE)
    assert m, 'jsArg not found in INDEX_TEMPLATE'
    assert '&quot;' in m.group(1), 'jsArg must HTML-escape its JSON output for onclick attributes'


# ── Task 7: Licenses view marker ──────────────────────────────────────────────

def test_licenses_view_functions_present(vendor):
    html = vendor.get('/').get_data(as_text=True)
    for fn in ('function loadLicenses', 'function renderLicenses(', 'function joinLicenses(',
               'function licenseRowActions(', 'function revokeRow(', 'function publishRow(',
               'function openDetails(', 'function applyLicenseFilter('):
        assert fn in html
