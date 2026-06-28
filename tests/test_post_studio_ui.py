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


def test_post_studio_old_generator_form_removed():
    # P2a retires the Pillow generator; the old server-render form (photo picker,
    # theme/size selects, live preview) is gone. The tab shell + saved-posts
    # gallery remain; P2b rebuilds the editor body.
    for old_id in ('id="ps-photo-input"', 'id="ps-doctor-name"',
                   'id="ps-theme"', 'id="ps-size"', 'id="psPreview"'):
        assert old_id not in HTML_TEMPLATE


def test_post_studio_theme_options():
    # Theme values survive via the Settings → Branding default-theme select.
    for value in ('dark_premium', 'clean_clinical', 'soft_mint', 'bold_editorial'):
        assert f'value="{value}"' in HTML_TEMPLATE


# ── Task 6: ESM editor mount ─────────────────────────────────────────────────

def test_post_studio_editor_mount_present():
    assert 'id="ps-editor-root"' in HTML_TEMPLATE


def test_post_studio_loads_editor_module():
    assert ("from '/post_studio/editor.js'" in HTML_TEMPLATE or
            'from "/post_studio/editor.js"' in HTML_TEMPLATE)
    assert ("from '/post_studio/host.js'" in HTML_TEMPLATE or
            'from "/post_studio/host.js"' in HTML_TEMPLATE)


def test_post_studio_tab_open_mounts_editor():
    assert 'PostStudioMount' in HTML_TEMPLATE
    assert "tabName === 'poststudio'" in HTML_TEMPLATE


def test_post_studio_old_inline_generator_gone():
    # The P2a interim inline JS is fully superseded by the ESM editor.
    assert 'function psLoadGallery()' not in HTML_TEMPLATE
    assert 'function psOnTabOpen()' not in HTML_TEMPLATE
    assert 'id="psGallery"' not in HTML_TEMPLATE


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


def test_post_studio_bilingual_nav_label():
    assert 'data-en="Post Studio"' in HTML_TEMPLATE
    assert 'data-ar="استوديو المنشورات"' in HTML_TEMPLATE


# ── Task 11: Gallery — translation keys stay ─────────────────────────────────
# (The gallery HTML and JS were retired in Task 6; translation keys stay
#  in the bundle for future use and are tested here.)

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
    """escapeHtml utility must remain in the template."""
    assert 'escapeHtml' in HTML_TEMPLATE


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


def test_branding_wizard_removed():
    assert 'branding-wizard-modal' not in HTML_TEMPLATE
    assert 'wizard-done' not in HTML_TEMPLATE
    assert 'ps_wizard_title' not in HTML_TEMPLATE
    assert 'bwShow' not in HTML_TEMPLATE


def test_branding_logo_ui_removed():
    assert 'branding-logo-preview' not in HTML_TEMPLATE
    assert 'branding-logo-input' not in HTML_TEMPLATE
    assert 'brandingUploadLogo' not in HTML_TEMPLATE
    assert 'ps_branding_logo' not in HTML_TEMPLATE


# ── Task 1: Post Studio tab icon ────────────────────────────────────────────

def test_post_studio_tab_uses_image_icon():
    # The sprite must define the image glyph...
    assert '<symbol id="i-image"' in HTML_TEMPLATE
    # ...and the Post Studio nav button must use it, not the chart-bar.
    start = HTML_TEMPLATE.index('data-tab="poststudio"')
    button = HTML_TEMPLATE[start:HTML_TEMPLATE.index('</button>', start)]
    assert '#i-image' in button
    assert '#i-chart-bar' not in button
