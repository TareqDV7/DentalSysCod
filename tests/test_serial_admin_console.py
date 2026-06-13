"""Vendor console: settings persistence, cloud ping/revoke proxies, and HTML/JS
sanity. The console is loopback-only and the signing seed never leaves the box."""
import json
import os
import re
import shutil
import subprocess
import tempfile

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


@pytest.mark.xfail(reason='views land in the frontend rewrite (Task 5)', strict=False)
def test_index_renders_with_four_views(vendor):
    html = vendor.get('/').get_data(as_text=True)
    assert vendor.get('/').status_code == 200
    for marker in ('id="view-dashboard"', 'id="view-issue"',
                   'id="view-licenses"', 'id="view-settings"'):
        assert marker in html


def test_inline_script_is_valid_js():
    """Guards the templates.py escaping trap: a stray real newline inside a JS
    string literal is a syntax error that node --check catches."""
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    m = re.search(r'<script>(.*)</script>', serial_admin_ui.INDEX_TEMPLATE, re.S)
    assert m, 'no <script> block found in INDEX_TEMPLATE'
    fd, path = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(m.group(1))
        res = subprocess.run([node, '--check', path], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
    finally:
        os.unlink(path)
