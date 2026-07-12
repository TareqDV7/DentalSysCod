"""A shared dentistsCache/loadDentists() exists and each of the three forms
has a name="dentist_id" select -- FormData auto-includes it in the POST body,
so no save-function changes are needed, only presence of the field. Mirrors
tests/test_reports_ui.py's presence-check style."""
from templates import HTML_TEMPLATE


def test_load_dentists_helper_present():
    assert 'async function loadDentists()' in HTML_TEMPLATE
    assert 'let dentistsCache' in HTML_TEMPLATE


def test_dentist_selects_present_on_all_three_forms():
    assert 'id="appointment-dentist"' in HTML_TEMPLATE
    assert 'id="followup-dentist"' in HTML_TEMPLATE
    assert 'id="billing-dentist"' in HTML_TEMPLATE
    assert 'name="dentist_id"' in HTML_TEMPLATE
