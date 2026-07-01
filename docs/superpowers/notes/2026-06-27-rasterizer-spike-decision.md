# Rasterizer spike decision (2026-06-27)

Technique tested: SVG <foreignObject> → Image → canvas.drawImage → canvas.toDataURL
(the core of html-to-image), against radial-gradient bg, rounded/glow card,
letter-spaced + mixed-weight text, embedded same-origin (data-URL) image,
Arabic RTL text, and a @font-face web font (Manrope-Regular, base64-embedded),
at devicePixelRatio scale.

Result: PASS.
- Canvas taint (toDataURL SecurityError): none
- Output dimensions: 2160×2160 px (1080 logical × devicePixelRatio 2) — correct
- Output PNG size: >20 000 bytes — confirms gradient + text content rasterized
- Fidelity verified by rendered-pixel check: background pixel at device-px (20,20)
  is dark opaque navy (outer radial-gradient stop #060f1c), proving CSS styles
  including `background: radial-gradient(...)` actually rasterized in the isolated
  SVG render context (not just unstyled raw text on a transparent/white canvas)

## Test evidence

```
python -m pytest tests/e2e/test_rasterizer_spike.py -v
1 passed in 2.32s  (exit 0)
```

Test: `tests/e2e/test_rasterizer_spike.py::test_spike_rasterizes_hard_composition_without_taint`
Harness: Playwright Chromium, device_scale_factor=2, file:// URL (no server).

Assertions in the strengthened test:
1. No rasterizer error (`window.__spikeError is None`)
2. Output is `data:image/png;base64,...`
3. Decoded PNG dimensions == 2160×2160
4. PNG size > 20 000 bytes
5. **NEW — pixel fidelity**: `window.__spikeSamplePixel(20, 20)` returns a dark
   opaque pixel (a==255, r<80, g<80, b<100), proving the radial-gradient
   background rendered. An unstyled capture yields transparent or white there.

## Decision for P2b export

PASS → adopt a vendored `html-to-image` (or the minimal foreignObject rasterizer
above, hardened) as `static/post_studio/vendor/rasterize.js`.

Constraints proven safe — P2b export MUST honour:
1. Embed all fonts as `data:` URLs (not CDN/network references) and `await document.fonts.ready` before capture.
2. Ensure all `<img>` sources are same-origin or `data:` URLs before calling `toDataURL` — cross-origin image sources will taint the canvas and throw `SecurityError`.
3. Use `devicePixelRatio` (or a fixed scale ≥ 2) for the canvas dimensions to hit full export resolution.
4. **NEW — inline computed styles before serialization**: Clone every element and
   copy `window.getComputedStyle(el)` into the clone's `style` attribute before
   calling `XMLSerializer.serializeToString`. Without this, `XMLSerializer` only
   carries class names; the isolated SVG render context has no page stylesheet, so
   radial-gradient, colors, font-weight, letter-spacing, direction:rtl, and image
   dimensions all revert to browser defaults. This is the bug the original spike
   silently had.
5. **NEW — embed @font-face inside the foreignObject**: Inject a `<style>` block
   containing the full `@font-face` rule (with `data:` URL src) into the
   foreignObject wrapper div. Even with computed styles inlined, `font-family`
   references an unresolvable name in the isolated context without the @font-face
   declaration.

If FAIL had been recorded → fall back to a hand-rolled Canvas 2D renderer that
mirrors the composition (separate just-in-time P2b task). Reason recorded above.
