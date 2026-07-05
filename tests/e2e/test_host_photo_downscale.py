from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "host_harness.html")

# Chromium blocks file:// cross-origin ES module imports by default.
_LAUNCH_ARGS = ['--allow-file-access-from-files']


def _goto_ready(page, uri):
    page.goto(uri)
    page.wait_for_function("() => window.__ready === true")


def test_downscale_shrinks_a_photo_larger_than_the_cap():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        max_dim = page.evaluate("() => window.__MAX_PHOTO_DIM")
        assert max_dim == 1600
        raw = page.evaluate("() => window.__makeDataUrl(4000, 3000)")
        result = page.evaluate("(u) => window.__downscaleAndMeasure(u, window.__MAX_PHOTO_DIM)", raw)
        browser.close()
    # longest edge (width, 4000) capped to 1600; aspect ratio preserved (4:3)
    assert result["w"] == 1600, result
    assert abs(result["h"] - 1200) <= 1, result
    # the downscaled data URL is meaningfully smaller than the original
    assert result["outLength"] < len(raw) * 0.5, (result["outLength"], len(raw))


def test_downscale_leaves_a_photo_already_within_the_cap_unchanged():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        raw = page.evaluate("() => window.__makeDataUrl(800, 600)")
        result = page.evaluate("(u) => window.__downscaleAndMeasure(u, window.__MAX_PHOTO_DIM)", raw)
        browser.close()
    assert result["w"] == 800, result
    assert result["h"] == 600, result
    assert result["outDataUrl"] == raw, "small photo should pass through unmodified"
