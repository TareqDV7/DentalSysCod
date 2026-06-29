import base64
import struct
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "render_harness.html")

# Chromium blocks file:// cross-origin ES module imports by default.
# --allow-file-access-from-files lifts the restriction so the harness can
# import ../render.js and ../rasterize.js via <script type="module">.
_LAUNCH_ARGS = ['--allow-file-access-from-files']

_DATA_PNG = ("data:image/png;base64,"
             "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEUlEQVR4nGNk"
             "YPjPgAcw4pMEAB0EAv9G2k0xAAAAAElFTkSuQmCC")

_COMP = {
    "version": 1, "size": "square", "theme": "dark_premium",
    "elements": [
        {"id": "title", "type": "title", "x": 0.5, "y": 0.10, "align": "center",
         "headline": {"text": "Root Canal Treatment", "size": 64, "weight": 800,
                      "color": "#ffffff", "letterSpacing": 1},
         "subline": {"text": "for Lower Molar", "size": 40, "weight": 500,
                     "color": "#5fd3c8", "letterSpacing": 0}},
        {"id": "strip", "type": "photoStrip", "layout": "row",
         "blocks": [{"photo": _DATA_PNG, "badge": 1, "label": "Before Treatment"},
                    {"photo": _DATA_PNG, "badge": 2, "label": "After Treatment"}],
         "labelStyle": {"size": 28, "weight": 600, "color": "#cfd8e3"}},
        {"id": "doctor", "type": "doctorName", "x": 0.5, "y": 0.93, "align": "center",
         "text": "DR. WASFY BARZAQ", "size": 34, "weight": 700,
         "color": "#c9a227", "letterSpacing": 4},
    ],
}


def _png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def _goto_ready(page, url):
    """Navigate to the harness and wait until the ES module has set all hooks."""
    page.goto(url)
    page.wait_for_function("() => window.__harnessReady === true")


def test_rasterize_exports_untainted_png():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page(device_scale_factor=2)
        _goto_ready(page, HARNESS.as_uri())
        page.evaluate("(c) => window.__buildStage(c)", _COMP)
        data_url = page.evaluate("() => window.__rasterize()")
        err = page.evaluate("() => window.__rasterizeError")
        browser.close()
    assert err is None, f"rasterizer threw: {err}"
    assert data_url.startswith("data:image/png;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    w, h = _png_size(raw)
    assert (w, h) == (2160, 2160), (w, h)   # 1080 logical * scale 2
    assert len(raw) > 20_000, f"suspiciously small PNG: {len(raw)} bytes"


def test_render_structure_before_after():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        info = page.evaluate("(c) => window.__describe(c)", _COMP)
        browser.close()
    assert info["size"] == [1080, 1080]
    assert info["imgs"] == 2                       # two photo blocks rendered
    assert info["badges"] == ["1", "2"]            # numbered badges in order
    assert info["hasDoctor"] is True


def test_render_story_size():
    comp = dict(_COMP, size="story")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        info = page.evaluate("(c) => window.__describe(c)", comp)
        browser.close()
    assert info["size"] == [1080, 1920]


def test_theme_changes_background_and_divider():
    dark = _COMP
    light = dict(_COMP, theme="light_luxury")
    clinical = dict(_COMP, theme="clinical_premium")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        d = page.evaluate("(c) => window.__describe(c)", dark)
        l = page.evaluate("(c) => window.__describe(c)", light)
        c = page.evaluate("(c) => window.__describe(c)", clinical)
        browser.close()
    assert d["bg"] != l["bg"], "themes must produce different backgrounds"
    assert d["hasDivider"] is True            # dark_premium has the tooth divider
    assert c["hasDivider"] is False           # clinical_premium has none
    assert "gradient" in d["bg"]              # navy radial glow, not a flat fill


def test_headline_uses_theme_font_family():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        page.evaluate("(c) => window.__buildStage(c)", dict(_COMP, theme="light_luxury"))
        fam = page.evaluate(
            "() => getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily"
        )
        browser.close()
    assert "Playfair Display" in fam
