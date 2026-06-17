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


def test_status_mapping_cancelled_is_danger_not_amber():
    # cancelled / no-show are terminal -> danger (red), no longer amber
    assert "normalized === 'cancelled' || normalized === 'no_show' || normalized === 'no-show') return 'badge-danger'" in HTML_TEMPLATE
    # the old muddled mapping is gone
    assert "normalized === 'cancelled' || normalized === 'postponed' || normalized === 'inactive') return 'badge-pending'" not in HTML_TEMPLATE


def test_status_mapping_uses_semantic_names():
    assert "normalized === 'scheduled' || normalized === 'confirmed') return 'badge-info'" in HTML_TEMPLATE
    assert "normalized === 'pending' || normalized === 'postponed') return 'badge-warning'" in HTML_TEMPLATE
    assert "normalized === 'completed' || normalized === 'paid' || normalized === 'active') return 'badge-success'" in HTML_TEMPLATE


def test_phase3_i18n_keys_present_both_langs():
    for key in ("today_schedule", "quick_actions", "new_appointment",
                "no_appointments_today", "loading_today", "schedule_load_failed"):
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"


def test_dashboard_two_column_css_present():
    assert ".dash-grid" in HTML_TEMPLATE
    assert ".dash-rail" in HTML_TEMPLATE
    assert ".dash-main" in HTML_TEMPLATE
    assert ".quick-actions" in HTML_TEMPLATE
    # responsive: stacks at the narrow breakpoint
    assert ".dash-grid" in HTML_TEMPLATE[HTML_TEMPLATE.find("@media (max-width: 720px)"):]


def test_dashboard_rail_uses_logical_props_for_rtl():
    # the grid is defined with a logical column order so RTL mirrors for free
    assert "grid-template-columns" in HTML_TEMPLATE[HTML_TEMPLATE.find(".dash-grid"):HTML_TEMPLATE.find(".dash-grid") + 400]


def test_quick_action_buttons_left_align():
    # buttons reuse .btn (inline-block) so justify-content alone is a no-op;
    # the rule must set display:flex for the left-aligned editorial rail look
    idx = HTML_TEMPLATE.find(".quick-actions__btn")
    assert idx != -1
    rule = HTML_TEMPLATE[idx:idx + 120]
    assert "display: flex" in rule
    assert "justify-content: flex-start" in rule


def test_dashboard_markup_two_column_and_schedule():
    assert 'class="dash-grid"' in HTML_TEMPLATE
    assert 'class="dash-rail"' in HTML_TEMPLATE
    assert 'id="today-schedule-body"' in HTML_TEMPLATE
    # quick actions wired to real, existing handlers
    assert 'onclick="showAddPatientModal()"' in HTML_TEMPLATE
    assert 'onclick="showAddAppointmentModal()"' in HTML_TEMPLATE
    # KPI ids preserved so loadDashboard keeps populating them
    for el_id in ('total-patients', 'today-appointments', 'total-visits', 'total-revenue', 'recent-appointments-body'):
        assert f'id="{el_id}"' in HTML_TEMPLATE
    # KPI grid keeps its id + gains the rail modifier
    assert 'class="stats-grid stats-grid--rail" id="stats-grid"' in HTML_TEMPLATE


def test_load_today_schedule_present_and_wired():
    assert "function loadTodaySchedule(" in HTML_TEMPLATE
    # reuses the P2 skeleton loader and the existing endpoint, no new API
    assert "renderSkeletonRows(4" in HTML_TEMPLATE
    assert "fetch('/api/appointments')" in HTML_TEMPLATE
    # called from loadDashboard
    idx = HTML_TEMPLATE.find("async function loadDashboard()")
    assert idx != -1
    assert "loadTodaySchedule()" in HTML_TEMPLATE[idx:idx + 900]
