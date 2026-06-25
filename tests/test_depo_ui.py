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


def test_item_editor_modal_and_handlers():
    assert 'id="depo-item-modal"' in HTML
    assert 'function openInventoryItemEditor' in HTML
    assert 'function saveInventoryItem' in HTML
    assert 'function deactivateInventoryItem' in HTML
    # all spec'd item fields have inputs
    for fid in ('depo-item-name', 'depo-item-name-ar', 'depo-item-category',
                'depo-item-base-unit', 'depo-item-pack-unit', 'depo-item-pack-size',
                'depo-item-threshold', 'depo-item-reorder', 'depo-item-supplier',
                'depo-item-location', 'depo-item-track-expiry'):
        assert f'id="{fid}"' in HTML, f'missing field {fid}'
    # POST create / PUT edit
    assert "method: 'POST'" in HTML and "method: 'PUT'" in HTML


def test_item_editor_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('edit_item', 'track_expiry', 'reorder_qty', 'supplier', 'location', 'deactivate'):
        assert f'{key}:' in en and f'{key}:' in ar, f'missing bilingual key {key}'


def test_stock_action_modals_and_handlers():
    for mid in ('depo-restock-modal', 'depo-adjust-modal', 'depo-writeoff-modal'):
        assert f'id="{mid}"' in HTML, f'missing {mid}'
    for fn in ('openRestockModal', 'submitRestock', 'openAdjustModal',
               'submitAdjust', 'openWriteoffModal', 'submitWriteoff'):
        assert f'function {fn}' in HTML, f'missing {fn}'
    assert '/restock' in HTML and '/adjust' in HTML and '/writeoff' in HTML
    # restock toggles expiry input only when the item tracks expiry
    assert 'depo-restock-expiry' in HTML


def test_stock_action_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('adjust_count', 'write_off', 'quantity', 'unit_cost', 'counted_qty', 'expiry_date'):
        assert f'{key}:' in en and f'{key}:' in ar, f'missing bilingual key {key}'


def test_materials_subpanel_present():
    assert 'id="materials-procedure-select"' in HTML
    assert 'id="materials-item-select"' in HTML
    assert 'id="materials-body"' in HTML
    for fn in ('loadProcedureMaterials', 'renderProcedureMaterials',
               'addProcedureMaterial', 'removeProcedureMaterial'):
        assert f'function {fn}' in HTML, f'missing {fn}'
    assert '/materials' in HTML


def test_materials_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('procedure_materials', 'default_qty', 'link_material'):
        assert f'{key}:' in en and f'{key}:' in ar, f'missing {key}'


def test_followup_override_rows_present():
    assert 'id="followup-materials-wrap"' in HTML
    assert 'id="followup-materials-body"' in HTML
    assert 'function loadFollowupMaterials' in HTML
    assert 'function collectFollowupMaterials' in HTML
    assert 'stock_warnings' in HTML
    assert 'data.materials' in HTML  # overrides injected into POST body


def test_followup_override_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('issued_from_stock', 'stock_low_after'):
        assert f'{key}:' in en and f'{key}:' in ar


def test_report_panel_present():
    for did in ('depo-report-low', 'depo-report-expiring', 'depo-report-value'):
        assert f'id="{did}"' in HTML, f'missing {did}'
    assert 'function loadDepoReport' in HTML
    assert 'function renderDepoReport' in HTML
    assert "/api/inventory/report" in HTML


def test_report_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('low_stock_items', 'expiring_soon', 'on_hand_value'):
        assert f'{key}:' in en and f'{key}:' in ar


DEPO_KEYS = [
    'depo_title', 'depo_summary', 'add_item', 'items_in_stock', 'stock_value', 'item', 'on_hand',
    'packs_remaining', 'in_stock', 'low_stock', 'negative', 'add_stock', 'edit_item', 'item_name_required',
    'item_name_ar', 'base_unit', 'pack_unit', 'pack_size', 'low_stock_threshold', 'reorder_qty', 'supplier',
    'location', 'track_expiry', 'deactivate', 'unable_save_item', 'item_saved', 'item_deactivated',
    'adjust_count', 'write_off', 'quantity', 'unit_cost', 'counted_qty', 'expiry_date', 'note', 'stock_added',
    'count_adjusted', 'written_off', 'now_low_stock', 'unable_restock', 'unable_adjust', 'unable_writeoff',
    'procedure_materials', 'procedure_materials_summary', 'default_qty', 'link_material', 'procedure', 'remove',
    'pick_procedure_item', 'unable_link', 'unable_unlink', 'issued_from_stock', 'stock_low_after',
    'depo_report', 'low_stock_items', 'expiring_soon', 'on_hand_value', 'none',
]


def test_every_depo_key_in_both_languages():
    en, ar = _lang_map('en'), _lang_map('ar')
    missing_en = [k for k in DEPO_KEYS if f'{k}:' not in en]
    missing_ar = [k for k in DEPO_KEYS if f'{k}:' not in ar]
    assert not missing_en, f'EN missing: {missing_en}'
    assert not missing_ar, f'AR missing: {missing_ar}'
