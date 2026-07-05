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


def test_export_after_edits_is_untainted():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # edit text + add photos, then save -> the fake host gets a non-empty PNG
        page.click("[data-ps-el='title.headline']")
        page.wait_for_selector("[data-ps-inspector-text]")
        page.fill("[data-ps-inspector-text] [data-ps-field='text']", "Crowns")
        page.click("[data-ps-action='add-photos']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length === 2")
        page.click("[data-ps-action='save']")
        page.wait_for_function("() => window.__savedCount === 1")
        assert page.evaluate("() => window.__lastPng") is True   # PNG produced => canvas not tainted
        browser.close()


def test_drag_moves_an_element_and_updates_pos():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # measure the doctor element, drag it left by ~40 display px
        box = page.eval_on_selector(
            "[data-ps-el='doctor']",
            "n => { const b = n.getBoundingClientRect();"
            "  return { x: b.left + b.width/2, y: b.top + b.height/2 }; }")
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"] - 40, box["y"], steps=6)
        page.mouse.up()
        # the doctor element's centre moved left on the stage
        moved = page.eval_on_selector(
            "[data-ps-el='doctor']",
            "n => n.getBoundingClientRect().left")
        assert moved < box["x"] - 20, moved
        browser.close()


def test_drag_snaps_to_canvas_center_and_shows_guide():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        stage = page.eval_on_selector("[data-ps-stage]",
            "n => { const b = n.getBoundingClientRect();"
            "  return { left: b.left, top: b.top, w: b.width, h: b.height }; }")
        # grab the doctor, drag its centre a few px off the canvas centre-x
        box = page.eval_on_selector("[data-ps-el='doctor']",
            "n => { const b = n.getBoundingClientRect();"
            "  return { x: b.left + b.width/2, y: b.top + b.height/2 }; }")
        target_x = stage["left"] + stage["w"] / 2 + 3   # ~3px right of centre -> within snap threshold
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(target_x, box["y"], steps=8)
        # a guide line is visible mid-drag ...
        assert page.query_selector("[data-ps-guide]") is not None
        page.mouse.up()
        # ... and the doctor snapped to exact canvas centre-x (pos.x == 0.5)
        cx = page.eval_on_selector("[data-ps-el='doctor']",
            "n => { const b = n.getBoundingClientRect();"
            "  const s = n.closest('[data-ps-stage]').getBoundingClientRect();"
            "  return (b.left + b.width/2 - s.left) / s.width; }")
        assert abs(cx - 0.5) < 0.01, cx
        # guides cleared after drop
        assert page.query_selector("[data-ps-guide]") is None
        browser.close()


def test_arrow_keys_nudge_selected_element():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-el='doctor']")   # select the doctor
        before = page.eval_on_selector("[data-ps-el='doctor']",
            "n => n.getBoundingClientRect().top")
        # Shift+ArrowDown = 10 canvas-px -> 10 * (360/1080) ~= 3.3 display-px down
        page.keyboard.down("Shift")
        page.keyboard.press("ArrowDown")
        page.keyboard.up("Shift")
        after = page.eval_on_selector("[data-ps-el='doctor']",
            "n => n.getBoundingClientRect().top")
        assert after > before, (before, after)
        browser.close()


def test_arrow_keys_nudge_selected_pill_moves_pill_not_panel():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # default theme (dark_premium) renders pill labels alongside panels
        page.wait_for_selector("[data-ps-pill-block='0']")
        panel_before = page.eval_on_selector("[data-ps-block='0']",
            "n => n.getBoundingClientRect().top")
        pill_before = page.eval_on_selector("[data-ps-pill-block='0']",
            "n => n.getBoundingClientRect().top")
        page.click("[data-ps-pill-block='0']")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-inspector]').dataset.psSelected === 'block:0'")
        page.keyboard.down("Shift")
        page.keyboard.press("ArrowDown")
        page.keyboard.up("Shift")
        panel_after = page.eval_on_selector("[data-ps-block='0']",
            "n => n.getBoundingClientRect().top")
        pill_after = page.eval_on_selector("[data-ps-pill-block='0']",
            "n => n.getBoundingClientRect().top")
        assert pill_after > pill_before, (pill_before, pill_after)
        assert panel_after == panel_before, (panel_before, panel_after)
        browser.close()


def test_export_after_drag_is_untainted():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-action='add-photos']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length === 2")
        # drag a panel, then save -> the fake host still receives a non-empty PNG
        box = page.eval_on_selector("[data-ps-block='0']",
            "n => { const b = n.getBoundingClientRect();"
            "  return { x: b.left + b.width/2, y: b.top + b.height/2 }; }")
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"] + 30, box["y"] + 20, steps=6)
        page.mouse.up()
        page.click("[data-ps-action='save']")
        page.wait_for_function("() => window.__savedCount === 1")
        assert page.evaluate("() => window.__lastPng") is True     # PNG produced => canvas not tainted
        # no editor chrome (selection outline / snap guides) leaked into the composition JSON
        tj_raw = page.evaluate("() => window.__lastTemplateJson || ''")
        assert "data-ps-guide" not in tj_raw and "outline" not in tj_raw, tj_raw
        browser.close()


