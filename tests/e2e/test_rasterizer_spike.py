import base64
import struct
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright not installed in this environment",
)
from playwright.sync_api import sync_playwright  # noqa: E402

SPIKE = (Path(__file__).resolve().parents[1].parent
         / "static" / "post_studio" / "spike" / "spike.html")


def _png_size(data: bytes):
    # PNG: 8-byte signature, then IHDR (length+type+width+height...)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_spike_rasterizes_hard_composition_without_taint():
    url = SPIKE.as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto(url)
        # Run the in-page rasterizer; this rejects on SecurityError (tainted canvas).
        data_url = page.evaluate("() => window.__spikeRasterize()")
        err = page.evaluate("() => window.__spikeError")
        # Sample a background pixel to verify CSS styles actually rasterized.
        # Device-pixel (20,20) = logical (10,10) — top-left corner, well outside
        # the card and text, deep in the outer stop of the radial gradient (#060f1c).
        # An unstyled/transparent capture would yield r=g=b=0,a=0 (transparent) or
        # r=g=b=255,a=255 (white default), not a dark opaque navy pixel.
        bg_pixel = page.evaluate("() => window.__spikeSamplePixel(20, 20)")
        browser.close()

    assert err is None, f"rasterizer threw: {err}"
    assert data_url.startswith("data:image/png;base64,"), data_url[:40]
    raw = base64.b64decode(data_url.split(",", 1)[1])
    w, h = _png_size(raw)
    # 1080 logical px at device_scale_factor=2 → 2160 device px.
    assert (w, h) == (2160, 2160), (w, h)
    # Non-blank: a fully-uniform image would compress tiny. The gradient + text
    # guarantees a substantial PNG.
    assert len(raw) > 20_000, f"suspiciously small PNG: {len(raw)} bytes"

    # Fidelity check: the background pixel must be dark opaque navy, proving that
    # the radial-gradient (and all other computed CSS) actually rasterized.
    # Outer gradient stop is #060f1c = rgb(6, 15, 28); allow ±40 for anti-aliasing
    # and gamma differences across Chromium builds, but it must be clearly dark.
    assert bg_pixel is not None, "pixel sampler returned None (canvas not stored)"
    r, g, b, a = bg_pixel
    assert a == 255, (
        f"background pixel is transparent (a={a}): computed styles were NOT inlined"
    )
    assert r < 80 and g < 80 and b < 100, (
        f"background pixel is not dark navy: rgb({r},{g},{b}) — "
        "radial-gradient did not rasterize; computed styles likely missing"
    )
