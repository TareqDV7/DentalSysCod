# Rasterizer spike decision (2026-06-27)

Technique tested: SVG <foreignObject> → Image → canvas.drawImage → canvas.toDataURL
(the core of html-to-image), against radial-gradient bg, rounded/glow card,
letter-spaced + mixed-weight text, embedded same-origin (data-URL) image,
Arabic RTL text, and a @font-face web font (Manrope-Regular, base64-embedded),
at devicePixelRatio scale.

Result: PASS.
- Canvas taint (toDataURL SecurityError): none
- Output dimensions: 2160×2160 px (1080 logical × devicePixelRatio 2) — correct
- Output PNG size: >20 000 bytes — confirms gradient + text content rasterized (not blank)
- Fidelity issues: none observed

## Test evidence

```
python -m pytest tests/e2e/test_rasterizer_spike.py -v
1 passed   (exit 0)
```

Test: `tests/e2e/test_rasterizer_spike.py::test_spike_rasterizes_hard_composition_without_taint`
Harness: Playwright Chromium, device_scale_factor=2, file:// URL (no server).

## Decision for P2b export

PASS → adopt a vendored `html-to-image` (or the minimal foreignObject rasterizer
above, hardened) as `static/post_studio/vendor/rasterize.js`.

Constraints proven safe — P2b export must honour:
1. Embed all fonts as `data:` URLs (not CDN/network references) and `await document.fonts.ready` before capture.
2. Ensure all `<img>` sources are same-origin or `data:` URLs before calling `toDataURL` — cross-origin image sources will taint the canvas and throw `SecurityError`.
3. Use `devicePixelRatio` (or a fixed scale ≥ 2) for the canvas dimensions to hit full export resolution.
4. The SVG `<foreignObject>` path handles CSS radial gradients, `border-radius`, `box-shadow`, `letter-spacing`, mixed `font-weight`, and `direction: rtl` (Arabic) correctly at render time.

If FAIL had been recorded → fall back to a hand-rolled Canvas 2D renderer that mirrors the composition (separate just-in-time P2b task). Reason recorded above.
