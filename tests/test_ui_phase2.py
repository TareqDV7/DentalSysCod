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
