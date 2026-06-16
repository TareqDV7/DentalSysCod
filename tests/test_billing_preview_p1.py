from templates import HTML_TEMPLATE


def test_preview_css_present():
    assert ".billing-preview" in HTML_TEMPLATE
    assert ".form-with-preview" in HTML_TEMPLATE
    # solid surface using the Phase 0 token, never frosted
    assert "var(--surface)" in HTML_TEMPLATE


def test_billing_form_has_preview_panel_and_field_ids():
    assert 'id="billing-preview"' in HTML_TEMPLATE
    assert 'id="billing-discount"' in HTML_TEMPLATE
    assert 'id="billing-paid"' in HTML_TEMPLATE
    assert 'class="form-with-preview"' in HTML_TEMPLATE


def test_followup_form_has_preview_panel():
    assert 'id="followup-preview"' in HTML_TEMPLATE


def test_preview_i18n_keys_present_both_langs():
    for key in ("preview_title", "preview_net", "preview_new_balance",
                "preview_owes", "preview_credit", "preview_settled",
                "preview_change", "preview_select_patient", "preview_discount_exceeds"):
        # one definition in the EN dict + one in the AR dict
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"


def test_preview_core_functions_present():
    for fn in ("function computeBillingPreview",
               "function renderBillingPreview",
               "function resolveCalcValue",
               "function previewDebounce"):
        assert fn in HTML_TEMPLATE, f"{fn} missing"


def test_wiring_present():
    assert "function wireBillingPreview" in HTML_TEMPLATE
    assert "wireBillingPreview(" in HTML_TEMPLATE          # at least one call site
    assert "/full-profile" in HTML_TEMPLATE                # billing balance fetch
    assert "currentFollowupBalanceSigned" in HTML_TEMPLATE  # signed balance for follow-up
