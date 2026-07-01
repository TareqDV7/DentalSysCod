# Post Studio — P4b-1 Layout & Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-layout renderer with a free-positioning canvas — every element (title, doctor, each panel, each pill) placeable by pointer drag with smart guides + keyboard nudge — and bake the navy_gold flagship's exact geometry into `dark_premium` layout tokens so a dark_premium post lays out on the go.png grid.

**Architecture:** An absolute fractional coordinate model (`pos:{x,y}` 0–1) seeded deterministically from per-theme **layout tokens** in `themes.js`. `composition.js` gains `seedLayout`/`ensureLayout` (idempotent) and immutable `setPosition`/`nudgePosition`. `render.js` becomes a single absolute-placement path (no flex/center) that calls `ensureLayout` defensively so any comp renders. `editor.js` adds a pointer-drag controller, a snap/guide overlay, and a nudge key handler layered on the P4a selection/inspector. Selection, outline, and guides stay editor-only; positions are serialized.

**Tech Stack:** Pure-ESM JS modules under `static/post_studio/` (no bundler, no new runtime deps); `node --test` (DOM-free unit); Playwright (`--allow-file-access-from-files`) over `static/post_studio/spike/{editor,render}_harness.html`; pytest harness.

## Global Constraints

- **No new runtime dependencies.** No npm/pip additions.
- **`render.js` stays INLINE STYLES ONLY.** New position/size are inline `left`/`top`/`width`/`transform`; `data-ps-pill-block` is a bare `data-*` attribute (no className, no style, no external ref). Export safety (untainted foreignObject→canvas PNG) and the `@font-face`-embedded-in-export invariant are preserved; do NOT touch `rasterize.js`.
- **Selection, outline, and snap guides are editor-only and NEVER serialized.** `state.selectedRef`, the outline, and guide lines live in `editor.js`; `exportBlob()` re-renders a fresh, chrome-free stage via `renderComposition`.
- **Positions ARE serialized** into `template_json` (`pos`, `strip.panelW/panelH/gap`, per-block `panelPos/pillPos/pill.width`).
- **Immutability:** every `composition.js` helper returns a NEW composition via `structuredClone` and never mutates its input.
- **Coordinate model:** `pos:{x,y}` fractional 0–1; `x` of canvas width, `y` of canvas height. Anchor = **center** for text elements (title, doctor), **top-left** for box elements (panel, pill). Positions clamp to `[0,1]`.
- **Fidelity = grid-as-theme-tokens (user decision).** Exact go.png geometry lives in `dark_premium` layout tokens; literal go.png = 4-panel template + dark_premium + a pill set to `double`. The pill-width editing UI, resize handles, and per-block label typography are **P4b-2** (out of scope here). The `pill.width='double'` DATA + render ARE in this slice (no toggle UI yet).
- **Exact `dark_premium` layout tokens (px/1080):** margin `16/1080`, gap `16/1080`, `panelW=250/1080`, `panelH=320/1080`, `panelRowY=360/1080`, `pillRowY=708/1080`, `titleY=172/1080`, `doctorY=920/1080`. Pill height is a fixed `56px`; single pill width = `panelW`, double = `2·panelW + gap`.
- **Generic (default) layout tokens:** margin `0.06`, gap `0.03`, `panelW=null` (derive to fill row), `panelH=null` (derive from theme card aspect), `panelRowY=null` (center), `pillRowY=null` (below panel), `titleY=0.10`, `doctorY=0.93`. Single row for all panel counts (the former 2-col grid auto-layout is retired — rearrange by drag).
- **PR HELD.** Stack P4b-1 on `feat/post-studio`; do NOT open a PR or push to origin unprompted. Git commit attribution disabled (no Co-Authored-By).

**Base commit:** `c8a13a4` (P4a HEAD).
**Spec:** `docs/superpowers/specs/2026-07-01-post-studio-p4b1-layout-fidelity.md`

---

### Task 1: Layout tokens in themes.js

**Files:**
- Modify: `static/post_studio/themes.js`
- Test: `tests/js/themes.test.mjs`

**Interfaces:**
- Consumes: existing `THEMES`, `themeTokens`.
- Produces: `themeLayout(name) -> { margin, gap, panelW, panelH, panelRowY, pillRowY, titleY, doctorY }` — merges a per-theme `layout` override onto `DEFAULT_LAYOUT`; unknown name falls back to `dark_premium`'s merged layout. Any token may be `null` (meaning "derive in seedLayout").

- [ ] **Step 1: Write the failing test** — append to `tests/js/themes.test.mjs`

```javascript
import { themeLayout } from '../../static/post_studio/themes.js';

test('themeLayout returns the exact dark_premium go.png grid tokens', () => {
  const L = themeLayout('dark_premium');
  assert.equal(L.panelW, 250 / 1080);
  assert.equal(L.panelH, 320 / 1080);
  assert.equal(L.panelRowY, 360 / 1080);
  assert.equal(L.pillRowY, 708 / 1080);
  assert.equal(L.doctorY, 920 / 1080);
  assert.equal(L.margin, 16 / 1080);
  assert.equal(L.gap, 16 / 1080);
});

test('themeLayout gives a generic theme the derive-mode defaults', () => {
  const L = themeLayout('light_luxury');
  assert.equal(L.panelW, null);      // derive to fill the row
  assert.equal(L.panelH, null);
  assert.equal(L.panelRowY, null);   // center vertically
  assert.equal(L.margin, 0.06);
  assert.equal(L.doctorY, 0.93);
});

test('themeLayout falls back to dark_premium for unknown names', () => {
  assert.deepEqual(themeLayout('nope'), themeLayout('dark_premium'));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/themes.test.mjs`
