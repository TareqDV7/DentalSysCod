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


# ── Task 12: Settings → Branding panel ──────────────────────────────────────

def test_branding_card_present():
    assert 'id="branding-card"' in HTML_TEMPLATE
    assert 'id="branding-doctor-name"' in HTML_TEMPLATE
    assert 'id="branding-doctor-name-ar"' in HTML_TEMPLATE
    assert 'id="branding-default-theme"' in HTML_TEMPLATE


def test_branding_theme_options():
    """Branding select must have all 4 theme options."""
    # All 4 option values exist (shared with Post Studio select)
    for value in ('dark_premium', 'clean_clinical', 'soft_mint', 'bold_editorial'):
        assert f'value="{value}"' in HTML_TEMPLATE


def test_branding_js_functions_present():
    assert 'function loadBranding()' in HTML_TEMPLATE
    assert 'function brandingSave()' in HTML_TEMPLATE


def test_branding_wired_into_load_support():
    """loadSupportSection must call loadBranding()."""
    support_idx = HTML_TEMPLATE.index('function loadSupportSection()')
    call_idx = HTML_TEMPLATE.find('loadBranding()', support_idx)
    assert call_idx > support_idx, 'loadSupportSection does not call loadBranding()'


def test_branding_api_calls_correct_endpoints():
    """brandingSave uses PUT /api/branding."""
    save_idx = HTML_TEMPLATE.index('function brandingSave()')
    branding_put = HTML_TEMPLATE.find("'/api/branding'", save_idx)
    assert branding_put > save_idx, 'brandingSave does not call /api/branding'
    put_method = HTML_TEMPLATE.find("method: 'PUT'", save_idx)
    assert put_method > save_idx, 'brandingSave does not use PUT method'


def test_branding_translation_keys_in_en():
    en_match = re.search(r'en:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert en_match, 'Could not find en: { ... } translation block'
    en_block = en_match.group(1)
    required_keys = [
        'ps_branding',
        'ps_branding_name_ar',
        'ps_branding_default_theme',
        'ps_branding_save',
        'ps_branding_saved',
        'ps_branding_save_failed',
    ]
    for key in required_keys:
        assert f'{key}:' in en_block, f'Missing EN translation key: {key}'


def test_branding_translation_keys_in_ar():
    ar_match = re.search(r'ar:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert ar_match, 'Could not find ar: { ... } translation block'
    ar_block = ar_match.group(1)
    required_keys = [
        'ps_branding',
        'ps_branding_name_ar',
        'ps_branding_default_theme',
        'ps_branding_save',
        'ps_branding_saved',
        'ps_branding_save_failed',
    ]
    for key in required_keys:
        assert f'{key}:' in ar_block, f'Missing AR translation key: {key}'


# ── Task 13: First-run branding wizard ──────────────────────────────────────

def test_wizard_modal_present():
    assert 'id="branding-wizard-modal"' in HTML_TEMPLATE
    assert 'id="bw-step-0"' in HTML_TEMPLATE
    assert 'id="bw-step-1"' in HTML_TEMPLATE
    assert 'id="bw-step-2"' in HTML_TEMPLATE


def test_wizard_nav_buttons_present():
    assert 'id="bw-btn-skip"' in HTML_TEMPLATE
    assert 'id="bw-btn-back"' in HTML_TEMPLATE
    assert 'id="bw-btn-next"' in HTML_TEMPLATE
    assert 'id="bw-btn-finish"' in HTML_TEMPLATE


def test_wizard_form_inputs_present():
    assert 'id="bw-name-en"' in HTML_TEMPLATE
    assert 'id="bw-name-ar"' in HTML_TEMPLATE
    assert 'id="bw-logo-input"' in HTML_TEMPLATE
    assert 'id="bw-theme"' in HTML_TEMPLATE


def test_wizard_calls_wizard_done_endpoint():
    assert "'/api/branding/wizard-done'" in HTML_TEMPLATE


def test_wizard_translation_keys_in_en():
    en_match = re.search(r'en:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert en_match, 'Could not find en: { ... } translation block'
    en_block = en_match.group(1)
    wizard_keys = [
        'ps_wizard_title',
        'ps_wizard_subtitle',
        'ps_wizard_step1',
        'ps_wizard_step2',
        'ps_wizard_step3',
        'ps_wizard_name_en',
        'ps_wizard_name_ar',
        'ps_wizard_logo_hint',
        'ps_wizard_theme_hint',
        'ps_wizard_skip',
        'ps_wizard_back',
        'ps_wizard_next',
        'ps_wizard_finish',
        'ps_wizard_saving',
        'ps_wizard_done_toast',
    ]
    for key in wizard_keys:
        assert f'{key}:' in en_block, f'Missing EN translation key: {key}'


def test_wizard_translation_keys_in_ar():
    ar_match = re.search(r'ar:\s*\{(.+?)^\s*\}', HTML_TEMPLATE, re.S | re.M)
    assert ar_match, 'Could not find ar: { ... } translation block'
    ar_block = ar_match.group(1)
    wizard_keys = [
        'ps_wizard_title',
        'ps_wizard_subtitle',
        'ps_wizard_step1',
        'ps_wizard_step2',
        'ps_wizard_step3',
        'ps_wizard_name_en',
        'ps_wizard_name_ar',
        'ps_wizard_logo_hint',
        'ps_wizard_theme_hint',
        'ps_wizard_skip',
        'ps_wizard_back',
        'ps_wizard_next',
        'ps_wizard_finish',
        'ps_wizard_saving',
        'ps_wizard_done_toast',
    ]
    for key in wizard_keys:
        assert f'{key}:' in ar_block, f'Missing AR translation key: {key}'


def test_wizard_domcontentloaded_gate_present():
    """DOMContentLoaded must check wizard_done and call bwShow."""
    assert 'wizard_done' in HTML_TEMPLATE
    assert 'bwShow()' in HTML_TEMPLATE


def test_wizard_js_functions_present():
    assert 'function bwShow()' in HTML_TEMPLATE
    assert 'function bwHide()' in HTML_TEMPLATE
    assert 'function bwGoStep(' in HTML_TEMPLATE
    assert 'window.bwHandleLogoInput' in HTML_TEMPLATE


# ── Task 1: Post Studio tab icon ────────────────────────────────────────────

def test_post_studio_tab_uses_image_icon():
    # The sprite must define the image glyph...
    assert '<symbol id="i-image"' in HTML_TEMPLATE
    # ...and the Post Studio nav button must use it, not the chart-bar.
    start = HTML_TEMPLATE.index('data-tab="poststudio"')
    button = HTML_TEMPLATE[start:HTML_TEMPLATE.index('</button>', start)]
    assert '#i-image' in button
    assert '#i-chart-bar' not in button
