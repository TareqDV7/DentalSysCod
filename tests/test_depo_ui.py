# tests/test_depo_ui.py
import re
import templates

HTML = templates.HTML_TEMPLATE


def _lang_map(name):
    """Return the raw text of translations.<name> = { ... } block for key checks."""
    m = re.search(name + r':\s*\{', HTML)
    assert m, f'translations.{name} map not found'
    start = m.end()
    depth = 1
    i = start
    while i < len(HTML) and depth:
        if HTML[i] == '{':
            depth += 1
        elif HTML[i] == '}':
            depth -= 1
        i += 1
    return HTML[start:i]


def test_depo_nav_tab_and_panel_present():
    assert 'data-tab="depo"' in HTML
    assert "switchTab('depo'" in HTML
    assert 'id="depo"' in HTML and 'class="tab-content"' in HTML
    assert 'id="depo-items-body"' in HTML


def test_depo_list_render_wired():
    assert 'function loadDepoSection' in HTML
    assert 'function renderInventoryItems' in HTML
    assert "fetch('/api/inventory/items')" in HTML or 'fetch(`/api/inventory/items' in HTML
    # lazy-load + language-refresh hooks
    assert "tabName === 'depo'" in HTML
    assert "activeTab === 'depo'" in HTML


def test_depo_core_strings_are_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('depo_title', 'on_hand', 'packs_remaining', 'low_stock', 'stock_value'):
        assert f'{key}:' in en, f'missing EN key {key}'
        assert f'{key}:' in ar, f'missing AR key {key}'
