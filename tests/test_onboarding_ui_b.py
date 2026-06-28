# tests/test_onboarding_ui_b.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import templates


def test_template_has_cloud_link_panel():
    html = templates.HTML_TEMPLATE
    assert 'id="license-link-cloud"' in html       # the one-tap link button
    assert 'id="license-link-skip"' in html        # "Not now"
    assert "fetch('/api/cloud/pair'" in html or 'fetch("/api/cloud/pair"' in html
    assert "fetch('/api/onboarding/state'" in html or 'fetch("/api/onboarding/state"' in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_template_scripts_pass_node_check():
    html = templates.HTML_TEMPLATE
    # Exclude type="module" blocks — those use ES import syntax which node --check
    # only accepts when the file extension is .mjs; they are checked separately
    # by tests/test_post_studio_ui.py::test_template_module_scripts_pass_node_check.
    scripts = re.findall(r'<script(?![^>]*type=["\']module["\'])[^>]*>(.*?)</script>', html, re.DOTALL)
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
