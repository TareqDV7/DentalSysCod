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


def test_custom_fonts_available_and_export_still_untainted():
    themed = dict(_COMP, theme="light_luxury")   # serif headline -> needs Playfair
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page(device_scale_factor=2)
        _goto_ready(page, HARNESS.as_uri())
        playfair = page.evaluate("() => window.__fontLoaded(\"700 40px 'Playfair Display'\")")
        manrope = page.evaluate("() => window.__fontLoaded(\"800 40px 'Manrope'\")")
        page.evaluate("(c) => window.__buildStage(c)", themed)
        data_url = page.evaluate("() => window.__rasterize()")
        err = page.evaluate("() => window.__rasterizeError")
        browser.close()
    assert playfair is True, "Playfair @font-face did not load in the document"
    assert manrope is True, "Manrope @font-face did not load in the document"
    assert err is None, f"rasterizer threw: {err}"
    assert data_url.startswith("data:image/png;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 20_000


def test_arabic_headline_resolves_to_cairo_font():
    ar = {
        "version": 1, "size": "square", "theme": "dark_premium",
        "elements": [
            {"id": "title", "type": "title", "x": 0.5, "y": 0.10, "align": "center",
             "headline": {"text": "علاج عصب الجذر"},
             "subline": {"text": "للضرس السفلي"}},
        ],
    }
    latin = {
        "version": 1, "size": "square", "theme": "dark_premium",
        "elements": [
            {"id": "title", "type": "title", "x": 0.5, "y": 0.10, "align": "center",
             "headline": {"text": "Root Canal Treatment"}},
        ],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        page.evaluate("(c) => window.__buildStage(c)", ar)
        ar_fam = page.evaluate(
            "() => getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily")
        page.evaluate("(c) => window.__buildStage(c)", latin)
        latin_fam = page.evaluate(
            "() => getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily")
        browser.close()
    assert "Cairo" in ar_fam, f"Arabic headline must resolve to Cairo, got {ar_fam}"
    assert "Cairo" not in latin_fam, f"Latin headline must not use Cairo, got {latin_fam}"
    assert "Poppins" in latin_fam, f"Latin headline must use the theme font, got {latin_fam}"


def test_pill_labels_for_dark_premium_and_corner_badge_for_clinical():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        dark = page.evaluate("(c) => window.__describe(c)", _COMP)
        clinical = page.evaluate("(c) => window.__describe(c)", dict(_COMP, theme="clinical_premium"))
        # dark_premium pills carry their number + label text
        dark_pills = page.evaluate(
            "(c) => { window.__buildStage(c);"
            "  return Array.from(document.querySelectorAll('[data-ps-pill]'))"
            "    .map(p => p.textContent); }", _COMP)
        # frame size comes from the theme's per-block panelW/panelH tokens (P4b-2:
        # the frame's height is now an explicit px value, not a CSS aspect-ratio,
        # so free-aspect resize can set width/height independently).
        page.evaluate("(c) => window.__buildStage(c)", _COMP)
        frame_rect = page.evaluate(
            "() => { const r = document.querySelector('[data-ps-frame]').getBoundingClientRect();"
            "  return { w: Math.round(r.width), h: Math.round(r.height) }; }")
        browser.close()
    assert dark["pills"] == 2, "dark_premium renders one pill per block"
    assert clinical["pills"] == 0, "clinical_premium keeps corner-badge labels (no pills)"
    assert dark["badges"] == ["1", "2"], "pill number circles still detected as numbered badges"
    assert all("Treatment" in t for t in dark_pills), dark_pills   # label text inside the pill
    assert abs(frame_rect["w"] - 250) <= 2 and abs(frame_rect["h"] - 320) <= 2, (
        f"portrait panel size (250x320) expected, got {frame_rect}")


def test_wave_footer_present_for_dark_premium_only():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        dark = page.evaluate("(c) => window.__describe(c)", _COMP)
        clinical = page.evaluate("(c) => window.__describe(c)", dict(_COMP, theme="clinical_premium"))
        browser.close()
    assert dark["hasWave"] is True, "dark_premium must render the wave footer"
    assert dark["wavePaths"] == 3, "wave footer has 3 sine layers"
    assert clinical["hasWave"] is False, "themes without waveFooter.enabled render no wave"


def test_identity_hooks_and_pill_labelstyle_override():
    # P4b-2: labelStyle moved from the shared strip-level field to per-block
    # (spec: "strip.labelStyle is dropped entirely once every block carries
    # its own"). Supply pos/panelPos/panelW/panelH/labelStyle directly so
    # ensureLayout treats this as already-seeded and doesn't overwrite the
    # per-block override with the theme default.
    comp = {
        "version": 1, "size": "square", "theme": "dark_premium",
        "elements": [
            {"id": "title", "type": "title", "pos": {"x": 0.5, "y": 0.15},
             "headline": {"text": "Root Canal"}, "subline": {"text": "Lower Molar"}},
            {"id": "strip", "type": "photoStrip", "panelW": 250 / 1080, "panelH": 320 / 1080, "gap": 16 / 1080,
             "blocks": [
                 {"photo": None, "badge": 1, "label": "Before",
                  "panelPos": {"x": 16 / 1080, "y": 360 / 1080}, "panelW": 250 / 1080, "panelH": 320 / 1080,
                  "pillPos": {"x": 16 / 1080, "y": 708 / 1080}, "pill": {"width": "single"},
                  "labelStyle": {"font": "Poppins", "size": 44, "weight": 400, "color": "#F5F5F0"}},
                 {"photo": None, "badge": 2, "label": "After",
                  "panelPos": {"x": 300 / 1080, "y": 360 / 1080}, "panelW": 250 / 1080, "panelH": 320 / 1080,
                  "pillPos": {"x": 300 / 1080, "y": 708 / 1080}, "pill": {"width": "single"},
                  "labelStyle": {"font": "Poppins", "size": 44, "weight": 400, "color": "#F5F5F0"}},
             ]},
            {"id": "doctor", "type": "doctorName", "pos": {"x": 0.5, "y": 0.93}, "text": "DR. WASFY"},
        ],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__harnessReady === true")
        info = page.evaluate("(c) => window.__describe(c)", comp)
        browser.close()
    assert set(info["psEls"]) == {"title.headline", "title.subline", "doctor"}, info
    assert info["blockCount"] == 2, info
    # pill label honors each block's own labelStyle override (proves buildPill
    # reads b.labelStyle, the P4b-2 per-block model)
    assert info["pillLabelSize"] == "44px", info


_QUAD = {
    "version": 1, "size": "square", "theme": "dark_premium",
    "elements": [
        {"id": "title", "type": "title",
         "headline": {"text": "Case"}, "subline": {"text": "Study"}},
        {"id": "strip", "type": "photoStrip",
         "blocks": [{"photo": None, "badge": 1, "label": "One"},
                    {"photo": None, "badge": 2, "label": "Two"},
                    {"photo": None, "badge": 3, "label": "Three", "pill": {"width": "double"}},
                    {"photo": None, "badge": 4, "label": "Four"}]},
        {"id": "doctor", "type": "doctorName", "text": "DR. WASFY BARZAQ"},
    ],
}


def test_dark_premium_seeds_exact_gopng_grid():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        info = page.evaluate("(c) => window.__describe(c)", _QUAD)
        browser.close()
    panels = info["rects"]["panels"]
    assert len(panels) == 4, info
    # panel row at y=360, size 250x320, first panel x=16 (centered 4-up row)
    assert abs(panels[0]["top"] - 360) <= 2, panels
    assert abs(panels[0]["w"] - 250) <= 2 and abs(panels[0]["h"] - 320) <= 2, panels
    assert abs(panels[0]["left"] - 16) <= 2, panels
    assert abs(panels[1]["left"] - (16 + 266)) <= 2, panels
    # pill row at y=708
    assert abs(info["rects"]["pills"][0]["top"] - 708) <= 2, info["rects"]["pills"]
    # doctor centered at y=920
    d = info["rects"]["doctor"]
    assert abs((d["top"] + d["h"] / 2) - 920) <= 4, d
    # the 3rd pill is double-width (516), others single (250)
    assert abs(info["pillWidths"][2] - 516) <= 2, info["pillWidths"]
    assert abs(info["pillWidths"][0] - 250) <= 2, info["pillWidths"]


_UNEVEN = {
    "version": 1, "size": "square", "theme": "dark_premium",
    "elements": [
        {"id": "title", "type": "title", "pos": {"x": 0.5, "y": 0.1},
         "headline": {"text": "Case"}, "subline": {"text": "Study"}},
        {"id": "strip", "type": "photoStrip", "panelW": 250 / 1080, "panelH": 320 / 1080, "gap": 16 / 1080,
         "blocks": [
             {"photo": None, "badge": 1, "label": "One",
              "panelPos": {"x": 16 / 1080, "y": 360 / 1080}, "panelW": 200 / 1080, "panelH": 260 / 1080,
              "pillPos": {"x": 16 / 1080, "y": 708 / 1080}, "pill": {"width": "double"},
              "labelStyle": {"font": "Manrope", "size": 28, "weight": 600, "color": "#cfd8e3"}},
             {"photo": None, "badge": 2, "label": "Two",
              "panelPos": {"x": 300 / 1080, "y": 360 / 1080}, "panelW": 350 / 1080, "panelH": 400 / 1080,
              "pillPos": {"x": 300 / 1080, "y": 708 / 1080}, "pill": {"width": "single"},
              "labelStyle": {"font": "Manrope", "size": 28, "weight": 600, "color": "#cfd8e3"}},
         ]},
        {"id": "doctor", "type": "doctorName", "pos": {"x": 0.5, "y": 0.92}, "text": "DR. WASFY BARZAQ"},
    ],
}


def test_per_block_size_renders_independently_and_double_pill_covers_next_edge():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        _goto_ready(page, HARNESS.as_uri())
        info = page.evaluate("(c) => window.__describe(c)", _UNEVEN)
        browser.close()
    panels = info["rects"]["panels"]
    assert abs(panels[0]["w"] - 200) <= 2 and abs(panels[0]["h"] - 260) <= 2, panels
    assert abs(panels[1]["w"] - 350) <= 2 and abs(panels[1]["h"] - 400) <= 2, panels
    # only ONE pill rendered (block 1's own pill is suppressed by block 0's double)
    assert len(info["rects"]["pills"]) == 1, info["rects"]["pills"]
    # the double pill's right edge reaches panel 1's actual right edge (300+350=650)
    pill0 = info["rects"]["pills"][0]
    assert abs((pill0["left"] + pill0["w"]) - 650) <= 2, pill0
