# Post Studio — P4b-2: Shape & Per-Element Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every photo panel be independently resized (drag corner handles), let a pill's single/double width be toggled from the inspector (auto-hiding the neighbor it covers), and let each block's label carry its own typography instead of one shared style.

**Architecture:** `strip.panelW/panelH/labelStyle` (currently shared across all blocks) move to per-block fields (`blocks[i].panelW/panelH/labelStyle`), seeded by an extended `seedLayout` and migrated additively (without disturbing existing dragged positions) by a new `seedBlockStyle`. `render.js` reads per-block size/style and computes double-pill geometry from the actual next-panel edge instead of an assumed-uniform formula. `editor.js` gains a resize-handle overlay (4 corner squares, editor-only chrome) with its own pointer-drag controller layered next to the existing move-drag. `inspector.js` gets one new toggle button.

**Tech Stack:** Pure-ESM JS modules under `static/post_studio/` (no bundler, no new runtime deps); `node --test` (DOM-free unit); Playwright (`--allow-file-access-from-files`) over `static/post_studio/spike/{editor,render}_harness.html`; pytest harness.

## Global Constraints

- **No new runtime dependencies.** No npm/pip additions.
- **`render.js` stays INLINE STYLES ONLY.** Every style goes through the existing `setStyle`/inline-style helpers; no className-based styling; the untainted foreignObject→canvas PNG export path (`rasterize.js`) is not touched by this plan.
- **Resize handles are editor-only DOM chrome — same invariant class as the P4a selection outline and the P4b-1 snap guides.** They are appended to the rendered stage by `editor.js` AFTER `renderComposition` returns, never inside `render.js`, and never reach `template_json` (export re-renders a fresh, chrome-free stage from `state.comp`, same as every prior phase).
- **Immutability:** every `composition.js` helper returns a NEW composition via `structuredClone` and never mutates its input.
- **Panel resize is free-aspect, clamp-only, no snap.** Width clamps to `[40/1080, 1 − 2·margin]` (fractional of canvas width, `margin` from `themeLayout`), height clamps to `[40/1080, 0.9]` (fractional of canvas height). No snap-to-guides while resizing (P4b-1's snap engine is drag-only, unchanged).
- **Pill width stays a discrete `'single' | 'double'` enum — no freeform pill width.** Whether the *next* block's own pill renders is a **computed** check in `render.js` (`blocks[i-1]?.pill?.width === 'double'`), never a stored flag, so toggling is always reversible with nothing to keep in sync.
- **`strip.panelW`/`panelH` are kept** (not deleted) as the template-default size a freshly `addBlock`-ed block starts at, until the next full `seedLayout` (theme switch) gives it its own. `strip.labelStyle` is fully retired — every block always has its own `labelStyle` after `ensureLayout`.
- **PR remains HELD.** Stack P4b-2 on `feat/post-studio`; do NOT open a PR or push to origin unprompted. Git commit attribution disabled (no Co-Authored-By).

**Base commit:** `b736a11` (P4b-1 HEAD, opus-reviewed).
**Spec:** `docs/superpowers/specs/2026-07-04-post-studio-p4b2-shape-style.md`

---

### Task 1: Per-block panelW/panelH/labelStyle — seedLayout, hasLayout, seedBlockStyle, ensureLayout

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `themeTokens`, `themeLayout` (themes.js); `structuredClone`; existing `CANVAS_DIMS`, `parseAspect`.
- Produces:
  - `seedLayout(comp) -> comp` — extended: alongside `title.pos`/`doctor.pos`/`panelPos`/`pillPos`, now ALSO stamps every block's `panelW`, `panelH` (same formula as before, now written per-block) and `labelStyle` (from `themeTokens(theme).label`). Called by `applyTheme` (full reset — theme switch) and by `ensureLayout` when positions are entirely absent (brand-new/pre-P4b-1 comp).
  - `hasBlockStyle(comp) -> boolean` — true if every block already has `panelW`, `panelH`, and `labelStyle` (or the strip has no blocks).
  - `seedBlockStyle(comp) -> comp` — NEW, additive-only: fills in ONLY missing per-block `panelW`/`panelH`/`labelStyle` from the theme's tokens, WITHOUT touching any existing `pos`/`panelPos`/`pillPos`. Migrates a P4b-1-era saved post (has positions, lacks per-block size/style) without discarding dragged layout.
  - `ensureLayout(comp) -> comp` — extended to run BOTH migrations in sequence: `hasLayout` gate (unchanged, position seeding) THEN `hasBlockStyle` gate (new, size/style seeding).

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import {
  hasBlockStyle, seedBlockStyle,
} from '../../static/post_studio/composition.js';

test('seedLayout stamps per-block panelW/panelH/labelStyle', () => {
  const c = defaultComposition('before_after');   // dark_premium default
  const strip = c.elements.find((e) => e.id === 'strip');
  for (const b of strip.blocks) {
    assert.equal(b.panelW, 250 / 1080);
    assert.equal(b.panelH, 320 / 1080);
    assert.ok(b.labelStyle && b.labelStyle.font);
  }
  assert.equal(hasBlockStyle(c), true);
});

test('ensureLayout migrates a P4b-1-shape comp: fills per-block size/style, preserves existing positions', () => {
  const legacy = {
    version: 1, size: 'square', theme: 'dark_premium',
    elements: [
      { id: 'title', type: 'title', pos: { x: 0.5, y: 0.2 },
        headline: { text: 'X' }, subline: { text: 'Y' } },
      { id: 'strip', type: 'photoStrip', panelW: 0.3, panelH: 0.35, gap: 16 / 1080,
        labelStyle: { font: 'Manrope', size: 28, weight: 600, color: '#cfd8e3' },
        blocks: [
          { photo: null, badge: 1, label: 'A',
            panelPos: { x: 0.1, y: 0.4 }, pillPos: { x: 0.1, y: 0.7 }, pill: { width: 'single' } },
          { photo: null, badge: 2, label: 'B',
            panelPos: { x: 0.45, y: 0.4 }, pillPos: { x: 0.45, y: 0.7 }, pill: { width: 'single' } },
        ] },
      { id: 'doctor', type: 'doctorName', pos: { x: 0.5, y: 0.9 }, text: 'DR. X' },
    ],
  };
  assert.equal(hasBlockStyle(legacy), false);
  const c = ensureLayout(legacy);
  const strip = c.elements.find((e) => e.id === 'strip');
  // dragged positions untouched
  assert.deepEqual(strip.blocks[0].panelPos, { x: 0.1, y: 0.4 });
  assert.deepEqual(strip.blocks[1].pillPos, { x: 0.45, y: 0.7 });
  // per-block size/style filled in
  for (const b of strip.blocks) {
    assert.ok(b.panelW != null && b.panelH != null);
    assert.ok(b.labelStyle && b.labelStyle.font);
  }
  assert.equal(hasBlockStyle(c), true);
});

test('seedBlockStyle never overwrites an existing per-block value', () => {
  const c = defaultComposition('before_after');
  const strip = c.elements.find((e) => e.id === 'strip');
  strip.blocks[0].panelW = 0.5;   // pretend block 0 was already resized
  const seeded = seedBlockStyle(c);
  const strip2 = seeded.elements.find((e) => e.id === 'strip');
  assert.equal(strip2.blocks[0].panelW, 0.5);
  assert.equal(strip2.blocks[1].panelW, 250 / 1080);   // still gets the default
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `hasBlockStyle`/`seedBlockStyle` not exported; `seedLayout`'s blocks have no `panelW`/`labelStyle`.

- [ ] **Step 3: Implement** — edit `static/post_studio/composition.js`.

Replace the whole `seedLayout` function with:

```javascript
export function seedLayout(comp) {
  const next = structuredClone(comp);
  const L = themeLayout(next.theme);
  const [W, H] = CANVAS_DIMS[next.size] || CANVAS_DIMS.square;
  const title = next.elements.find((e) => e.id === 'title');
  const strip = next.elements.find((e) => e.id === 'strip');
  const doctor = next.elements.find((e) => e.id === 'doctor');
  if (title) title.pos = { x: 0.5, y: L.titleY };
  if (doctor) doctor.pos = { x: 0.5, y: L.doctorY };
  if (strip) {
    const n = strip.blocks.length || 1;
    const asp = parseAspect(themeTokens(next.theme).card);
    const panelW = L.panelW != null ? L.panelW : (1 - 2 * L.margin - (n - 1) * L.gap) / n;
    const panelH = L.panelH != null ? L.panelH : panelW * (W / H) * (asp.h / asp.w);
    const rowW = n * panelW + (n - 1) * L.gap;
    const startX = (1 - rowW) / 2;   // centre the row for any panel count
    const panelY = L.panelRowY != null ? L.panelRowY : 0.5 - panelH / 2;
    const pillY = L.pillRowY != null ? L.pillRowY : panelY + panelH + L.gap;
    const labelStyle = themeTokens(next.theme).label;
    strip.panelW = panelW;
    strip.panelH = panelH;
    strip.gap = L.gap;
    strip.blocks = strip.blocks.map((b, i) => ({
      ...b,
      panelPos: { x: startX + i * (panelW + L.gap), y: panelY },
      pillPos: { x: startX + i * (panelW + L.gap), y: pillY },
      pill: { width: (b.pill && b.pill.width) || 'single' },
      panelW,
      panelH,
      labelStyle: { ...labelStyle },
    }));
  }
  return next;
}

// True if every block already carries its own panelW/panelH/labelStyle (or
// the strip has no blocks — nothing to migrate).
export function hasBlockStyle(comp) {
  const strip = (comp.elements || []).find((e) => e.id === 'strip');
  if (!strip || !strip.blocks.length) return true;
  return strip.blocks.every((b) => b.panelW != null && b.panelH != null && b.labelStyle);
}

// Additive-only migration: fills in ONLY missing per-block panelW/panelH/
// labelStyle from the theme's tokens, WITHOUT touching any existing
// pos/panelPos/pillPos. Used to upgrade a P4b-1-era saved post (which has
// positions but no per-block size/style) without discarding dragged layout.
export function seedBlockStyle(comp) {
  const next = structuredClone(comp);
  const strip = next.elements.find((e) => e.id === 'strip');
  if (!strip) return next;
  const L = themeLayout(next.theme);
  const [W, H] = CANVAS_DIMS[next.size] || CANVAS_DIMS.square;
  const n = strip.blocks.length || 1;
  const asp = parseAspect(themeTokens(next.theme).card);
  const fallbackW = L.panelW != null ? L.panelW : (1 - 2 * L.margin - (n - 1) * L.gap) / n;
  const fallbackH = L.panelH != null ? L.panelH : fallbackW * (W / H) * (asp.h / asp.w);
  const labelStyle = themeTokens(next.theme).label;
  strip.blocks = strip.blocks.map((b) => ({
    ...b,
    panelW: b.panelW != null ? b.panelW : fallbackW,
    panelH: b.panelH != null ? b.panelH : fallbackH,
    labelStyle: b.labelStyle || { ...labelStyle },
  }));
  return next;
}
```

Replace the whole `ensureLayout` function with:

```javascript
export function ensureLayout(comp) {
  let next = hasLayout(comp) ? comp : seedLayout(comp);
  next = hasBlockStyle(next) ? next : seedBlockStyle(next);
  return next;
}
```

`hasLayout` itself is unchanged (still just checks `title.pos`) — leave its existing definition as-is.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS (new + all existing composition tests green — the P4b-1 exact-grid tests still assert `panelW===250/1080` etc, now read per-block, still the same value since `seedLayout` stamps the identical computed number onto every block).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/composition.js
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): per-block panelW/panelH/labelStyle (seedLayout + additive legacy migration)"
```

---

### Task 2: setSize — immutable, clamped per-block panel resize

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `themeLayout` (for `margin`); `structuredClone`.
- Produces: `setSize(comp, index, {w, h}) -> comp` — immutable; writes `blocks[index].panelW/panelH`, clamping `w` to `[40/1080, 1 − 2·margin]` and `h` to `[40/1080, 0.9]`. Throws on an out-of-range `index`.

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import { setSize } from '../../static/post_studio/composition.js';

test('setSize writes panelW/panelH immutably and clamps both axes independently', () => {
  const c = defaultComposition('before_after');
  const next = setSize(c, 0, { w: 0.5, h: 0.4 });
  const strip = next.elements.find((e) => e.id === 'strip');
  assert.equal(strip.blocks[0].panelW, 0.5);
  assert.equal(strip.blocks[0].panelH, 0.4);
  // input untouched
  const origStrip = c.elements.find((e) => e.id === 'strip');
  assert.notEqual(origStrip.blocks[0].panelW, 0.5);
  // clamps: too small
  const tiny = setSize(c, 0, { w: 0.001, h: 0.001 });
  assert.equal(tiny.elements.find((e) => e.id === 'strip').blocks[0].panelW, 40 / 1080);
  assert.equal(tiny.elements.find((e) => e.id === 'strip').blocks[0].panelH, 40 / 1080);
  // clamps: too large
  const huge = setSize(c, 0, { w: 5, h: 5 });
  const L = 16 / 1080;   // dark_premium margin token
  assert.ok(Math.abs(huge.elements.find((e) => e.id === 'strip').blocks[0].panelW - (1 - 2 * L)) < 1e-9);
  assert.equal(huge.elements.find((e) => e.id === 'strip').blocks[0].panelH, 0.9);
  assert.throws(() => setSize(c, 9, { w: 0.3, h: 0.3 }));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `setSize` is not exported.

- [ ] **Step 3: Implement** — append to `static/post_studio/composition.js`

```javascript
export const PANEL_SIZE_MIN = 40 / 1080;
export const PANEL_H_MAX = 0.9;

export function setSize(comp, index, wh) {
  const next = structuredClone(comp);
  const strip = next.elements.find((e) => e.id === 'strip');
  if (!strip) throw new Error('composition has no photoStrip');
  if (index < 0 || index >= strip.blocks.length) throw new Error(`bad index ${index}`);
  const L = themeLayout(next.theme);
  const maxW = 1 - 2 * L.margin;
  const w = Math.max(PANEL_SIZE_MIN, Math.min(maxW, Number(wh.w)));
  const h = Math.max(PANEL_SIZE_MIN, Math.min(PANEL_H_MAX, Number(wh.h)));
  strip.blocks[index] = { ...strip.blocks[index], panelW: w, panelH: h };
  return next;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS.

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/composition.js
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): immutable setSize (clamped panel width/height)"
```

---

### Task 3: setPillWidth + block-scoped label typography ref

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `structuredClone`.
- Produces:
  - `setPillWidth(comp, index, width) -> comp` — immutable; `width` must be `'single'` or `'double'`; writes `blocks[index].pill = {width}`. Throws on a bad index or an invalid width value.
  - `setTypography(comp, ref, patch) -> comp` — `ref` scheme extended: `'block:N.label'` now addresses `blocks[N].labelStyle` (replacing the old shared `'strip.label'` ref, which is removed). Behavior for `'title.headline'`/`'title.subline'`/`'doctor'` refs is unchanged.

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import { setPillWidth } from '../../static/post_studio/composition.js';

test('setPillWidth writes single/double immutably and validates the enum', () => {
  const c = defaultComposition('before_after');
  const doubled = setPillWidth(c, 0, 'double');
  assert.equal(doubled.elements.find((e) => e.id === 'strip').blocks[0].pill.width, 'double');
  // input untouched
  assert.equal(c.elements.find((e) => e.id === 'strip').blocks[0].pill.width, 'single');
  assert.throws(() => setPillWidth(c, 0, 'triple'));
  assert.throws(() => setPillWidth(c, 9, 'double'));
});

test('setTypography with a block:N.label ref edits only that block\'s labelStyle', () => {
  const c = defaultComposition('before_after');
  const next = setTypography(c, 'block:1.label', { size: 44, color: '#ff0000' });
  const strip = next.elements.find((e) => e.id === 'strip');
  assert.equal(strip.blocks[1].labelStyle.size, 44);
  assert.equal(strip.blocks[1].labelStyle.color, '#ff0000');
  // block 0 unaffected
  assert.notEqual(strip.blocks[0].labelStyle.size, 44);
});
```

(`setTypography` and `defaultComposition` are already imported at the top of this test file from earlier tasks.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `setPillWidth` not exported; `'block:1.label'` is an unrecognized ref (throws "bad typography ref").

- [ ] **Step 3: Implement** — edit `static/post_studio/composition.js`.

Append `setPillWidth`:

```javascript
export function setPillWidth(comp, index, width) {
  if (width !== 'single' && width !== 'double') throw new Error(`bad pill width: ${width}`);
  const next = structuredClone(comp);
  const strip = next.elements.find((e) => e.id === 'strip');
  if (!strip) throw new Error('composition has no photoStrip');
  if (index < 0 || index >= strip.blocks.length) throw new Error(`bad index ${index}`);
  strip.blocks[index] = { ...strip.blocks[index], pill: { width } };
  return next;
}
```

Replace the `typoTarget` function (currently handles `'strip.label'`) with:

```javascript
// A typography target — text runs plus a block's own label style
// (`ref = 'block:N.label'`). Initializes an empty labelStyle on the clone
// if the block doesn't have one yet (e.g. a just-added block).
function typoTarget(comp, ref) {
  const m = /^block:(\d+)\.label$/.exec(ref);
  if (m) {
    const strip = comp.elements.find((e) => e.id === 'strip');
    const b = strip && strip.blocks[Number(m[1])];
    if (b && !b.labelStyle) b.labelStyle = {};
    return b && b.labelStyle;
  }
  return textRunTarget(comp, ref);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS.

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/composition.js
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): setPillWidth + block-scoped label typography ref (block:N.label)"
```

---

### Task 4: render.js — per-block size/style, double-pill geometry, neighbor auto-hide

**Files:**
- Modify: `static/post_studio/render.js`
- Test: `tests/e2e/test_editor_render.py`

**Interfaces:**
- Consumes: per-block `panelW`/`panelH`/`labelStyle`/`pill.width` (Tasks 1–3); existing `themeTokens`, `typoStyle`, `fontStack`.
- Produces (rendered DOM contract change): each panel's width/height comes from ITS OWN block (`b.panelW`/`b.panelH`, falling back to the strip's template-default `el.panelW`/`el.panelH` for a not-yet-seeded block); the photo frame's height is now explicit (`panelH`) instead of CSS `aspect-ratio` (free-aspect resize, decision 2 in the spec); a double pill's width reaches the actual next-panel's right edge; a pill is not rendered at all when the previous block is `'double'`.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_render.py`

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_render.py::test_per_block_size_renders_independently_and_double_pill_covers_next_edge -q`
Expected: FAIL — panels render at the shared/uniform size, both pills render, double-pill width uses the old uniform formula.

- [ ] **Step 3: Implement** — edit `static/post_studio/render.js`.

Replace `buildPanel` with:

```javascript
function buildPanel(b, el, theme, index, W, H, isPill) {
  const pos = b.panelPos || { x: 0, y: 0 };
  const panelW = b.panelW != null ? b.panelW : (el.panelW || 0.2);
  const panelH = b.panelH != null ? b.panelH : (el.panelH || 0.2);
  const card = document.createElement('div');
  card.setAttribute('data-ps-block', String(index));
  setStyle(card, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    width: px(panelW * W), pointerEvents: 'auto',
    display: 'flex', flexDirection: 'column', gap: '14px', alignItems: 'center',
  });
  const frame = document.createElement('div');
  frame.setAttribute('data-ps-frame', '');
  setStyle(frame, {
    position: 'relative', width: '100%', height: px(panelH * H),
    borderRadius: px(theme.card.borderRadius), overflow: 'hidden',
    border: theme.card.border, boxShadow: theme.card.boxShadow,
    background: theme.card.background,
  });
  if (b.photo) {
    const img = document.createElement('img');
    img.src = b.photo; img.alt = '';
    setStyle(img, { width: '100%', height: '100%', objectFit: 'cover', display: 'block' });
    frame.appendChild(img);
  }
  if (!isPill) {
    const badge = document.createElement('div');
    badge.textContent = String(b.badge || 0);
    setStyle(badge, {
      position: 'absolute', top: '14px', left: '14px', width: '52px', height: '52px',
      borderRadius: theme.badge.shape === 'circle' ? '50%' : '10px',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: theme.badge.background, color: theme.badge.color,
      border: theme.badge.border, fontWeight: '700', fontSize: '26px',
    });
    frame.appendChild(badge);
  }
  card.appendChild(frame);
  if (!isPill) {
    const label = document.createElement('div');
    label.textContent = b.label || '';
    setStyle(label, { ...typoStyle({ ...theme.label, ...b.labelStyle }, label.textContent), textAlign: 'center' });
    card.appendChild(label);
  }
  return card;
}
```

(Note: `theme.card.aspect` is still used by `composition.js`'s `seedLayout`/`seedBlockStyle` to DERIVE a generic theme's default `panelH` — it is simply no longer applied as a CSS `aspect-ratio` here, since a resized panel must support any width/height combination.)

Replace `buildPill` with (note the new `nextBlock` parameter):

```javascript
function buildPill(b, el, nextBlock, theme, index, W, H) {
  const pos = b.pillPos || { x: 0, y: 0 };
  const ownW = (b.panelW != null ? b.panelW : (el.panelW || 0.2)) * W;
  const isDouble = b.pill && b.pill.width === 'double';
  let pillW = ownW;
  if (isDouble && nextBlock) {
    const nextPos = nextBlock.panelPos || { x: 0, y: 0 };
    const nextW = (nextBlock.panelW != null ? nextBlock.panelW : (el.panelW || 0.2)) * W;
    pillW = (nextPos.x * W + nextW) - (pos.x * W);
  } else if (isDouble) {
    const gapPx = (el.gap || 0) * W;
    pillW = 2 * ownW + gapPx;   // no next block to measure against (shouldn't normally occur)
  }
  const pill = document.createElement('div');
  pill.setAttribute('data-ps-pill', '');
  pill.setAttribute('data-ps-pill-block', String(index));
  setStyle(pill, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    width: px(pillW), height: '56px', pointerEvents: 'auto',
    display: 'flex', alignItems: 'center', gap: '10px', padding: '0 16px',
    boxSizing: 'border-box', borderRadius: '28px', border: theme.pill.border,
  });
  const circle = document.createElement('div');
  circle.textContent = String(b.badge || 0);
  setStyle(circle, {
    flex: '0 0 auto', width: '26px', height: '26px', borderRadius: '50%',
    border: theme.pill.circleBorder, color: theme.label.color || '#F5F5F0',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: fontStack(theme.label.font, ''), fontWeight: '700', fontSize: '19px',
  });
  const text = document.createElement('div');
  text.textContent = b.label || '';
  setStyle(text, {
    ...typoStyle({ ...theme.label, ...b.labelStyle, color: theme.pill.color || theme.label.color }, b.label),
    flex: '1 1 auto', textAlign: isDouble ? 'center' : 'left',
  });
  pill.appendChild(circle);
  pill.appendChild(text);
  return pill;
}
```

Replace `buildStrip` with:

```javascript
function buildStrip(el, theme, W, H) {
  const wrap = document.createElement('div');
  setStyle(wrap, { position: 'absolute', left: '0', top: '0', width: '100%', height: '100%',
    pointerEvents: 'none' });
  const isPill = theme.label && theme.label.style === 'pill';
  const blocks = el.blocks || [];
  blocks.forEach((b, i) => {
    wrap.appendChild(buildPanel(b, el, theme, i, W, H, isPill));
    const prevDouble = blocks[i - 1] && blocks[i - 1].pill && blocks[i - 1].pill.width === 'double';
    if (isPill && !prevDouble) {
      wrap.appendChild(buildPill(b, el, blocks[i + 1], theme, i, W, H));
    }
  });
  return wrap;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_render.py -q`
Expected: PASS — the new uneven-size/double-geometry test, plus every pre-existing render test (they render through `ensureLayout`, which now stamps identical per-block values by default, so uniform-panel scenarios are numerically unchanged).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/render.js
git add static/post_studio/render.js tests/e2e/test_editor_render.py
git commit -m "feat(post-studio): render.js reads per-block size/style; double-pill reaches actual next-panel edge; auto-hides covered neighbor"
```

---

### Task 5: editor.js — resize-handle overlay + resize-drag controller

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `setSize`, `getPosition`, `setPosition` (composition.js); `EXPORT_PX` (render.js); the existing P4b-1 pointer-drag machinery (`drag`, `refsFor`, `renderPreview`, `endDrag`).
- Produces: whenever `state.selectedRef` is `'block:N'`, `renderPreview()` draws 4 corner-square handles (`data-ps-resize-handle="tl|tr|bl|br"`) on that block's rendered panel. A `pointerdown` on a handle starts a resize (instead of a move); `pointermove` resizes via `setSize` and repositions the anchor corner via `setPosition` when the dragged corner is top or left; `pointerup`/`pointercancel` commit.

- [ ] **Step 1: Write the failing tests** — append to `tests/e2e/test_editor_flow.py`

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_resize_handle_br_grows_panel_others_unaffected -q`
Expected: FAIL — `[data-ps-resize-handle='br']` never appears (no timeout-safe selector found).

- [ ] **Step 3: Implement** — edit `static/post_studio/editor.js`.

Extend the composition import (add `setSize`):

```javascript
import { TEMPLATES, MAX_BLOCKS, defaultComposition, serialize, deserialize, applyTheme,
         setText, setTypography, setBlockLabel, setBlockPhoto,
         addBlock, removeBlock, reorderBlock,
         setPosition, getPosition, nudgePosition, setSize } from './composition.js';
```

Add the resize-anchor table and `resize` state (place it next to the existing `let drag = null;` declaration):

```javascript
  // Corner -> which side(s) move. dx/dy = 1 means that axis's ANCHOR position
  // moves with the drag (so the OPPOSITE corner stays visually fixed);
  // dw/dh = the sign the delta applies to width/height.
  const RESIZE_ANCHOR = {
    br: { dx: 0, dy: 0, dw: 1, dh: 1 },
    bl: { dx: 1, dy: 0, dw: -1, dh: 1 },
    tr: { dx: 0, dy: 1, dw: 1, dh: -1 },
    tl: { dx: 1, dy: 1, dw: -1, dh: -1 },
  };
  let resize = null;
  function startResize(corner, e) {
    const i = Number(state.selectedRef.slice(6));
    const strip = state.comp.elements.find((e2) => e2.id === 'strip');
    const b = strip.blocks[i];
    const [W, H] = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    const scale = PREVIEW_W / W;
    resize = {
      index: i, corner, startX: e.clientX, startY: e.clientY, scale, W, H,
      origW: b.panelW != null ? b.panelW : (strip.panelW || 0.2),
      origH: b.panelH != null ? b.panelH : (strip.panelH || 0.2),
      origPos: b.panelPos || { x: 0, y: 0 },
    };
    previewBox.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
    rootEl.focus({ preventScroll: true });
  }
```

Change the `pointerdown` handler to check for a resize-handle hit FIRST (before the existing move-drag `refsFor` logic):

```javascript
  previewBox.addEventListener('pointerdown', (e) => {
    const handle = e.target.closest('[data-ps-resize-handle]');
    if (handle && state.selectedRef && state.selectedRef.startsWith('block:')) {
      startResize(handle.getAttribute('data-ps-resize-handle'), e);
      return;
    }
    const refs = refsFor(e.target);
    if (!refs) { selectRef(null); return; }
    selectRef(refs.sel);
    const [W, H] = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    const scale = PREVIEW_W / W;
    drag = { posRef: refs.pos, startX: e.clientX, startY: e.clientY, scale, W, H,
             orig: getPosition(state.comp, refs.pos) };
    previewBox.setPointerCapture(e.pointerId);
    e.preventDefault();
    rootEl.focus({ preventScroll: true });
  });
```

Change the `pointermove` handler to branch on `resize` FIRST:

```javascript
  previewBox.addEventListener('pointermove', (e) => {
    if (resize) {
      const a = RESIZE_ANCHOR[resize.corner];
      const dxFrac = (e.clientX - resize.startX) / resize.scale / resize.W;
      const dyFrac = (e.clientY - resize.startY) / resize.scale / resize.H;
      const w = resize.origW + a.dw * dxFrac;
      const h = resize.origH + a.dh * dyFrac;
      const nx = resize.origPos.x + a.dx * dxFrac;
      const ny = resize.origPos.y + a.dy * dyFrac;
      state.comp = setSize(state.comp, resize.index, { w, h });
      state.comp = setPosition(state.comp, 'panel:' + resize.index, { x: nx, y: ny });
      renderPreview();
      return;
    }
    if (!drag || !drag.scale) return;
    const rawX = drag.orig.x + (e.clientX - drag.startX) / drag.scale / drag.W;
    const rawY = drag.orig.y + (e.clientY - drag.startY) / drag.scale / drag.H;
    const snap = computeSnap(drag.posRef, rawX, rawY);
    state.comp = setPosition(state.comp, drag.posRef, { x: snap.x, y: snap.y });
    renderPreview();
    drawGuides(snap.lines);
  });
```

Change `endDrag` to also clear `resize`:

```javascript
  function endDrag() {
    if (drag) { drag = null; clearGuides(); renderInspector(); }
    if (resize) { resize = null; renderInspector(); }
  }
```

Finally, extend `renderPreview()`'s selection block to draw the 4 corner handles when a panel is selected. Replace:

```javascript
    if (state.selectedRef) {
      const sel = state.selectedRef.startsWith('block:')
        ? stage.querySelector(`[data-ps-block="${state.selectedRef.slice(6)}"]`)
        : stage.querySelector(`[data-ps-el="${state.selectedRef}"]`);
      if (sel) { sel.style.outline = '3px solid #38bdf8'; sel.style.outlineOffset = '4px'; }
    }
```

with:

```javascript
    if (state.selectedRef) {
      const sel = state.selectedRef.startsWith('block:')
        ? stage.querySelector(`[data-ps-block="${state.selectedRef.slice(6)}"]`)
        : stage.querySelector(`[data-ps-el="${state.selectedRef}"]`);
      if (sel) { sel.style.outline = '3px solid #38bdf8'; sel.style.outlineOffset = '4px'; }
      if (sel && state.selectedRef.startsWith('block:')) {
        const hs = 10 / scale;   // handle size in native-stage px so it looks ~10 screen-px
        for (const corner of ['tl', 'tr', 'bl', 'br']) {
          const handle = el('div', { 'data-ps-resize-handle': corner }, {
            position: 'absolute', width: `${hs}px`, height: `${hs}px`,
            background: '#38bdf8', border: '2px solid #fff', borderRadius: '2px',
            cursor: (corner === 'tl' || corner === 'br') ? 'nwse-resize' : 'nesw-resize',
            top: corner.startsWith('t') ? `${-hs / 2}px` : 'auto',
            bottom: corner.startsWith('b') ? `${-hs / 2}px` : 'auto',
            left: corner.endsWith('l') ? `${-hs / 2}px` : 'auto',
            right: corner.endsWith('r') ? `${-hs / 2}px` : 'auto',
          });
          sel.appendChild(handle);
        }
      }
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (all prior P4a/P4b-1 flow tests + the 3 new resize tests).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/editor.js
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): resize-handle overlay + resize-drag controller (4 corners, free aspect, clamped)"
```

---

### Task 6: inspector.js — "Double width" toggle + per-block label typography wiring

**Files:**
- Modify: `static/post_studio/inspector.js`
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `setPillWidth`, `setTypography(comp, 'block:N.label', patch)` (Task 3); `weightsFor` (already in inspector.js).
- Produces: `buildBlockInspector(block, opts)` — signature changes from `(block, labelStyle, opts)` to `(block, opts)` (typography now reads `block.labelStyle` directly, no separate shared-style parameter). `opts` gains `onToggleDouble`. Renders a "Double width" / "Single width" toggle button (`data-ps-action="toggle-double"`), disabled when `opts.index >= opts.count - 1`.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_double_width_toggle_hides_and_restores_next_pill -q`
Expected: FAIL — `[data-ps-action='toggle-double']` does not exist.

- [ ] **Step 3: Implement.**

In `static/post_studio/inspector.js`, replace the `buildBlockInspector` function (and its preceding comment) with:

```javascript
// block: { photo, badge, label, labelStyle, pill }
// opts: { lang, palette, index, count, maxBlocks,
//         onLabel, onLabelTypography, onLabelFont, onToggleDouble,
//         onReplace, onRemove, onMoveLeft, onMoveRight, onAdd }
export function buildBlockInspector(block, opts) {
  const ar = opts.lang === 'ar';
  const root = elt('div', { 'data-ps-inspector-block': '' },
    { display: 'flex', flexDirection: 'column', gap: '10px' });

  const label = elt('input', { type: 'text', 'data-ps-field': 'label', value: block.label || '' }, { width: '100%' });
  label.addEventListener('input', () => opts.onLabel(label.value));
  const labelWrap = elt('div');
  labelWrap.appendChild(fieldLabel(ar ? 'التسمية' : 'Label'));
  labelWrap.appendChild(label);
  root.appendChild(labelWrap);

  const ls = block.labelStyle || {};
  root.appendChild(buildTextInspector(
    { text: undefined, font: ls.font, size: ls.size, weight: ls.weight, color: ls.color },
    { lang: opts.lang, palette: opts.palette,
      onText: () => {}, onTypography: opts.onLabelTypography, onFont: opts.onLabelFont }));

  const isDouble = !!(block.pill && block.pill.width === 'double');
  const isLast = opts.index >= opts.count - 1;
  const doubleBtn = actionBtn(
    isDouble ? (ar ? 'عرض مفرد' : 'Single width') : (ar ? 'عرض مزدوج' : 'Double width'),
    'toggle-double', isLast, opts.onToggleDouble);
  root.appendChild(doubleBtn);

  const photoRow = elt('div', {}, { display: 'flex', gap: '8px' });
  photoRow.appendChild(actionBtn(ar ? 'استبدال الصورة' : 'Replace photo', 'replace', false, opts.onReplace));
  photoRow.appendChild(actionBtn(ar ? 'حذف' : 'Remove', 'remove', opts.count <= 1, opts.onRemove));
  root.appendChild(photoRow);

  const moveRow = elt('div', {}, { display: 'flex', gap: '8px' });
  moveRow.appendChild(actionBtn('◄', 'move-left', opts.index <= 0, opts.onMoveLeft));
  moveRow.appendChild(actionBtn('►', 'move-right', opts.index >= opts.count - 1, opts.onMoveRight));
  moveRow.appendChild(actionBtn(ar ? '+ كتلة' : '+ Add block', 'add-block', opts.count >= opts.maxBlocks, opts.onAdd));
  root.appendChild(moveRow);

  return root;
}
```

In `static/post_studio/editor.js`, update the composition import to add `setPillWidth`:

```javascript
import { TEMPLATES, MAX_BLOCKS, defaultComposition, serialize, deserialize, applyTheme,
         setText, setTypography, setBlockLabel, setBlockPhoto,
         addBlock, removeBlock, reorderBlock,
         setPosition, getPosition, nudgePosition, setSize, setPillWidth } from './composition.js';
```

Replace the `buildBlockInspector(...)` call inside `renderInspector()` — find:

```javascript
      inspectorSlot.appendChild(buildBlockInspector(strip.blocks[i], strip.labelStyle, {
        lang, palette: themePalette(state.comp.theme),
        index: i, count: strip.blocks.length, maxBlocks: MAX_BLOCKS,
        onLabel: (v) => { state.comp = setBlockLabel(state.comp, i, v); renderPreview(); },
        onLabelTypography: (patch) => { state.comp = setTypography(state.comp, 'strip.label', patch); renderPreview(); },
        onLabelFont: (family) => {
          const allowed = weightsFor(family);
          const w = allowed.includes(strip.labelStyle.weight) ? strip.labelStyle.weight : allowed[0];
          state.comp = setTypography(state.comp, 'strip.label', { font: family, weight: w });
          renderPreview(); renderInspector();
        },
        onReplace: async () => {
          const picked = await host.pickPhotos();
          if (picked && picked.length) { state.comp = setBlockPhoto(state.comp, i, picked[0].dataUrl); renderPreview(); renderInspector(); }
        },
        onRemove: () => { state.comp = removeBlock(state.comp, i); selectRef(null); },
        onMoveLeft: () => { state.comp = reorderBlock(state.comp, i, i - 1); selectRef('block:' + (i - 1)); },
        onMoveRight: () => { state.comp = reorderBlock(state.comp, i, i + 1); selectRef('block:' + (i + 1)); },
        onAdd: () => { state.comp = addBlock(state.comp); renderPreview(); renderInspector(); },
      }));
```

replace with:

```javascript
      inspectorSlot.appendChild(buildBlockInspector(strip.blocks[i], {
        lang, palette: themePalette(state.comp.theme),
        index: i, count: strip.blocks.length, maxBlocks: MAX_BLOCKS,
        onLabel: (v) => { state.comp = setBlockLabel(state.comp, i, v); renderPreview(); },
        onLabelTypography: (patch) => { state.comp = setTypography(state.comp, `block:${i}.label`, patch); renderPreview(); },
        onLabelFont: (family) => {
          const cur = strip.blocks[i].labelStyle || {};
          const allowed = weightsFor(family);
          const w = allowed.includes(cur.weight) ? cur.weight : allowed[0];
          state.comp = setTypography(state.comp, `block:${i}.label`, { font: family, weight: w });
          renderPreview(); renderInspector();
        },
        onToggleDouble: () => {
          const cur = strip.blocks[i].pill && strip.blocks[i].pill.width === 'double';
          state.comp = setPillWidth(state.comp, i, cur ? 'single' : 'double');
          renderPreview(); renderInspector();
        },
        onReplace: async () => {
          const picked = await host.pickPhotos();
          if (picked && picked.length) { state.comp = setBlockPhoto(state.comp, i, picked[0].dataUrl); renderPreview(); renderInspector(); }
        },
        onRemove: () => { state.comp = removeBlock(state.comp, i); selectRef(null); },
        onMoveLeft: () => { state.comp = reorderBlock(state.comp, i, i - 1); selectRef('block:' + (i - 1)); },
        onMoveRight: () => { state.comp = reorderBlock(state.comp, i, i + 1); selectRef('block:' + (i + 1)); },
        onAdd: () => { state.comp = addBlock(state.comp); renderPreview(); renderInspector(); },
      }));
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (all prior flow tests + the 2 new inspector tests).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/inspector.js
node --check static/post_studio/editor.js
git add static/post_studio/inspector.js static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): Double width pill toggle + per-block label typography wired in the inspector"
```

---

### Task 7: Phase gate — full suite + syntax checks

**Files:**
- (verification only — no source changes expected)

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: a green phase gate across `node --test`, `node --check`, and the full pytest suite, confirming P4b-2 is complete and non-regressive.

- [ ] **Step 1: Run the full JS unit suite**

Run: `node --test tests/js/`
Expected: PASS (every suite green — `composition.test.mjs`, `themes.test.mjs`, and any others).

- [ ] **Step 2: Syntax-check every touched module**

Run:
```bash
node --check static/post_studio/composition.js
node --check static/post_studio/themes.js
node --check static/post_studio/render.js
node --check static/post_studio/inspector.js
node --check static/post_studio/editor.js
```
Expected: all OK, no output.

- [ ] **Step 3: Run the full e2e editor suites**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py tests/e2e/test_editor_render.py -q`
Expected: PASS — every P4a/P4b-1/P4b-2 test green (drag, snap, nudge, resize, double-width toggle, per-block typography, export-after-resize).

- [ ] **Step 4: Run the full pytest suite**

Run: `rtk proxy python -m pytest -q`
Expected: EXIT 0 (the one pre-existing `X` xpass from earlier phases is acceptable; no `F`/`E`).

- [ ] **Step 5: Commit** (only if Step 1–4 needed any follow-up fixes; otherwise this task is verification-only and produces no diff)

```bash
git status --porcelain
```
If clean, no commit is needed — Tasks 1–6 already committed everything. If Steps 1–4 uncovered a regression and you fixed it, commit that fix with a message describing what broke and why, e.g.:

```bash
git add <fixed files>
git commit -m "fix(post-studio): <describe the regression found during the P4b-2 phase gate>"
```

---

## Self-Review

**1. Spec coverage:**
- Per-panel independent resize, moving `panelW`/`panelH` to per-block, additive legacy migration → Task 1 (`seedLayout`/`hasBlockStyle`/`seedBlockStyle`/`ensureLayout`). ✓
- `setSize` immutable/clamped → Task 2. ✓
- 4 corner handles, free aspect, opposite-corner-anchored, clamp-only (no snap) → Task 5 (`RESIZE_ANCHOR`, `startResize`, `pointermove` resize branch — explicitly bypasses `computeSnap`). ✓
- Pill single/double toggle button, disabled on the last block → Task 3 (`setPillWidth`) + Task 6 (inspector button, `isLast` disable). ✓
- Auto-hide the covered neighbor's own pill (computed, not stored) → Task 4 (`buildStrip`'s `prevDouble` check). ✓
- Double-pill width reaches the actual next-panel edge (not the old uniform formula) → Task 4 (`buildPill`'s `nextBlock` geometry). ✓
- Per-block label typography, seeded from the old shared style, no bulk-apply UI → Task 1 (seed source) + Task 3 (`block:N.label` ref) + Task 6 (inspector wiring, no "apply to all" button present). ✓
- Resize handles / selection / guides stay editor-only, never serialized → Task 5 (handles appended post-render in `editor.js`, same pattern as the pre-existing outline/guides; `exportBlob` is untouched and still re-renders a fresh stage from `state.comp`). ✓
- Non-goals (snap-while-resizing, aspect lock, freeform pill width, multi-panel span, resize on pills/title/doctor, bulk-apply) correctly absent from every task. ✓

**2. Placeholder scan:** No "TBD"/"add error handling"/bare "write tests" — every step shows complete code; exact clamp constants (`40/1080`, `0.9`) and the resize-anchor table appear in Tasks 2 and 5.

**3. Type consistency:** `setSize(comp, index, {w,h})` (Task 2) is called identically in `editor.js`'s resize `pointermove` (Task 5). `setPillWidth(comp, index, width)` (Task 3) matches its call site in Task 6's `onToggleDouble`. `'block:N.label'` ref string is produced identically in Task 6 (`` `block:${i}.label` ``) and consumed identically in Task 3's `typoTarget` regex (`/^block:(\d+)\.label$/`). `buildBlockInspector(block, opts)`'s new 2-arg signature (Task 6) matches its call site (Task 6, same task — both sides updated together). Field names `panelW`/`panelH`/`labelStyle` are used identically across Tasks 1, 2, 4, and 6. `data-ps-resize-handle` attribute values (`tl`/`tr`/`bl`/`br`) match between the handle-drawing code and `RESIZE_ANCHOR`'s keys (Task 5) and the e2e test selectors (Task 5's tests).