Expected: FAIL — `themeLayout` is not exported.

- [ ] **Step 3: Implement** — in `static/post_studio/themes.js`, add a `layout` key to the `dark_premium` theme object (right after its `accent` line, inside the object), then append the exports at the end of the file.

Add inside the `dark_premium` object (after `accent: '#C6A274',`):
```javascript
    layout: {
      margin: 16 / 1080, gap: 16 / 1080,
      panelW: 250 / 1080, panelH: 320 / 1080,
      panelRowY: 360 / 1080, pillRowY: 708 / 1080,
      titleY: 172 / 1080, doctorY: 920 / 1080,
    },
```

Append at the end of the file:
```javascript
// Layout tokens drive seedLayout (composition.js). A theme may override any key;
// null means "derive in seedLayout" (panelW→fill row, panelH→from card aspect,
// panelRowY→center, pillRowY→below panel).
export const DEFAULT_LAYOUT = {
  margin: 0.06, gap: 0.03,
  panelW: null, panelH: null,
  panelRowY: null, pillRowY: null,
  titleY: 0.10, doctorY: 0.93,
};

export function themeLayout(name) {
  const t = THEMES[name] || THEMES.dark_premium;
  return { ...DEFAULT_LAYOUT, ...(t.layout || {}) };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/themes.test.mjs`
Expected: PASS.

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/themes.js
git add static/post_studio/themes.js tests/js/themes.test.mjs
git commit -m "feat(post-studio): per-theme layout tokens (dark_premium = exact go.png grid)"
```

---

### Task 2: seedLayout + coordinate model in composition.js

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `themeTokens`, `themeLayout` (themes.js); `structuredClone`.
- Produces:
  - `CANVAS_DIMS = { square:[1080,1080], portrait:[1080,1350], story:[1080,1920] }`.
  - `seedLayout(comp) -> comp` — returns a NEW comp with every positionable element's coordinates (re)computed from the active theme's layout tokens: `title.pos`, `doctor.pos` (center anchor `{x:0.5,y}`); `strip.panelW`, `strip.panelH`, `strip.gap`; each `blocks[i].panelPos`, `blocks[i].pillPos` (top-left), and `blocks[i].pill = {width}` (preserving an existing `'double'`). Single row for all counts, centered.
  - `hasLayout(comp) -> boolean` — true if the title element already has a `pos`.
  - `ensureLayout(comp) -> comp` — `seedLayout` only when `!hasLayout` (idempotent; preserves saved/dragged positions).
  - `applyTheme` now re-seeds layout (theme switch resets to that theme's grid — consistent with the existing typography reset); `deserialize` seeds legacy posts.

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import {
  seedLayout, ensureLayout, hasLayout, CANVAS_DIMS,
} from '../../static/post_studio/composition.js';

test('defaultComposition seeds positions for every element', () => {
  const c = defaultComposition('before_after');   // dark_premium default
  const title = c.elements.find((e) => e.id === 'title');
  const strip = c.elements.find((e) => e.id === 'strip');
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.ok(title.pos && strip.blocks[0].panelPos && strip.blocks[0].pillPos && doctor.pos);
  assert.equal(hasLayout(c), true);
});

test('dark_premium seeds the exact go.png grid', () => {
  // 4-panel dark_premium comp (quad_grid) -> the go.png panel row + pills
  const c = defaultComposition('quad_grid');
  const strip = c.elements.find((e) => e.id === 'strip');
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.equal(strip.panelW, 250 / 1080);
  assert.equal(strip.panelH, 320 / 1080);
  assert.equal(strip.blocks[0].panelPos.y, 360 / 1080);
  assert.equal(strip.blocks[0].panelPos.x, 16 / 1080);           // centered row: 4*250+3*16=1048 -> start 16
  assert.equal(strip.blocks[1].panelPos.x, (16 + 266) / 1080);   // panelW+gap = 266
  assert.equal(strip.blocks[0].pillPos.y, 708 / 1080);
  assert.equal(doctor.pos.y, 920 / 1080);
});

test('a generic theme derives a centered, row-filling layout', () => {
  const c = applyTheme(defaultComposition('before_after'), 'light_luxury');
  const strip = c.elements.find((e) => e.id === 'strip');
  // 2 panels, margin .06, gap .03 -> panelW = (1 - .12 - .03)/2 = .425
  assert.ok(Math.abs(strip.panelW - 0.425) < 1e-9);
  assert.ok(strip.blocks[0].panelPos.y > 0 && strip.blocks[0].panelPos.y < 0.5);  // centered
});

test('seedLayout is deterministic and preserves a double pill', () => {
  let c = defaultComposition('before_after');
  c = structuredClone(c);
  c.elements.find((e) => e.id === 'strip').blocks[0].pill = { width: 'double' };
  const s1 = seedLayout(c);
  const s2 = seedLayout(s1);
  assert.deepEqual(s1, s2);                                          // idempotent shape
  assert.equal(s1.elements.find((e) => e.id === 'strip').blocks[0].pill.width, 'double');
});

test('ensureLayout only seeds when positions are absent', () => {
  const raw = { version: 1, size: 'square', theme: 'dark_premium', elements: [
    { id: 'title', type: 'title', headline: { text: 'X' }, subline: { text: 'Y' } },
    { id: 'strip', type: 'photoStrip', blocks: [{ photo: null, badge: 1, label: 'A' }] },
    { id: 'doctor', type: 'doctorName', text: 'DR. Z' },
  ] };
  assert.equal(hasLayout(raw), false);
  const seeded = ensureLayout(raw);
  assert.equal(hasLayout(seeded), true);
  assert.equal(ensureLayout(seeded), seeded);                        // no re-seed (same reference)
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `seedLayout`/`ensureLayout`/`hasLayout`/`CANVAS_DIMS` not exported; `defaultComposition` output has no `pos`.

- [ ] **Step 3: Implement** — edit `static/post_studio/composition.js`.

Change the themes import to add `themeLayout`:
```javascript
import { themeTokens, themeLayout } from './themes.js';
```

Append after the existing `renumber` export (or anywhere at module top-level below the imports) the canvas dims + layout engine:
```javascript
// Canvas pixel dims per size (mirrors render.EXPORT_PX; kept here so the DOM-free
// layout engine has no dependency on render.js).
export const CANVAS_DIMS = { square: [1080, 1080], portrait: [1080, 1350], story: [1080, 1920] };

