# tests/test_license_gate_ui_a3.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import templates


def test_template_has_gate_markup():
    html = templates.HTML_TEMPLATE
    assert 'id="license-gate-overlay"' in html
    assert 'id="license-renew-banner"' in html
    assert 'id="license-viewonly-banner"' in html
    assert "fetch('/api/license/gate'" in html or 'fetch("/api/license/gate"' in html


def test_template_wires_activation_post():
    html = templates.HTML_TEMPLATE
    assert '/api/license/activate' in html
    assert 'view-only' in html   # the body class hook for the lockout


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_template_scripts_pass_node_check():
    # Guards the templates.py JS-escaping trap: a literal '\n' inside HTML_TEMPLATE
    # collapses to a real newline and breaks the inline script. node --check catches it.
    html = templates.HTML_TEMPLATE
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    assert scripts, 'no inline <script> blocks found'
    blob = '\n;\n'.join(scripts)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
        fh.write(blob)
        path = fh.name
    try:
        proc = subprocess.run(
            ['node', '--check', path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)


def test_hidden_utility_is_authoritative():
    # Regression: the activation overlay is `<div class="license-overlay hidden">`
    # and the renew/view-only banners are `class="license-banner hidden"`. Both
    # `.license-overlay` and `.license-banner` set `display:flex` and are defined
    # AFTER the `.hidden` utility in the same stylesheet, so without !important they
    # win the equal-specificity source-order tie and the `hidden` class becomes
    # visually inert -- the activation card stays on screen and "re-pops" after a
    # licensed reload. Pin that `.hidden` forces display:none authoritatively.
    css = templates.HTML_TEMPLATE
    # Match the standalone `.hidden { ... }` utility, NOT a compound selector like
    # `.license-chip.hidden { ... }` (the negative lookbehind rejects a preceding
    # identifier/`-` char, so we don't grab the wrong rule and misreport).
    m = re.search(r'(?<![\w-])\.hidden\s*\{[^}]*\}', css)
    assert m, '.hidden rule not found in portal CSS'
    assert 'display:none!important' in re.sub(r'\s+', '', m.group(0)), (
        '.hidden must be `display:none !important` so the licensing overlay/banners '
        'actually hide; a later `.license-overlay{display:flex}` otherwise wins the '
        'source-order tie and the activation card re-pops after activation'
    )
