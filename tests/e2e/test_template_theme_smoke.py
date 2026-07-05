from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "render_harness.html")

_LAUNCH_ARGS = ['--allow-file-access-from-files']


def _goto_ready(page, uri):
    page.goto(uri)
    page.wait_for_function("() => window.__harnessReady === true")


def test_every_template_theme_combination_renders_en_and_ar():
    """P5 QA sweep: every template x theme x language combo must render
    without throwing, show the strip's blocks, and show the doctor name."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        results = page.evaluate("() => window.__smokeMatrix()")
        browser.close()

    failures = [r for r in results if not r["ok"]]
    assert not failures, failures

    expected_blocks = {
        "before_after": 2, "multi_phase": 3, "quad_grid": 4, "single_feature": 1,
    }
    for r in results:
        assert r["blockCount"] == expected_blocks[r["template"]], r
        assert r["doctorText"] == r["doctorName"], r
        assert "title.headline" in r["psEls"] and "title.subline" in r["psEls"], r
        assert "doctor" in r["psEls"], r

    # sanity: the matrix actually covers everything (4 templates x 4 themes x 2 langs)
    assert len(results) == 4 * 4 * 2, len(results)