function parseAspect(card) {
  // card.aspect like '250 / 320' (W / H); default square 1:1.
  if (!card || !card.aspect) return { w: 1, h: 1 };
  const parts = String(card.aspect).split('/').map((s) => parseFloat(s.trim()));
  if (parts.length === 2 && parts[0] > 0 && parts[1] > 0) return { w: parts[0], h: parts[1] };
  return { w: 1, h: 1 };
}

// Returns a NEW comp with every positionable element's coordinates recomputed
// from the active theme's layout tokens. Single centered row for all panel counts.
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
    const startX = (1 - rowW) / 2;
    const panelY = L.panelRowY != null ? L.panelRowY : 0.5 - panelH / 2;
    const pillY = L.pillRowY != null ? L.pillRowY : panelY + panelH + L.gap;
    strip.panelW = panelW;
    strip.panelH = panelH;
    strip.gap = L.gap;
    strip.blocks = strip.blocks.map((b, i) => ({
      ...b,
      panelPos: { x: startX + i * (panelW + L.gap), y: panelY },
      pillPos: { x: startX + i * (panelW + L.gap), y: pillY },
      pill: { width: (b.pill && b.pill.width) || 'single' },
    }));
  }
  return next;
}

export function hasLayout(comp) {
  const title = (comp.elements || []).find((e) => e.id === 'title');
  return !!(title && title.pos);
}

export function ensureLayout(comp) {
  return hasLayout(comp) ? comp : seedLayout(comp);
}
```

In `applyTheme`, seed the layout after stamping typography — change its final `return next;` to:
```javascript
  return seedLayout(next);
```

In `deserialize`, seed legacy posts — change its final `return structuredClone(c);` to:
```javascript
  return ensureLayout(structuredClone(c));
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS (new + existing composition tests green).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/composition.js
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): seedLayout coordinate model (per-theme tokens, exact go.png grid)"
```

---

### Task 3: setPosition / nudgePosition helpers

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `CANVAS_DIMS`, `structuredClone`.
- Produces:
  - `getPosition(comp, ref) -> {x,y}` — `ref ∈ {'title','doctor','panel:N','pill:N'}`; reads `pos`/`panelPos`/`pillPos`; missing → `{x:0,y:0}`.
  - `setPosition(comp, ref, {x,y}) -> comp` — immutable; writes the ref's position field, clamping each axis to `[0,1]`. Throws on a bad ref.
  - `nudgePosition(comp, ref, dxPx, dyPx, canvas) -> comp` — `canvas = [W,H]`; adds a pixel delta as a fraction, then `setPosition` (clamped).

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import { getPosition, setPosition, nudgePosition } from '../../static/post_studio/composition.js';

test('setPosition writes each ref field immutably and clamps to [0,1]', () => {
  const c = defaultComposition('before_after');
  const t = setPosition(c, 'title', { x: 0.4, y: 0.2 });
  assert.deepEqual(t.elements.find((e) => e.id === 'title').pos, { x: 0.4, y: 0.2 });
  assert.notDeepEqual(c.elements.find((e) => e.id === 'title').pos, { x: 0.4, y: 0.2 }); // input intact
  const p = setPosition(c, 'panel:1', { x: 1.5, y: -0.3 });                              // clamps
  assert.deepEqual(p.elements.find((e) => e.id === 'strip').blocks[1].panelPos, { x: 1, y: 0 });
  const q = setPosition(c, 'pill:0', { x: 0.1, y: 0.7 });
  assert.deepEqual(q.elements.find((e) => e.id === 'strip').blocks[0].pillPos, { x: 0.1, y: 0.7 });
  assert.throws(() => setPosition(c, 'nope:9', { x: 0, y: 0 }));
});

test('nudgePosition adds a pixel delta as a canvas fraction', () => {
  const c = setPosition(defaultComposition('before_after'), 'doctor', { x: 0.5, y: 0.5 });
  const n = nudgePosition(c, 'doctor', 10, -20, [1080, 1080]);
  const pos = n.elements.find((e) => e.id === 'doctor').pos;
  assert.ok(Math.abs(pos.x - (0.5 + 10 / 1080)) < 1e-9);
  assert.ok(Math.abs(pos.y - (0.5 - 20 / 1080)) < 1e-9);
});

test('getPosition reads the correct field per ref', () => {
  const c = defaultComposition('before_after');
  assert.deepEqual(getPosition(c, 'panel:0'),
    c.elements.find((e) => e.id === 'strip').blocks[0].panelPos);
  assert.deepEqual(getPosition(c, 'title'), c.elements.find((e) => e.id === 'title').pos);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `getPosition`/`setPosition`/`nudgePosition` not exported.

- [ ] **Step 3: Implement** — append to `static/post_studio/composition.js`

```javascript
const clamp01 = (n) => Math.max(0, Math.min(1, Number(n)));

