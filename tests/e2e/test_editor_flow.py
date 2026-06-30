from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "editor_harness.html")

# Chromium blocks file:// cross-origin ES module imports by default.
# --allow-file-access-from-files lifts the restriction so the harness can
# import ../editor.js and its transitive deps via <script type="module">.
_LAUNCH_ARGS = ['--allow-file-access-from-files']


def test_editor_template_addphotos_save_reopen():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        # mounts with a default template -> a preview stage exists
        page.wait_for_selector("[data-ps-stage]")
        # add photos via the (fake) host -> two <img> appear in the preview
        page.click("[data-ps-action='add-photos']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length === 2")
        # save -> fake host records the post + a non-empty PNG blob
        page.click("[data-ps-action='save']")
        page.wait_for_function("() => window.__savedCount === 1")
        assert page.evaluate("() => window.__lastPng") is True
        # gallery shows the saved post; reopen re-renders a stage
        page.wait_for_selector("[data-ps-gallery-item]")
        page.click("[data-ps-action='reopen']")
        page.wait_for_selector("[data-ps-stage]")
        browser.close()


def test_editor_theme_and_headline_font_switch():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # default theme is dark_premium -> radial-gradient background
        bg0 = page.evaluate(
            "() => getComputedStyle(document.querySelector('[data-ps-stage]')).backgroundImage"
        )
        assert "gradient" in bg0
        # switch to light_luxury -> solid cream background (no gradient image)
        page.click("[data-ps-theme='light_luxury']")
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('[data-ps-stage]'))"
            ".backgroundImage === 'none'"
        )
        # pick Manrope for the headline -> headline font-family updates
        # (light_luxury default is Playfair Display, so Manrope proves the picker
        # actually overrides the theme default — a vacuous Playfair pick would not)
        page.click("[data-ps-fontopt='manrope']")
        page.wait_for_function(
            "() => /Manrope/.test("
            "getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily)"
        )
        browser.close()


def test_selection_outline_and_inspector_slot():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # nothing selected initially
        assert page.get_attribute("[data-ps-inspector]", "data-ps-selected") == ""
        # click the headline -> it becomes selected and gets an outline
        page.click("[data-ps-el='title.headline']")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-inspector]').dataset.psSelected === 'title.headline'")
        assert page.evaluate(
            "() => /solid/.test(document.querySelector('[data-ps-el=\"title.headline\"]').style.outline)")
        # click a photo block -> block selection
        page.click("[data-ps-block='1']")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-inspector]').dataset.psSelected === 'block:1'")
        browser.close()