def test_resize_handle_br_grows_panel_others_unaffected():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-resize-handle='br']")
        before0 = page.eval_on_selector("[data-ps-block='0']",
            "n => { const b = n.getBoundingClientRect(); return { w: b.width, h: b.height }; }")
        before1 = page.eval_on_selector("[data-ps-block='1']",
            "n => { const b = n.getBoundingClientRect(); return { w: b.width, left: b.left }; }")
        handle = page.eval_on_selector("[data-ps-resize-handle='br']",
            "n => { const b = n.getBoundingClientRect(); return { x: b.left + b.width/2, y: b.top + b.height/2 }; }")
        page.mouse.move(handle["x"], handle["y"])
        page.mouse.down()
        page.mouse.move(handle["x"] + 40, handle["y"] + 30, steps=6)
        page.mouse.up()
        after0 = page.eval_on_selector("[data-ps-block='0']",
            "n => { const b = n.getBoundingClientRect(); return { w: b.width, h: b.height }; }")
        after1 = page.eval_on_selector("[data-ps-block='1']",
            "n => { const b = n.getBoundingClientRect(); return { w: b.width, left: b.left }; }")
        assert after0["w"] > before0["w"] + 10, (before0, after0)
        assert after0["h"] > before0["h"] + 5, (before0, after0)
        assert abs(after1["w"] - before1["w"]) < 2, (before1, after1)
        assert abs(after1["left"] - before1["left"]) < 2, (before1, after1)
        browser.close()


def test_resize_handle_tl_keeps_opposite_corner_anchored():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-resize-handle='tl']")
        before_br = page.eval_on_selector("[data-ps-block='0']",
            "n => { const b = n.getBoundingClientRect(); return { x: b.right, y: b.bottom }; }")
        handle = page.eval_on_selector("[data-ps-resize-handle='tl']",
            "n => { const b = n.getBoundingClientRect(); return { x: b.left + b.width/2, y: b.top + b.height/2 }; }")
        page.mouse.move(handle["x"], handle["y"])
        page.mouse.down()
        page.mouse.move(handle["x"] - 20, handle["y"] - 15, steps=6)
        page.mouse.up()
        after_br = page.eval_on_selector("[data-ps-block='0']",
            "n => { const b = n.getBoundingClientRect(); return { x: b.right, y: b.bottom }; }")
        assert abs(after_br["x"] - before_br["x"]) < 2, (before_br, after_br)
        assert abs(after_br["y"] - before_br["y"]) < 2, (before_br, after_br)
        browser.close()


def test_export_after_resize_is_untainted():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-action='add-photos']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length === 2")
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-resize-handle='br']")
        handle = page.eval_on_selector("[data-ps-resize-handle='br']",
            "n => { const b = n.getBoundingClientRect(); return { x: b.left + b.width/2, y: b.top + b.height/2 }; }")
        page.mouse.move(handle["x"], handle["y"])
        page.mouse.down()
        page.mouse.move(handle["x"] + 30, handle["y"] + 20, steps=6)
        page.mouse.up()
        page.click("[data-ps-action='save']")
        page.wait_for_function("() => window.__savedCount === 1")
        assert page.evaluate("() => window.__lastPng") is True
        browser.close()


def test_double_width_toggle_hides_and_restores_next_pill():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        assert page.query_selector("[data-ps-pill-block='1']") is not None
        page.click("[data-ps-block='0']")
        page.click("[data-ps-action='toggle-double']")
        assert page.query_selector("[data-ps-pill-block='1']") is None
        page.click("[data-ps-action='toggle-double']")
        assert page.query_selector("[data-ps-pill-block='1']") is not None
        browser.close()


def test_per_block_label_typography_is_independent():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # dark_premium is a pill-style theme -> the label text lives in the
        # SIBLING pill ([data-ps-pill-block]), not inside the panel card.
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-inspector-block] [data-ps-field='size']")
        page.eval_on_selector("[data-ps-inspector-block] [data-ps-field='size']",
            "n => { n.value = '60'; n.dispatchEvent(new Event('input', { bubbles: true })); }")
        size0 = page.eval_on_selector("[data-ps-pill-block='0']",
            "n => parseFloat(getComputedStyle(n.lastElementChild).fontSize)")
        size1 = page.eval_on_selector("[data-ps-pill-block='1']",
            "n => parseFloat(getComputedStyle(n.lastElementChild).fontSize)")
        assert size0 != size1, (size0, size1)
        browser.close()


def test_touch_profile_grows_resize_handle():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri() + "?profile=touch")
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-resize-handle='br']")
        size = page.eval_on_selector("[data-ps-resize-handle='br']",
            "n => { const b = n.getBoundingClientRect(); return { w: b.width, h: b.height }; }")
        # mouse profile renders ~10 screen-px, touch renders ~32 — 20 cleanly separates them
        assert size["w"] > 20 and size["h"] > 20, size
        browser.close()
