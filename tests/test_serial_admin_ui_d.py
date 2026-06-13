import re
import shutil
import subprocess
import tempfile
import os
import pytest
import serial_admin


def test_index_has_key_and_mint_surfaces():
    with serial_admin.app.test_client() as c:
        html = c.get('/').get_data(as_text=True)
    # The redesigned SPA renders the signing key inside the Settings view and the
    # mint form inside the Issue view; both endpoints are wired through the api()
    # fetch helper rather than a bare fetch() call.
    assert 'id="view-settings"' in html
    assert 'id="view-issue"' in html
    assert 'id="m-name"' in html  # the mint form's clinic-name field
    assert "'/api/mint'" in html or '"/api/mint"' in html
    assert "'/api/key/status'" in html or '"/api/key/status"' in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_index_scripts_pass_node_check():
    with serial_admin.app.test_client() as c:
        html = c.get('/').get_data(as_text=True)
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    assert scripts
    blob = '\n;\n'.join(scripts)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
        fh.write(blob)
        path = fh.name
    try:
        proc = subprocess.run(
            ['node', '--check', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            text=True
        )
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)
