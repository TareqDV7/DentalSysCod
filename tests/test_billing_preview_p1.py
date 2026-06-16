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