// A positionable target + which field holds its coordinates.
function posField(ref) {
  if (ref.startsWith('panel:')) return 'panelPos';
  if (ref.startsWith('pill:')) return 'pillPos';
  return 'pos';
}
function posTarget(comp, ref) {
  if (ref === 'title') return comp.elements.find((e) => e.id === 'title');
  if (ref === 'doctor') return comp.elements.find((e) => e.id === 'doctor');
  if (ref.startsWith('panel:') || ref.startsWith('pill:')) {
    const strip = comp.elements.find((e) => e.id === 'strip');
    const i = Number(ref.slice(ref.indexOf(':') + 1));
    return strip && strip.blocks[i];
  }
  return null;
}

export function getPosition(comp, ref) {
  const t = posTarget(comp, ref);
  if (!t) return { x: 0, y: 0 };
  return t[posField(ref)] || { x: 0, y: 0 };
}

export function setPosition(comp, ref, xy) {
  const next = structuredClone(comp);
  const t = posTarget(next, ref);
  if (!t) throw new Error(`bad pos ref: ${ref}`);
  t[posField(ref)] = { x: clamp01(xy.x), y: clamp01(xy.y) };
  return next;
}

export function nudgePosition(comp, ref, dxPx, dyPx, canvas) {
  const [W, H] = canvas || CANVAS_DIMS.square;
  const cur = getPosition(comp, ref);
  return setPosition(comp, ref, { x: cur.x + dxPx / W, y: cur.y + dyPx / H });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS.

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/composition.js
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): immutable setPosition/nudgePosition/getPosition (clamped)"
```

---

### Task 4: render.js absolute placement + pill.width + hooks + harness probes

**Files:**
- Modify: `static/post_studio/render.js`
- Modify: `static/post_studio/spike/render_harness.html`
- Test: `tests/e2e/test_editor_render.py`

**Interfaces:**
- Consumes: `ensureLayout` (composition.js); `pos`/`panelPos`/`pillPos`/`panelW`/`panelH`/`gap`/`pill.width` from Task 2; existing `typoStyle`/`buildDivider`/`buildWaveFooter`/`fontStack`.
- Produces (rendered DOM contract): title/doctor placed by their `pos` (center anchor); each panel `data-ps-block="<i>"` placed by `panelPos` with width `panelW`; each pill (pill themes) `data-ps-pill` + `data-ps-pill-block="<i>"` placed by `pillPos`, width single=`panelW` / double=`2·panelW+gap`, double text centered. Non-pill themes keep the label inside the panel (glued). Harness `__describe` gains `rects` (panels/pills/doctor bounding boxes relative to the stage) + `pillWidths`.

- [ ] **Step 1: Add render-side probes to the harness** — in `static/post_studio/spike/render_harness.html`, inside `window.__describe`'s returned object (next to `hasDoctor`), add:

```javascript
      rects: (() => {
        const s = stage.getBoundingClientRect();
        const r = (n) => { if (!n) return null; const b = n.getBoundingClientRect();
          return { left: Math.round(b.left - s.left), top: Math.round(b.top - s.top),
                   w: Math.round(b.width), h: Math.round(b.height) }; };
        return {
          panels: Array.from(stage.querySelectorAll('[data-ps-block]')).map(r),
          pills: Array.from(stage.querySelectorAll('[data-ps-pill-block]')).map(r),
          doctor: r(stage.querySelector('[data-ps-el="doctor"]')),
        };
      })(),
      pillWidths: Array.from(stage.querySelectorAll('[data-ps-pill]')).map((p) => Math.round(p.getBoundingClientRect().width)),
