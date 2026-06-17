"""Phase 2 — skeleton loading screens.

The three data tables (dashboard recent-appointments, patients, appointments)
and the dashboard stat tiles used to flash a centered "Loading..." text box.
Phase 2 replaces those with shape-mimicking shimmer skeletons that respect the
P0 token spine and "solid for data" rule (opaque bars, never frosted glass).
"""

from templates import HTML_TEMPLATE


def test_skeleton_css_primitive_present():
    # the reusable shimmer primitive + its keyframe
    assert ".skeleton" in HTML_TEMPLATE
    assert "@keyframes skeletonShimmer" in HTML_TEMPLATE
    # bars sit on a solid (opaque) data surface, not frosted chrome
    assert ".skeleton-bar" in HTML_TEMPLATE


def test_skeleton_uses_p0_motion_token():
    # shimmer easing rides the Phase 0 motion token, not a hardcoded curve
    assert "skeletonShimmer 1.25s var(--ease)" in HTML_TEMPLATE


def test_skeleton_respects_reduced_motion():
    # the prefers-reduced-motion block must silence the shimmer animation
    idx = HTML_TEMPLATE.find("@media (prefers-reduced-motion: reduce)")
    assert idx != -1
    block = HTML_TEMPLATE[idx:idx + 600]
    assert ".skeleton::after" in block
    assert "animation: none" in block


def test_skeleton_dark_theme_override_present():
    assert 'body[data-theme="dark"] .skeleton' in HTML_TEMPLATE


def test_sr_only_utility_present():
    # skeleton rows are aria-hidden; an sr-only status preserves the announcement
    assert ".sr-only" in HTML_TEMPLATE


def test_render_skeleton_rows_helper_present():
    assert "function renderSkeletonRows(" in HTML_TEMPLATE
    # decorative rows are hidden from assistive tech; a status row announces load
    assert 'aria-hidden="true"' in HTML_TEMPLATE
    assert 'role="status"' in HTML_TEMPLATE


def test_three_tables_use_skeleton_not_text_loading():
    # all three table loaders moved off the renderStateRow text spinner
    assert HTML_TEMPLATE.count("kind: 'loading'") == 0
    # dashboard(4) + patients(9) + appointments(6) call sites + the definition
    assert HTML_TEMPLATE.count("renderSkeletonRows(") >= 4


def test_skeleton_announcements_reuse_loading_i18n():
    # the loading_* i18n keys stay live as the sr-only announcement text
    assert "announce: t('loading_patients'" in HTML_TEMPLATE
    assert "announce: t('loading_appointments'" in HTML_TEMPLATE
    assert "announce: t('loading_dashboard'" in HTML_TEMPLATE


def test_dashboard_stat_tiles_skeleton_toggle():
    # the stat tiles shimmer via a reversible class toggle (non-destructive)
    assert ".stats-grid.is-loading" in HTML_TEMPLATE
    assert "stats-grid" in HTML_TEMPLATE
    assert "classList.add('is-loading')" in HTML_TEMPLATE
    assert "classList.remove('is-loading')" in HTML_TEMPLATE


def test_skeleton_does_not_reintroduce_native_dialogs():
    # guard the Phase 2 invariants the prior commits established
    assert HTML_TEMPLATE.count("alert(") == 0
    assert HTML_TEMPLATE.count("confirm(") == 0
    assert HTML_TEMPLATE.count("prompt(") == 2


def test_billing_history_loader_uses_skeleton():
    # the billing payment-history loader moved off its inline text spinner
    assert "${t('loading', 'Loading…')}" not in HTML_TEMPLATE
    # the billing table has 5 columns -> its skeleton call is the only colSpan-5 one
    assert "renderSkeletonRows(5" in HTML_TEMPLATE


def test_profile_skeleton_present_and_wired():
    # patient profile shows a shape-mimicking skeleton during its fetch
    assert "function renderProfileSkeleton(" in HTML_TEMPLATE
    assert "renderProfileSkeleton()" in HTML_TEMPLATE  # called inside viewPatientProfile
    assert 'class="profile-skeleton"' in HTML_TEMPLATE
    # the avatar + tile placeholders that distinguish a profile from a table
    assert ".skeleton-avatar" in HTML_TEMPLATE
    assert ".skeleton-tile" in HTML_TEMPLATE


def test_profile_skeleton_is_decorative_for_a11y():
    # the profile skeleton block is hidden from assistive tech (decorative only)
    idx = HTML_TEMPLATE.find('class="profile-skeleton"')
    assert idx != -1
    assert 'aria-hidden="true"' in HTML_TEMPLATE[idx:idx + 120]
