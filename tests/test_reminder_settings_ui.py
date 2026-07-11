"""The Reminders settings panel exists in the Settings tab HTML and its
JS functions are wired up (loaded on Settings tab open, saved via button).
Mirrors tests/test_post_studio_ui.py's presence-check style — no browser,
just string checks against the served HTML/JS."""
from templates import HTML_TEMPLATE


def test_reminders_panel_markup_present():
    assert 'id="reminders-card"' in HTML_TEMPLATE
    assert 'id="reminder-lead-hours"' in HTML_TEMPLATE
    assert 'onclick="reminderSettingsSave()"' in HTML_TEMPLATE


def test_reminders_js_functions_present():
    assert 'async function loadReminderSettings()' in HTML_TEMPLATE
    assert 'async function reminderSettingsSave()' in HTML_TEMPLATE
    assert 'loadReminderSettings();' in HTML_TEMPLATE  # wired into loadSupportSection
