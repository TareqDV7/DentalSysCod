# tests/test_post_studio_ui.py
"""Presence tests for the Post Studio tab (Tasks 10 & 11 — generator + gallery UI)."""
import re

from templates import HTML_TEMPLATE


def test_post_studio_nav_button_present():
    assert 'data-tab="poststudio"' in HTML_TEMPLATE
    assert "onclick=\"switchTab('poststudio', this)\"" in HTML_TEMPLATE


def test_post_studio_panel_present():
    assert 'id="poststudio"' in HTML_TEMPLATE
    assert 'class="tab-content"' in HTML_TEMPLATE


def test_post_studio_key_ui_elements():
    assert 'id="ps-photo-input"' in HTML_TEMPLATE
    assert 'id="ps-doctor-name"' in HTML_TEMPLATE
    assert 'id="ps-theme"' in HTML_TEMPLATE
    assert 'id="ps-size"' in HTML_TEMPLATE
    assert 'id="psPreview"' in HTML_TEMPLATE


def test_post_studio_theme_options():
    for value in ('dark_premium', 'clean_clinical', 'soft_mint', 'bold_editorial'):
        assert f'value="{value}"' in HTML_TEMPLATE


def test_post_studio_size_options():
    for value in ('square', 'portrait', 'story'):
        assert f'value="{value}"' in HTML_TEMPLATE


def test_post_studio_js_functions_present():
    assert 'function psSave()' in HTML_TEMPLATE
    assert 'function psDownload()' in HTML_TEMPLATE
    assert 'function psOnTabOpen()' in HTML_TEMPLATE


def test_post_studio_translation_keys_in_en():
    # Locate the en: { block and verify keys are present
    en_match = re.search(r'en:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert en_match, 'Could not find en: { ... } translation block'
    en_block = en_match.group(1)
    required_keys = [
        'post_studio_title',
        'ps_photos',
        'ps_doctor_name',
        'ps_theme',
        'ps_size',
        'ps_save',
        'ps_download',
        'ps_saved',
    ]
    for key in required_keys:
        assert f'{key}:' in en_block, f'Missing EN translation key: {key}'


def test_post_studio_translation_keys_in_ar():
    # Locate the ar: { block and verify keys are present
    ar_match = re.search(r'ar:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert ar_match, 'Could not find ar: { ... } translation block'
    ar_block = ar_match.group(1)
    required_keys = [
        'post_studio_title',
        'ps_photos',
        'ps_doctor_name',
        'ps_theme',
        'ps_size',
        'ps_save',
        'ps_download',
        'ps_saved',
    ]
    for key in required_keys:
        assert f'{key}:' in ar_block, f'Missing AR translation key: {key}'


def test_post_studio_tab_switch_wired():
    assert "tabName === 'poststudio'" in HTML_TEMPLATE
    assert 'psOnTabOpen()' in HTML_TEMPLATE


def test_post_studio_bilingual_nav_label():
    assert 'data-en="Post Studio"' in HTML_TEMPLATE
    assert 'data-ar="استوديو المنشورات"' in HTML_TEMPLATE


# ── Task 11: Gallery UI ──────────────────────────────────────────────────────

def test_gallery_container_present():
    assert 'id="psGallery"' in HTML_TEMPLATE
    assert 'id="psGalleryEmpty"' in HTML_TEMPLATE


def test_gallery_js_function_present():
    assert 'function psLoadGallery()' in HTML_TEMPLATE


def test_gallery_wired_into_tab_open():
    """psOnTabOpen must call psLoadGallery so the gallery loads when the tab opens."""
    # The call must appear at least twice: once in psSave guard, once in psOnTabOpen
    assert HTML_TEMPLATE.count('psLoadGallery()') >= 2, (
        'Expected psLoadGallery() in both psSave guard and psOnTabOpen'
    )
    # psOnTabOpen definition must appear before the call site at psLoadGallery() closing area
    ps_on_idx = HTML_TEMPLATE.index('async function psOnTabOpen()')
    # psLoadGallery() must appear after psOnTabOpen starts (wired in its body)
    load_call_idx = HTML_TEMPLATE.index('psLoadGallery();', ps_on_idx)
    assert load_call_idx > ps_on_idx, 'psOnTabOpen does not call psLoadGallery()'


def test_gallery_translation_keys_in_en():
    en_match = re.search(r'en:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert en_match, 'Could not find en: { ... } translation block'
    en_block = en_match.group(1)
    for key in ('ps_gallery', 'ps_gallery_empty', 'ps_delete', 'ps_delete_confirm'):
        assert f'{key}:' in en_block, f'Missing EN translation key: {key}'


def test_gallery_translation_keys_in_ar():
    ar_match = re.search(r'ar:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert ar_match, 'Could not find ar: { ... } translation block'
    ar_block = ar_match.group(1)
    for key in ('ps_gallery', 'ps_gallery_empty', 'ps_delete', 'ps_delete_confirm'):
        assert f'{key}:' in ar_block, f'Missing AR translation key: {key}'


def test_gallery_uses_escape_html():
    """Gallery cards must use escapeHtml for user-controlled values."""
    assert 'escapeHtml' in HTML_TEMPLATE


def test_gallery_uses_show_confirm():
    """Delete must use the showConfirm modal — check it appears after psLoadGallery definition."""
    load_idx = HTML_TEMPLATE.index('async function psLoadGallery()')
    # showConfirm must appear somewhere after psLoadGallery starts
    confirm_idx = HTML_TEMPLATE.find('showConfirm(', load_idx)
    assert confirm_idx > load_idx, 'psLoadGallery does not use showConfirm for delete'


def test_gallery_delete_uses_fetch_delete():
    """Delete action must issue a fetch with method DELETE."""
    load_idx = HTML_TEMPLATE.index('async function psLoadGallery()')
    delete_idx = HTML_TEMPLATE.find("method: 'DELETE'", load_idx)
    assert delete_idx > load_idx, 'psLoadGallery delete does not use fetch method DELETE'
