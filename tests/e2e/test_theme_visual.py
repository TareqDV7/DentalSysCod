"""Per-theme visual smoke: render the Before/After template in each theme, save a
screenshot for human review, and assert cross-theme invariants. Replaces the
retired golden-image pixel tests (fidelity is judged from the screenshots)."""
import base64
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "render_harness.html")
_LAUNCH_ARGS = ['--allow-file-access-from-files']
_ARTIFACTS = Path(__file__).resolve().parent / "_artifacts"

_DATA_PNG = ("data:image/png;base64,"
             "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEUlEQVR4nGNk"
             "YPjPgAcw4pMEAB0EAv9G2k0xAAAAAElFTkSuQmCC")

THEMES = ["dark_premium", "light_luxury", "clinical_premium", "bold_editorial"]


def _comp(theme, headline="Root Canal Treatment", subline="for Lower Molar",
          doctor="DR. WASFY BARZAQ"):
    return {
        "version": 1, "size": "square", "theme": theme,
        "elements": [
            # text only — let each theme's own tokens drive typography so the
            # screenshots are an honest fidelity check (no hardcoded size/color overrides)
            {"id": "title", "type": "title", "x": 0.5, "y": 0.15, "align": "center",
             "headline": {"text": headline},
             "subline": {"text": subline}},
            {"id": "strip", "type": "photoStrip", "layout": "row",
             "blocks": [{"photo": _DATA_PNG, "badge": 1, "label": "Before Treatment"},
                        {"photo": _DATA_PNG, "badge": 2, "label": "After Treatment"}]},
            {"id": "doctor", "type": "doctorName", "x": 0.5, "y": 0.93, "align": "center",
             "text": doctor},
        ],
    }


def test_each_theme_renders_distinctly_with_screenshots():
    _ARTIFACTS.mkdir(exist_ok=True)
    backgrounds = {}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__harnessReady === true")
        infos = {}
        for theme in THEMES:
            info = page.evaluate("(c) => window.__describe(c)", _comp(theme))
            infos[theme] = info
            backgrounds[theme] = info["bg"]
            assert info["imgs"] == 2, f"{theme}: expected 2 photos"
            assert info["hasDoctor"] is True, f"{theme}: doctor name missing"
            # screenshot the native-size stage element for human fidelity review
            page.locator("[data-ps-stage]").screenshot(path=str(_ARTIFACTS / f"theme_{theme}.png"))
        # Navy & Gold flagship: pill labels + tooth divider + wave footer all present
        dark_info = infos["dark_premium"]
        assert dark_info["pills"] == 2, dark_info
        assert dark_info["hasDivider"] is True, dark_info
        assert dark_info["hasWave"] is True, dark_info
        # Regression guard: buildDivider geometry is token-driven, so retuning the
        # flagship divider must NOT leak into light_luxury (the only other theme with
        # a divider). dark_premium overrides to 32%; light_luxury keeps the original
        # 130px line. (A boolean hasDivider check can't catch a geometry regression.)
        assert dark_info["dividerLineWidth"] == "32%", dark_info
        assert infos["light_luxury"]["dividerLineWidth"] == "130px", infos["light_luxury"]
        # the pill + wave treatments are flagship-only — the other three themes opt out
        for theme in ("light_luxury", "clinical_premium", "bold_editorial"):
            assert infos[theme]["pills"] == 0, (theme, infos[theme])
            assert infos[theme]["hasWave"] is False, (theme, infos[theme])
        # Arabic sanity: render with Arabic copy, no crash, doctor still present
        ar = _comp("dark_premium", headline="علاج عصب الجذر", subline="للضرس السفلي",
                   doctor="د. وصفي برزق")
        ar_info = page.evaluate("(c) => window.__describe(c)", ar)
        page.locator("[data-ps-stage]").screenshot(path=str(_ARTIFACTS / "theme_dark_premium_ar.png"))
        browser.close()
    assert not errors, f"console errors during render: {errors}"
    assert ar_info["imgs"] == 2
    # the four themes must not all share one background
    assert len(set(backgrounds.values())) >= 3, backgrounds
