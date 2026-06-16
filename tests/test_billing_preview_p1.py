from templates import HTML_TEMPLATE


def test_preview_css_present():
    assert ".billing-preview" in HTML_TEMPLATE
    assert ".form-with-preview" in HTML_TEMPLATE
    # solid surface using the Phase 0 token, never frosted
    assert "var(--surface)" in HTML_TEMPLATE
