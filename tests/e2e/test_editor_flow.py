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


def test_headline_font_via_inspector_and_text_edit():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # switch to light_luxury (Playfair default) so a Manrope pick is non-vacuous
        page.click("[data-ps-theme='light_luxury']")
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('[data-ps-stage]')).backgroundImage === 'none'")
        # select the headline -> text inspector appears
        page.click("[data-ps-el='title.headline']")
        page.wait_for_selector("[data-ps-inspector-text]")
        # pick Manrope in the inspector font dropdown -> headline font-family updates
        page.select_option("[data-ps-inspector-text] [data-ps-field='font']", "Manrope")
        page.wait_for_function(
            "() => /Manrope/.test(getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily)")
        # edit the headline text -> the rendered headline updates
        page.fill("[data-ps-inspector-text] [data-ps-field='text']", "Veneers")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-headline]').textContent === 'Veneers'")
        # the global font picker is gone
        assert page.query_selector("[data-ps-fontopt]") is None
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


def test_block_inspector_label_move_add_remove():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # select block 0 -> block inspector
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-inspector-block]")
        # edit its label -> the rendered label/pill text updates
        page.fill("[data-ps-inspector-block] [data-ps-field='label']", "Day 1")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-stage]').textContent.includes('Day 1')")
        # add a block -> 3 blocks, badges renumber 1..3
        page.click("[data-ps-inspector-block] [data-ps-action='add-block']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-block]').length === 3")
        # remove the currently selected block -> back to 2
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-inspector-block]")
        page.click("[data-ps-inspector-block] [data-ps-action='remove']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-block]').length === 2")
        browser.close()


def test_language_toggle_rerenders_and_preserves_comp():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # set a custom headline via the inspector
        page.click("[data-ps-el='title.headline']")
        page.wait_for_selector("[data-ps-inspector-text]")
        page.fill("[data-ps-inspector-text] [data-ps-field='text']", "Implants")
        page.wait_for_function("() => document.querySelector('[data-ps-headline]').textContent === 'Implants'")
        # flip the document language to Arabic
        page.evaluate("() => document.documentElement.setAttribute('lang', 'ar')")
        # editor re-mounts in Arabic (a known Arabic chrome string appears) ...
        page.wait_for_function("() => document.body.textContent.includes('القالب اللوني')")
        # ... and the custom composition survives the re-mount
        page.wait_for_function("() => document.querySelector('[data-ps-headline]').textContent === 'Implants'")
        browser.close()
