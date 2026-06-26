# tests/test_post_studio_ui.py
"""Presence tests for the Post Studio tab (Task 10 — generator UI)."""
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
