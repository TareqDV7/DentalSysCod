from templates import HTML_TEMPLATE


def test_phase2_i18n_keys_present_both_langs():
    for key in ("please_confirm", "confirm", "type_to_confirm"):
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"


def test_confirm_modal_css_present():
    assert ".modal--confirm" in HTML_TEMPLATE
    assert ".confirm-modal__icon" in HTML_TEMPLATE
    assert ".confirm-modal--danger" in HTML_TEMPLATE
    assert ".confirm-modal__ok:disabled" in HTML_TEMPLATE
    # danger button uses the Phase 0 danger token, solid (never frosted)
    assert "var(--danger)" in HTML_TEMPLATE


def test_confirm_modal_markup_present():
    assert 'id="confirm-modal"' in HTML_TEMPLATE
    assert 'role="dialog"' in HTML_TEMPLATE
    assert 'aria-modal="true"' in HTML_TEMPLATE
    assert 'id="confirm-modal-title"' in HTML_TEMPLATE
    assert 'class="confirm-modal__input"' in HTML_TEMPLATE
    assert 'class="btn confirm-modal__ok"' in HTML_TEMPLATE
    # a11y: message + typed hint are programmatically associated
    assert 'aria-describedby="confirm-modal-desc"' in HTML_TEMPLATE
    assert 'id="confirm-modal-desc"' in HTML_TEMPLATE
    assert 'aria-describedby="confirm-modal-hint"' in HTML_TEMPLATE


def test_confirm_controller_present():
    for fn in ("function showConfirm", "function showTypedConfirm",
               "function _openConfirm", "function _closeConfirm"):
        assert fn in HTML_TEMPLATE, f"{fn} missing"
    # capture-phase keydown so it resolves before the global Escape handler
    assert "addEventListener('keydown', _confirmKeydownHandler, true)" in HTML_TEMPLATE
    # backdrop/Esc/cancel resolve false; only ok/Enter resolve true
    assert "_closeConfirm(false)" in HTML_TEMPLATE
    assert "_closeConfirm(true)" in HTML_TEMPLATE


def test_no_native_confirm_remains():
    # all 6 confirm() sites migrated; controller uses no native fallback
    assert HTML_TEMPLATE.count("confirm(") == 0, "a native confirm( call still remains"


def test_confirm_sites_use_showconfirm():
    assert HTML_TEMPLATE.count("await showConfirm(") >= 6
