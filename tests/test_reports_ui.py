"""The Reports tab must show only ONE profit figure -- 'Clinic Gross Profit'
-- not two redundant stat-cards (the old 'Profit' card showed a DIFFERENT,
inconsistent number before the unification in dental_clinic.py)."""
from templates import HTML_TEMPLATE


def test_only_one_profit_stat_card_present():
    assert 'id="report-clinic-gross-profit"' in HTML_TEMPLATE
    assert 'id="report-profit"' not in HTML_TEMPLATE


def test_profit_js_setText_call_removed():
    assert "setText('report-profit'" not in HTML_TEMPLATE
    assert "setText('report-clinic-gross-profit'" in HTML_TEMPLATE