```

- [ ] **Step 2: Write the failing tests** — append to `tests/e2e/test_editor_render.py`

```python
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
```

(`_goto_ready`, `HARNESS`, `_LAUNCH_ARGS`, `sync_playwright` already exist at the top of this file.)

- [ ] **Step 3: Rewrite the placement in `static/post_studio/render.js`.**

Add the import at the top (next to the themes import):
```javascript
import { themeTokens } from './themes.js';
import { ensureLayout } from './composition.js';
```

Replace `buildTitle` with a center-anchored, position-driven version:
```javascript
function buildTitle(el, theme, W, H) {
  const pos = el.pos || { x: 0.5, y: 0.1 };
  const box = document.createElement('div');
  setStyle(box, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    transform: 'translate(-50%, -50%)', maxWidth: px(0.88 * W),
    textAlign: el.align || 'center', boxSizing: 'border-box',
  });
  const head = document.createElement('div');
  head.setAttribute('data-ps-headline', '');
  head.setAttribute('data-ps-el', 'title.headline');
  head.textContent = el.headline ? (el.headline.text || '') : '';
  setStyle(head, typoStyle({ ...theme.headline, ...el.headline }, head.textContent));
  const sub = document.createElement('div');
  sub.setAttribute('data-ps-el', 'title.subline');
  sub.textContent = el.subline ? (el.subline.text || '') : '';
  setStyle(sub, typoStyle({ ...theme.subline, ...el.subline }, sub.textContent));
  box.appendChild(head);
  box.appendChild(sub);
  if (theme.divider && theme.divider.enabled) box.appendChild(buildDivider(theme));
  return box;
}
```

Replace `buildDoctor` with a center-anchored version:
```javascript
function buildDoctor(el, theme, W, H) {
  const t = { ...theme.doctor, ...el };
  const pos = el.pos || { x: 0.5, y: 0.93 };
  const box = document.createElement('div');
  box.setAttribute('data-ps-el', 'doctor');
  box.textContent = el.text || '';
  setStyle(box, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    transform: 'translate(-50%, -50%)', textAlign: el.align || 'center',
    textTransform: 'uppercase',
    fontFamily: fontStack(t.font, box.textContent),
    color: t.color || '#c9a86a',
    fontSize: px(t.size || 34),
    fontWeight: String(t.weight || 700),
    letterSpacing: px(t.letterSpacing || 4),
  });
  return box;
}
```

Replace `buildStrip`, `buildCard`, and `buildPill` with absolute-placement `buildStrip`, `buildPanel`, `buildPill`:
```javascript
function buildStrip(el, theme, W, H) {
  const wrap = document.createElement('div');
  setStyle(wrap, { position: 'absolute', left: '0', top: '0', width: '100%', height: '100%' });
  const isPill = theme.label && theme.label.style === 'pill';
  (el.blocks || []).forEach((b, i) => {
    wrap.appendChild(buildPanel(b, el, theme, i, W, H, isPill));
    if (isPill) wrap.appendChild(buildPill(b, el, theme, i, W, H));
  });
  return wrap;
}

function buildPanel(b, el, theme, index, W, H, isPill) {
  const pos = b.panelPos || { x: 0, y: 0 };
  const card = document.createElement('div');
  card.setAttribute('data-ps-block', String(index));
  setStyle(card, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    width: px((el.panelW || 0.2) * W),
    display: 'flex', flexDirection: 'column', gap: '14px', alignItems: 'center',
  });
  const frame = document.createElement('div');
  frame.setAttribute('data-ps-frame', '');
  setStyle(frame, {
    position: 'relative', width: '100%', aspectRatio: theme.card.aspect || '1 / 1',
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
    setStyle(label, { ...typoStyle({ ...theme.label, ...el.labelStyle }, label.textContent), textAlign: 'center' });
    card.appendChild(label);
  }
  return card;
}

