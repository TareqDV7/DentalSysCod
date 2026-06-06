# tests/test_cloud_toggle_ui_c.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import templates


def test_template_cloud_sync_is_always_on_no_toggle():
    """Cloud sync is automatic — the on/off toggle and QR pairing are gone; the
    card is a status line + a manual 'Sync now' button."""
    html = templates.HTML_TEMPLATE
    # Status surface + manual sync remain.
    assert 'id="cloud-status-line"' in html
    assert 'cloudSyncNow(' in html
    # The toggle is removed (always-on by default).
    assert 'id="cloud-enabled"' not in html
    assert 'cloudToggle(' not in html
    # QR phone-pairing is removed — the phone links by typing the activation key.
    assert 'cloudShowPairingQr' not in html
    assert 'id="cloud-pairing-qr"' not in html


def test_template_drops_typed_pairing():
    html = templates.HTML_TEMPLATE
    assert 'id="cloud-url-input"' not in html
    assert 'id="cloud-serial-input"' not in html
    assert 'function cloudPair(' not in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_template_scripts_pass_node_check():
    html = templates.HTML_TEMPLATE
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    blob = '\n;\n'.join(scripts)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
        fh.write(blob); path = fh.name
    try:
        proc = subprocess.run(['node', '--check', path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              stdin=subprocess.DEVNULL, text=True)
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)
