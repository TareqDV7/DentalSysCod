"""Calendar dentist filter: presence-check style, matching
tests/test_per_dentist_reporting_ui.py. No Playwright, no mobile UI --
mobile has no calendar view to extend (see the design spec's non-goals)."""
from templates import HTML_TEMPLATE


def test_calendar_dentist_filter_select_present():
    assert 'id="calendar-dentist-filter"' in HTML_TEMPLATE


def test_populate_calendar_dentist_filter_function_present():
    assert 'function populateCalendarDentistFilter(' in HTML_TEMPLATE


def test_render_appointments_calendar_reads_filter_value():
    assert "getElementById('calendar-dentist-filter')" in HTML_TEMPLATE
