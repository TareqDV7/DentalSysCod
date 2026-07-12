"""Reports tab shows a per-dentist breakdown table below the existing
Finance stat-grid. Presence-check style, matching tests/test_reports_ui.py."""
from templates import HTML_TEMPLATE


def test_dentist_breakdown_table_present():
    assert 'id="report-dentist-breakdown-body"' in HTML_TEMPLATE


def test_render_report_stats_paints_dentist_breakdown():
    assert 'dentist_breakdown' in HTML_TEMPLATE
    assert 'function renderReportStats(data)' in HTML_TEMPLATE