function buildPill(b, el, theme, index, W, H) {
  const pos = b.pillPos || { x: 0, y: 0 };
  const single = (el.panelW || 0.2) * W;
  const gapPx = (el.gap || 0) * W;
  const isDouble = b.pill && b.pill.width === 'double';
  const pillW = isDouble ? 2 * single + gapPx : single;
  const pill = document.createElement('div');
  pill.setAttribute('data-ps-pill', '');
  pill.setAttribute('data-ps-pill-block', String(index));
  setStyle(pill, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    width: px(pillW), height: '56px',
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
    ...typoStyle({ ...theme.label, ...el.labelStyle, color: theme.pill.color || theme.label.color }, b.label),
    flex: '1 1 auto', textAlign: isDouble ? 'center' : 'left',
  });
  pill.appendChild(circle);
  pill.appendChild(text);
  return pill;
}
```

Update `renderComposition` to seed defensively and pass `W,H` to the builders:
```javascript
export function renderComposition(comp) {
  comp = ensureLayout(comp);
  const [w, h] = EXPORT_PX[comp.size] || EXPORT_PX.square;
  const theme = themeTokens(comp.theme);
  const stage = document.createElement('div');
  stage.setAttribute('data-ps-stage', '');
  setStyle(stage, {
    position: 'relative', width: px(w), height: px(h), overflow: 'hidden',
    background: theme.bg,
    fontFamily: 'system-ui, "Segoe UI", sans-serif',
  });
  for (const el of (comp.elements || [])) {
    if (el.type === 'title') stage.appendChild(buildTitle(el, theme, w, h));
    else if (el.type === 'photoStrip') stage.appendChild(buildStrip(el, theme, w, h));
    else if (el.type === 'doctorName') stage.appendChild(buildDoctor(el, theme, w, h));
  }
  if (theme.waveFooter && theme.waveFooter.enabled) stage.appendChild(buildWaveFooter(theme));
  return stage;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_render.py -q`
Expected: PASS — the new grid test plus all pre-existing render tests (they now render through `ensureLayout`; structure/aspect/pills/hooks are unchanged).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/render.js
git add static/post_studio/render.js static/post_studio/spike/render_harness.html tests/e2e/test_editor_render.py
git commit -m "feat(post-studio): absolute-placement renderer (pos-driven) + variable-width pills + data-ps-pill-block"
```

---

### Task 5: editor.js pointer-drag controller

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `EXPORT_PX` (render.js); `setPosition`, `getPosition` (composition.js); render hooks (Task 4); P4a `selectRef`/`renderPreview`/`renderInspector`.
- Produces: pointer-down on an element selects it (P4a inspector ref) and begins a move; pointer-move updates the element's position via `setPosition`; pointer-up commits. Position ref vs selection ref: title.headline/title.subline→`title`; doctor→`doctor`; panel `data-ps-block=N`→`panel:N` (selects `block:N`); pill `data-ps-pill-block=N`→`pill:N` (selects `block:N`).

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_drag_moves_an_element_and_updates_pos -q`
Expected: FAIL — clicking currently selects but does not drag; the element does not move.

- [ ] **Step 3: Implement** — edit `static/post_studio/editor.js`.

Extend the composition import to add the position helpers:
```javascript
import { TEMPLATES, MAX_BLOCKS, defaultComposition, serialize, deserialize, applyTheme,
         setText, setTypography, setBlockLabel, setBlockPhoto,
         addBlock, removeBlock, reorderBlock,
         setPosition, getPosition } from './composition.js';
```

Replace the existing P4a `previewBox.addEventListener('click', ...)` selection handler with a pointer-drag controller (map a hit node to its selection ref and position ref, select on down, move on drag, commit on up):
```javascript
  // Map a hit element to { selRef (inspector), posRef (drag target) }.
  function refsFor(node) {
    const elNode = node.closest('[data-ps-el]');
    if (elNode) {
      const v = elNode.getAttribute('data-ps-el');       // title.headline | title.subline | doctor
      return { sel: v, pos: v === 'doctor' ? 'doctor' : 'title' };
    }
    const pillNode = node.closest('[data-ps-pill-block]');
    if (pillNode) {
      const i = pillNode.getAttribute('data-ps-pill-block');
      return { sel: 'block:' + i, pos: 'pill:' + i };
    }
    const blockNode = node.closest('[data-ps-block]');
    if (blockNode) {
      const i = blockNode.getAttribute('data-ps-block');
      return { sel: 'block:' + i, pos: 'panel:' + i };
    }
    return null;
  }

  let drag = null;
  previewBox.addEventListener('pointerdown', (e) => {
    const refs = refsFor(e.target);
    if (!refs) { selectRef(null); return; }
    selectRef(refs.sel);
    const [W, H] = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    const scale = PREVIEW_W / W;
    drag = { posRef: refs.pos, startX: e.clientX, startY: e.clientY, scale, W, H,
             orig: getPosition(state.comp, refs.pos) };
    previewBox.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  previewBox.addEventListener('pointermove', (e) => {
    if (!drag || !drag.scale) return;
    const nx = drag.orig.x + (e.clientX - drag.startX) / drag.scale / drag.W;
    const ny = drag.orig.y + (e.clientY - drag.startY) / drag.scale / drag.H;
    state.comp = setPosition(state.comp, drag.posRef, { x: nx, y: ny });
    renderPreview();
  });
  function endDrag() { if (drag) { drag = null; renderInspector(); } }
  previewBox.addEventListener('pointerup', endDrag);
  previewBox.addEventListener('pointercancel', endDrag);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (all P4a flow tests + the new drag test).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/editor.js
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): pointer-drag controller — move any element, updates pos"
```

---

### Task 6: Smart alignment guides + snap

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: the Task 5 drag controller; `themeLayout` (themes.js) for the margin token.
- Produces: during a drag, the moving element's anchor snaps to canvas center-x/center-y, the safe margins, and other positionable elements' anchor x/y (threshold ~6 display-px → fractional); a guide line (a thin `data-ps-guide` div, editor-only) is drawn on the stage per active snap and cleared on drag end. A `computeSnap(posRef, nx, ny)` helper returns `{x, y, lines}`.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_drag_snaps_to_canvas_center_and_shows_guide -q`
Expected: FAIL — no snapping, no `[data-ps-guide]`.

- [ ] **Step 3: Implement** — edit `static/post_studio/editor.js`.

Add `themeLayout` to the themes import:
```javascript
import { THEME_OPTIONS, themePalette, themeLayout } from './themes.js';
```

Add the snap engine + guide overlay (place above the `pointerdown` handler from Task 5):
```javascript
  const SNAP_PX = 6;   // display-px threshold

  // Fractional snap targets on each axis: canvas centre + margins + every OTHER
  // positionable element's anchor. `exceptPos` is the dragged element's ref.
  function snapTargets(exceptPos) {
    const m = themeLayout(state.comp.theme).margin;
    const xs = [0.5, m, 1 - m];
    const ys = [0.5, m, 1 - m];
    const title = state.comp.elements.find((e) => e.id === 'title');
    const doctor = state.comp.elements.find((e) => e.id === 'doctor');
    const strip = state.comp.elements.find((e) => e.id === 'strip');
    const add = (ref, pt) => { if (ref !== exceptPos && pt) { xs.push(pt.x); ys.push(pt.y); } };
    add('title', title && title.pos);
    add('doctor', doctor && doctor.pos);
    (strip ? strip.blocks : []).forEach((b, i) => {
      add('panel:' + i, b.panelPos); add('pill:' + i, b.pillPos);
    });
    return { xs, ys };
  }

  function computeSnap(posRef, nx, ny) {
    const [W] = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    const thresh = SNAP_PX / (PREVIEW_W / W) / W;   // display-px -> fractional-of-width
    const T = snapTargets(posRef);
    let sx = nx, sy = ny; const lines = [];
    for (const t of T.xs) if (Math.abs(nx - t) < thresh) { sx = t; lines.push({ axis: 'x', at: t }); break; }
    for (const t of T.ys) if (Math.abs(ny - t) < thresh) { sy = t; lines.push({ axis: 'y', at: t }); break; }
    return { x: sx, y: sy, lines };
  }

  function drawGuides(lines) {
    const stage = previewBox._stage;
    if (!stage) return;
    stage.querySelectorAll('[data-ps-guide]').forEach((n) => n.remove());
    for (const ln of lines) {
      const g = el('div', { 'data-ps-guide': '' }, {
        position: 'absolute', background: '#38bdf8', pointerEvents: 'none', zIndex: '99',
        ...(ln.axis === 'x'
          ? { left: (ln.at * 100) + '%', top: '0', width: '2px', height: '100%' }
          : { top: (ln.at * 100) + '%', left: '0', height: '2px', width: '100%' }),
      });
      stage.appendChild(g);
    }
  }
  function clearGuides() {
    const stage = previewBox._stage;
    if (stage) stage.querySelectorAll('[data-ps-guide]').forEach((n) => n.remove());
  }
```

Change the Task 5 `pointermove` handler to run the snap + draw guides:
```javascript
  previewBox.addEventListener('pointermove', (e) => {
    if (!drag || !drag.scale) return;
    const rawX = drag.orig.x + (e.clientX - drag.startX) / drag.scale / drag.W;
    const rawY = drag.orig.y + (e.clientY - drag.startY) / drag.scale / drag.H;
    const snap = computeSnap(drag.posRef, rawX, rawY);
    state.comp = setPosition(state.comp, drag.posRef, { x: snap.x, y: snap.y });
    renderPreview();
    drawGuides(snap.lines);
  });
```

Change `endDrag` (Task 5) to clear guides:
```javascript
  function endDrag() { if (drag) { drag = null; clearGuides(); renderInspector(); } }
```

Note: `renderPreview()` rebuilds the stage each move, so guides (appended to the fresh stage after render) are naturally transient; `clearGuides` covers the drop frame where no further render occurs.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (flow tests + the new snap test).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/editor.js
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): smart alignment guides + snap (canvas centre/margins/other elements)"
```

---

### Task 7: Keyboard nudge

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `nudgePosition` (composition.js); `EXPORT_PX`; `state.selectedRef`.
- Produces: with an element selected, ArrowLeft/Right/Up/Down nudge it 1 canvas-px, Shift+Arrow 10 canvas-px; the selection ref maps to a position ref (`title.*`→`title`, `doctor`→`doctor`, `block:N`→`panel:N`). Handler is bound once on `rootEl` (tabindex) so keys are captured without stealing focus from inputs.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_arrow_keys_nudge_selected_element -q`
Expected: FAIL — arrow keys do nothing.

- [ ] **Step 3: Implement** — edit `static/post_studio/editor.js`.

Add `nudgePosition` to the composition import (extend the Task 5 import list):
```javascript
         setPosition, getPosition, nudgePosition } from './composition.js';
```

Map a selection ref to a position ref and bind the key handler. Add a helper + listener (place near the drag controller):
```javascript
  function posRefOf(selRef) {
    if (!selRef) return null;
    if (selRef.startsWith('title')) return 'title';
    if (selRef === 'doctor') return 'doctor';
    if (selRef.startsWith('block:')) return 'panel:' + selRef.slice(6);
    return null;
  }

  const NUDGE = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  rootEl.setAttribute('tabindex', '0');
  rootEl.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;  // don't hijack fields
    const delta = NUDGE[e.key];
    const posRef = posRefOf(state.selectedRef);
    if (!delta || !posRef) return;
    e.preventDefault();
    const step = e.shiftKey ? 10 : 1;
    const canvas = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    state.comp = nudgePosition(state.comp, posRef, delta[0] * step, delta[1] * step, canvas);
    renderPreview();
  });
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (flow tests + the nudge test).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/editor.js
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): keyboard nudge for the selected element (1px / Shift 10px)"
```

---

### Task 8: Legacy-seed + export-after-drag regression + phase gate

**Files:**
- Test: `tests/js/composition.test.mjs`
- Test: `tests/e2e/test_editor_flow.py`
- (verification only — no source changes expected)

**Interfaces:**
- Consumes: everything above; the fake host's `__lastPng`/`__savedCount` flags in `editor_harness.html`.
- Produces: a unit test proving `deserialize` seeds a legacy (no-`pos`) post; an e2e regression proving export after a drag is still a non-empty (untainted) PNG; a green phase gate across `node --test`, `node --check`, and the full pytest suite.

- [ ] **Step 1: Write the legacy-seed unit test** — append to `tests/js/composition.test.mjs`

```javascript
test('deserialize seeds a legacy post that has no positions', () => {
  const legacy = JSON.stringify({ version: 1, size: 'square', theme: 'dark_premium', elements: [
    { id: 'title', type: 'title', headline: { text: 'Old' }, subline: { text: 'Post' } },
    { id: 'strip', type: 'photoStrip', blocks: [{ photo: null, badge: 1, label: 'A' }] },
    { id: 'doctor', type: 'doctorName', text: 'DR. X' },
  ] });
  const c = deserialize(legacy);
  assert.equal(hasLayout(c), true);
  assert.ok(c.elements.find((e) => e.id === 'strip').blocks[0].panelPos);
});
```

- [ ] **Step 2: Write the export-after-drag regression** — append to `tests/e2e/test_editor_flow.py`

```python
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
        # no editor chrome leaked into the composition JSON
        tj = page.evaluate("() => JSON.parse(window.__lastTemplateJson || 'null')")
        browser.close()
```

Also add one line to the fake host in `static/post_studio/spike/editor_harness.html` so the test can read the saved JSON — in `savePost`, after `window.__lastPng = png && png.size > 0;` add:
```javascript
      window.__lastTemplateJson = templateJson;
```

- [ ] **Step 3: Run the new tests**

Run: `node --test tests/js/composition.test.mjs`
Then: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_export_after_drag_is_untainted -q`
Expected: PASS both.

- [ ] **Step 4: Run the JS unit + syntax gate**

Run: `node --test tests/js/`
Expected: PASS (all suites green).
Then: `node --check static/post_studio/composition.js && node --check static/post_studio/themes.js && node --check static/post_studio/render.js && node --check static/post_studio/inspector.js && node --check static/post_studio/editor.js`
Expected: all OK.

- [ ] **Step 5: Run the full suite gate**

Run: `rtk proxy python -m pytest -q`
Expected: EXIT 0 (a single pre-existing `X` xpass / `s` skip acceptable; no `F`/`E`).

- [ ] **Step 6: Commit**

```bash
git add tests/js/composition.test.mjs tests/e2e/test_editor_flow.py static/post_studio/spike/editor_harness.html
git commit -m "test(post-studio): legacy-seed + export-after-drag untainted; P4b-1 phase gate green"
```

---

## Self-Review

**1. Spec coverage:**
- Absolute coordinate model (`pos` fractional, center/top-left anchors, serialized) → Task 2 (`seedLayout`, model) + Task 3 (`setPosition`). ✓
- Seed-from-layout continuity + `dark_premium` exact grid + generic derive → Task 1 (tokens) + Task 2 (seedLayout formula + exact-grid test). ✓
- Everything draggable (title unit, doctor, each panel, each pill) → Task 5 (`refsFor` covers `data-ps-el`/`data-ps-block`/`data-ps-pill-block`). ✓
- Smart guides + snap (canvas centre/margins/other elements) + guide lines → Task 6. ✓
- Keyboard nudge (1px / Shift 10px) → Task 7. ✓
- Variable-width pills (`pill.width` single/double, double text centred) as DATA + render → Task 2 (model/seed preserve) + Task 4 (render 250/516). ✓
- render.js single absolute path, inline-styles-only, hooks (`data-ps-block`, `data-ps-pill-block`) → Task 4. ✓
- Legacy posts seeded on deserialize; export-after-drag untainted; selection/guides never serialized → Task 8 (+ Task 2 deserialize, Task 6 guides are editor-chrome on the stage cleared before export re-renders). ✓
- Non-goals (resize, pill-width UI, per-block label typography) correctly absent. ✓

**2. Placeholder scan:** No "TBD"/"add error handling"/bare "write tests" — every code step shows complete code; the exact `dark_premium` token values and formula appear in Tasks 1–2. ✓

**3. Type consistency:** Position refs (`title`/`doctor`/`panel:N`/`pill:N`) are used identically in `setPosition`/`getPosition`/`nudgePosition` (T3), the drag controller `refsFor`/`posRefOf` (T5, T7), and the snap engine (T6). Layout token keys (`margin/gap/panelW/panelH/panelRowY/pillRowY/titleY/doctorY`) match between `themeLayout` (T1) and `seedLayout` (T2). Element fields (`pos`, `panelPos`, `pillPos`, `strip.panelW/panelH/gap`, `pill.width`) match between `seedLayout` (T2), `setPosition` (T3), and `render.js` (T4). Helper signatures (`seedLayout(comp)`, `ensureLayout(comp)`, `setPosition(comp,ref,xy)`, `nudgePosition(comp,ref,dxPx,dyPx,canvas)`, `themeLayout(name)`, `buildPanel(b,el,theme,index,W,H,isPill)`, `buildPill(b,el,theme,index,W,H)`) match across defining and consuming tasks. ✓
