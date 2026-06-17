from templates import HTML_TEMPLATE


def test_badges_consolidated_semantic_and_aliases():
    # semantic name + legacy alias share one rule (grouped selector)
    assert ".badge-success, .badge-active" in HTML_TEMPLATE
    assert ".badge-warning, .badge-pending" in HTML_TEMPLATE
    assert ".badge-danger, .badge-blocked" in HTML_TEMPLATE
    assert ".badge-info, .badge-secondary" in HTML_TEMPLATE
    assert ".badge-neutral, .badge-muted" in HTML_TEMPLATE


def test_badges_have_dark_variants():
    for cls in ("badge-success", "badge-warning", "badge-danger", "badge-info", "badge-neutral"):
        assert f'body[data-theme="dark"] .{cls}' in HTML_TEMPLATE


def test_old_duplicate_badge_block_removed():
    # the redundant hardcoded status-set definitions are gone
    assert ".badge-neutral { background: #eef4fb; color: #33536d; }" not in HTML_TEMPLATE
    assert ".badge-secondary { background: #e3f1ff; color: #1f5d9e; }" not in HTML_TEMPLATE
