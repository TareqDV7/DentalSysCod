# Post Studio — P4a Content Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Post Studio editor from "pick template/theme/font + add photos + save" into a real content editor — select any text run or photo block and edit its copy, typography, and photo via a side-panel inspector — plus a live EN/AR re-render hook.

**Architecture:** A select-then-inspect editor over the existing pure-ESM client modules. Selection is editor-only state (`editor.js`), never serialized into `template_json`. `render.js` gains inert `data-*` identity hooks so the editor can map clicks → elements and draw an outline (export stays clean — it re-renders a selection-free stage). New immutable `composition.js` helpers do all state changes; a new pure `inspector.js` builds the inspector DOM; `themes.js` exposes a derived `themePalette`. Other three themes' tokens are read-only.

**Tech Stack:** Pure-ESM JS modules under `static/post_studio/` (no bundler, no new runtime deps); `node --test` (DOM-free unit); Playwright (`--allow-file-access-from-files`) over the existing `static/post_studio/spike/editor_harness.html` + `render_harness.html`; pytest harness.

## Global Constraints

- **No new runtime dependencies.** No npm/pip additions.
- **`render.js` stays INLINE STYLES ONLY.** The new `data-ps-el` / `data-ps-block` hooks are bare `data-*` attributes — no className, no style, no visual effect, no external reference. Export safety (untainted foreignObject→canvas PNG) and the `@font-face`-embedded-in-export invariant are preserved; do NOT touch `rasterize.js`.
- **Selection is editor-only and NEVER serialized.** `state.selectedRef` lives in `editor.js`; it never enters `template_json`. The selection outline is applied only to the on-screen preview stage; `exportBlob()` builds its own selection-free stage via `renderComposition`.
- **Immutability:** every `composition.js` helper returns a NEW composition via `structuredClone` and never mutates its input. The editor replaces the P2b in-place `block.photo` mutation with `setBlockPhoto`.
- **Only `dark_premium` flagship render path is touched in `render.js`** beyond the universal `data-*` hooks: the `buildPill` `labelStyle` merge. The four themes' token objects in `themes.js` are unchanged; `themePalette` reads them.
- **Typography guardrails (exact values):** size clamp `SIZE_MIN = 16`, `SIZE_MAX = 160` (px, integer); custom color must match `/^#[0-9a-fA-F]{6}$/` or it is ignored; weight options come from `WEIGHTS_BY_FAMILY` (`Manrope`→`[400,700,800]`, `Playfair Display`→`[700]`, `Cairo`→`[400,700]`, `Poppins`→`[400,700]`, fallback `[400,700]`).
- **Selectable text runs** are `title.headline`, `title.subline`, `doctor`. A photo block (`block:N`) is selected as a unit; its label is edited inside the block inspector.
- **SURFACED SCOPE NOTE — label typography is SHARED.** The data model has one `strip.labelStyle` for all labels (and pill themes read `theme.label`). So editing label *typography* in a block inspector applies to ALL labels (the inspector labels this "all labels"); only the label *text* is per-block. This is consistent with the existing model and is the faithful reading of the spec's "same controls". Per-block label typography is out of scope (would need a data-model change).
- **The P3 global headline-font picker is removed** — per-element font now lives in the inspector (one source of truth). `test_editor_flow.py::test_editor_theme_and_headline_font_switch` is updated to drive the font via the inspector.
- **Non-goals (P4b or later):** free dragging, `x` positioning, exact navy_gold pixel placement, the double-span 516px pill, block drag-reorder (arrows only), per-block label typography.
- **PR HELD.** Stack P4a on `feat/post-studio`; do NOT open a PR or push to origin. Git commit attribution disabled (no Co-Authored-By).

**Base commit:** `e8a1f41` (navy_gold HEAD).

**Spec:** `docs/superpowers/specs/2026-06-30-post-studio-p4a-content-editing.md`

---

### Task 1: Immutable content helpers in composition.js

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: existing `withBlocks`/`renumber` patterns, `structuredClone`.
- Produces:
  - `SIZE_MIN = 16`, `SIZE_MAX = 160` (exported consts).
  - `setText(comp, ref, value) -> comp` — `ref ∈ {'title.headline','title.subline','doctor'}`; sets that run's `.text`. Throws on a bad ref.
  - `setTypography(comp, ref, patch) -> comp` — `ref ∈ {'title.headline','title.subline','doctor','strip.label'}`; merges `{font?,size?,weight?,color?}` with size clamped to `[SIZE_MIN,SIZE_MAX]` and color applied only if it matches `/^#[0-9a-fA-F]{6}$/`. Throws on a bad ref.
  - `setBlockLabel(comp, index, value) -> comp` — sets `blocks[index].label`.
  - `setBlockPhoto(comp, index, photo) -> comp` — sets `blocks[index].photo`.

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import {
  setText, setTypography, setBlockLabel, setBlockPhoto, SIZE_MIN, SIZE_MAX,
  defaultComposition,
} from '../../static/post_studio/composition.js';

function comp() { return defaultComposition('before_after'); }

test('setText sets the run text immutably', () => {
  const c0 = comp();
  const c1 = setText(c0, 'title.headline', 'Whitening');
  const t0 = c0.elements.find((e) => e.id === 'title');
  const t1 = c1.elements.find((e) => e.id === 'title');
  assert.equal(t1.headline.text, 'Whitening');
  assert.notEqual(t0.headline.text, 'Whitening');   // input not mutated
});

test('setText supports subline and doctor, rejects bad refs', () => {
  const c = comp();
  assert.equal(setText(c, 'title.subline', 'Sub').elements.find((e) => e.id === 'title').subline.text, 'Sub');
  assert.equal(setText(c, 'doctor', 'DR. X').elements.find((e) => e.id === 'doctor').text, 'DR. X');
  assert.throws(() => setText(c, 'strip.label', 'no'));
});

test('setTypography merges font/weight, clamps size, validates hex', () => {
  const c = comp();
  const out = setTypography(c, 'title.headline',
    { font: 'Cairo', weight: 800, size: 999, color: '#abcdef' });
  const h = out.elements.find((e) => e.id === 'title').headline;
  assert.equal(h.font, 'Cairo');
  assert.equal(h.weight, 800);
  assert.equal(h.size, SIZE_MAX);                 // 999 clamped to 160
  assert.equal(h.color, '#abcdef');
  // below-min clamps up; invalid hex ignored (keeps prior color)
  const out2 = setTypography(out, 'title.headline', { size: 2, color: 'red' });
  const h2 = out2.elements.find((e) => e.id === 'title').headline;
  assert.equal(h2.size, SIZE_MIN);
  assert.equal(h2.color, '#abcdef');
});

test('setTypography on strip.label writes the shared labelStyle', () => {
  const c = comp();
  const out = setTypography(c, 'strip.label', { size: 44 });
  assert.equal(out.elements.find((e) => e.id === 'strip').labelStyle.size, 44);
});

test('setBlockLabel and setBlockPhoto are immutable per-block updates', () => {
  const c = comp();
  const c1 = setBlockLabel(c, 0, 'Day 1');
  assert.equal(c1.elements.find((e) => e.id === 'strip').blocks[0].label, 'Day 1');
  assert.equal(c.elements.find((e) => e.id === 'strip').blocks[0].label, 'Before Treatment');
  const c2 = setBlockPhoto(c, 1, 'data:image/png;base64,AAAA');
  assert.equal(c2.elements.find((e) => e.id === 'strip').blocks[1].photo, 'data:image/png;base64,AAAA');
  assert.equal(c.elements.find((e) => e.id === 'strip').blocks[1].photo, null);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `setText`/`setTypography`/`setBlockLabel`/`setBlockPhoto` are not exported.

- [ ] **Step 3: Implement the helpers** — append to `static/post_studio/composition.js`

```javascript
export const SIZE_MIN = 16;
export const SIZE_MAX = 160;
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function clampSize(n) {
  const v = Math.round(Number(n));
  if (!Number.isFinite(v)) return null;
  return Math.max(SIZE_MIN, Math.min(SIZE_MAX, v));
}

// A selectable text run (has its own .text): headline, subline, doctor.
function textRunTarget(comp, ref) {
  const title = comp.elements.find((e) => e.id === 'title');
  const doctor = comp.elements.find((e) => e.id === 'doctor');
  if (ref === 'title.headline') return title && title.headline;
  if (ref === 'title.subline') return title && title.subline;
  if (ref === 'doctor') return doctor;
  return null;
}

// A typography target — text runs plus the shared label style.
function typoTarget(comp, ref) {
  if (ref === 'strip.label') {
    const strip = comp.elements.find((e) => e.id === 'strip');
    return strip && strip.labelStyle;
  }
  return textRunTarget(comp, ref);
}

export function setText(comp, ref, value) {
  const next = structuredClone(comp);
  const target = textRunTarget(next, ref);
  if (!target) throw new Error(`bad text ref: ${ref}`);
  target.text = String(value);
  return next;
}

export function setTypography(comp, ref, patch) {
  const next = structuredClone(comp);
  const target = typoTarget(next, ref);
  if (!target) throw new Error(`bad typography ref: ${ref}`);
  if (patch.font != null) target.font = String(patch.font);
  if (patch.weight != null) target.weight = Number(patch.weight);
  if (patch.size != null) {
    const v = clampSize(patch.size);
    if (v != null) target.size = v;
  }
  if (patch.color != null && HEX_RE.test(patch.color)) target.color = patch.color;
  return next;
}

function updateBlock(comp, index, patch) {
  const next = structuredClone(comp);
  const strip = next.elements.find((e) => e.id === 'strip');
  if (!strip) throw new Error('composition has no photoStrip');
  if (index < 0 || index >= strip.blocks.length) throw new Error(`bad index ${index}`);
  strip.blocks[index] = { ...strip.blocks[index], ...patch };
  return next;
}

export function setBlockLabel(comp, index, value) {
  return updateBlock(comp, index, { label: String(value) });
}

export function setBlockPhoto(comp, index, photo) {
  return updateBlock(comp, index, { photo });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS (all new tests green).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/composition.js
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): immutable content helpers (setText/setTypography/setBlockLabel/setBlockPhoto)"
```

---

### Task 2: themePalette in themes.js

**Files:**
- Modify: `static/post_studio/themes.js`
- Test: `tests/js/themes.test.mjs`

**Interfaces:**
- Consumes: existing `themeTokens(name)`.
- Produces: `themePalette(name) -> string[]` — uppercase 6-digit hex swatches derived from the theme's own role colors, in order `[accent, headline.color, subline.color, doctor.color, label.color, card.background]`, de-duplicated (case-insensitive), skipping any non-hex value (gradients/rgba/none). Unknown name falls back to `dark_premium` (via `themeTokens`).

- [ ] **Step 1: Write the failing test** — append to `tests/js/themes.test.mjs`

```javascript
import { themePalette } from '../../static/post_studio/themes.js';

test('themePalette derives deduped hex swatches from theme tokens', () => {
  // navy_gold: gold (accent/subline/doctor), white (headline/label), navy (card bg)
  assert.deepEqual(themePalette('dark_premium'), ['#C6A274', '#F5F5F0', '#08162C']);
});

test('themePalette skips non-hex values and dedupes per theme', () => {
  const light = themePalette('light_luxury');
  assert.ok(light.includes('#B08D3C'));   // accent/subline/doctor gold
  assert.ok(light.includes('#FFFFFF'));   // card background
  // all entries are 6-digit uppercase hex, no duplicates
  const set = new Set(light);
  assert.equal(set.size, light.length);
  for (const c of light) assert.match(c, /^#[0-9A-F]{6}$/);
});

test('themePalette falls back to dark_premium for unknown names', () => {
  assert.deepEqual(themePalette('nope'), themePalette('dark_premium'));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/themes.test.mjs`
Expected: FAIL — `themePalette` is not exported.

- [ ] **Step 3: Implement** — append to `static/post_studio/themes.js`

```javascript
// Curated color swatches for the editor inspector, derived (read-only) from a
// theme's own role colors. Non-hex values (gradients/rgba) are skipped.
export function themePalette(name) {
  const t = themeTokens(name);
  const candidates = [
    t.accent,
    t.headline && t.headline.color,
    t.subline && t.subline.color,
    t.doctor && t.doctor.color,
    t.label && t.label.color,
    t.card && t.card.background,
  ];
  const seen = new Set();
  const out = [];
  for (const c of candidates) {
    if (!c) continue;
    const hex = String(c).toUpperCase();
    if (!/^#[0-9A-F]{6}$/.test(hex)) continue;
    if (seen.has(hex)) continue;
    seen.add(hex);
    out.push(hex);
  }
  return out;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/themes.test.mjs`
Expected: PASS.

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/themes.js
git add static/post_studio/themes.js tests/js/themes.test.mjs
git commit -m "feat(post-studio): themePalette derives curated inspector swatches from theme tokens"
```

---

### Task 3: render.js identity hooks + pill labelStyle merge

**Files:**
- Modify: `static/post_studio/render.js`
- Modify: `static/post_studio/spike/render_harness.html` (expose selectable-ref probes)
- Test: `tests/e2e/test_editor_render.py`

**Interfaces:**
- Consumes: existing `buildTitle`/`buildDoctor`/`buildStrip`/`buildCard`/`buildPill`.
- Produces (rendered DOM contract): the headline node has `data-ps-el="title.headline"` (keeps its existing `data-ps-headline`); the subline node `data-ps-el="title.subline"`; the doctor node `data-ps-el="doctor"`; each photo card `data-ps-block="<index>"`. Pill label text honors `el.labelStyle` overrides.

- [ ] **Step 1: Add render-side probes to the harness** — edit `static/post_studio/spike/render_harness.html`, inside `window.__describe`'s returned object (next to `pills`):

```javascript
      psEls: Array.from(stage.querySelectorAll('[data-ps-el]')).map((n) => n.getAttribute('data-ps-el')),
      blockCount: stage.querySelectorAll('[data-ps-block]').length,
      pillLabelSize: (() => {
        const t = stage.querySelector('[data-ps-pill] > div:last-child');
        return t ? t.style.fontSize : null;
      })(),
```

- [ ] **Step 2: Write the failing tests** — append to `tests/e2e/test_editor_render.py`

```python
def test_identity_hooks_and_pill_labelstyle_override():
    comp = {
        "version": 1, "size": "square", "theme": "dark_premium",
        "elements": [
            {"id": "title", "type": "title", "x": 0.5, "y": 0.15, "align": "center",
             "headline": {"text": "Root Canal"}, "subline": {"text": "Lower Molar"}},
            {"id": "strip", "type": "photoStrip", "layout": "row",
             "labelStyle": {"font": "Poppins", "size": 44, "weight": 400, "color": "#F5F5F0"},
             "blocks": [{"photo": None, "badge": 1, "label": "Before"},
                        {"photo": None, "badge": 2, "label": "After"}]},
            {"id": "doctor", "type": "doctorName", "x": 0.5, "y": 0.93, "align": "center",
             "text": "DR. WASFY"},
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
    # pill label honors the overridden shared labelStyle size (proves buildPill merge)
    assert info["pillLabelSize"] == "44px", info
```

(`HARNESS`, `_LAUNCH_ARGS`, `sync_playwright` already exist at the top of this file.)

- [ ] **Step 3: Add the hooks + pill merge** — edit `static/post_studio/render.js`:

In `buildTitle`, after `head.setAttribute('data-ps-headline', '');` add:
```javascript
  head.setAttribute('data-ps-el', 'title.headline');
```
and after creating `sub` (`const sub = document.createElement('div');`) add:
```javascript
  sub.setAttribute('data-ps-el', 'title.subline');
```

In `buildDoctor`, after `const box = document.createElement('div');` add:
```javascript
  box.setAttribute('data-ps-el', 'doctor');
```

Change `buildCard`'s signature and add the block hook:
```javascript
function buildCard(b, el, theme, index) {
  const isPill = theme.label && theme.label.style === 'pill';
  const card = document.createElement('div');
  card.setAttribute('data-ps-block', String(index));
```
and its pill branch to pass `el`:
```javascript
  if (isPill) {
    card.appendChild(buildPill(b, el, theme));
  } else {
```

Change `buildStrip`'s loop to pass the index:
```javascript
  blocks.forEach((b, i) => wrap.appendChild(buildCard(b, el, theme, i)));
```

Change `buildPill`'s signature and merge `el.labelStyle` into the label text:
```javascript
function buildPill(b, el, theme) {
```
and its `text` style:
```javascript
  setStyle(text, {
    ...typoStyle({ ...theme.label, ...el.labelStyle, color: theme.pill.color || theme.label.color }, b.label),
    flex: '1 1 auto', textAlign: 'left',
  });
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_render.py -q`
Expected: PASS (all render tests, including the new one).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/render.js
git add static/post_studio/render.js static/post_studio/spike/render_harness.html tests/e2e/test_editor_render.py
git commit -m "feat(post-studio): render identity hooks (data-ps-el/data-ps-block) + pill labelStyle merge"
```

---

### Task 4: editor.js selection plumbing (click → select + outline + inspector slot)

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: render hooks from Task 3; existing `mountEditor` structure.
- Produces: an inspector region with `data-ps-inspector` whose `dataset.psSelected` is the current selection (`''`, a text ref like `title.headline`, or `block:N`); clicking a `[data-ps-el]`/`[data-ps-block]` node selects it and outlines it on the on-screen stage; clicking empty canvas deselects. A `renderInspector()` function (placeholder body here; filled in Tasks 5–6) and a `selectRef(ref)` function.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
def test_selection_outline_and_inspector_slot():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # nothing selected initially
        assert page.get_attribute("[data-ps-inspector]", "data-ps-selected") == ""
        # click the headline -> it becomes selected and gets an outline
        page.click("[data-ps-el='title.headline']")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-inspector]').dataset.psSelected === 'title.headline'")
        assert page.evaluate(
            "() => /solid/.test(document.querySelector('[data-ps-el=\"title.headline\"]').style.outline)")
        # click a photo block -> block selection
        page.click("[data-ps-block='1']")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-inspector]').dataset.psSelected === 'block:1'")
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_selection_outline_and_inspector_slot -q`
Expected: FAIL — no `[data-ps-inspector]` element exists.

- [ ] **Step 3: Implement selection plumbing** — edit `static/post_studio/editor.js`:

Add `selectedRef` to the initial state:
```javascript
  const state = { comp: defaultComposition('before_after'), selectedRef: null };
```

Add the inspector slot to the controls column. After `controls.appendChild(themeGroup);` add:
```javascript
  const inspectorSlot = el('div', { 'data-ps-inspector': '' }, {
    display: 'flex', flexDirection: 'column', gap: '10px',
    padding: '12px', border: '1px solid rgba(0,0,0,.12)', borderRadius: '8px' });
  controls.appendChild(inspectorSlot);
```

Attach a single delegated click handler (once) right after the preview column is built — after `previewCol.appendChild(previewBox);` add:
```javascript
  previewBox.addEventListener('click', (e) => {
    const elNode = e.target.closest('[data-ps-el]');
    if (elNode) { selectRef(elNode.getAttribute('data-ps-el')); return; }
    const blockNode = e.target.closest('[data-ps-block]');
    if (blockNode) { selectRef('block:' + blockNode.getAttribute('data-ps-block')); return; }
    selectRef(null);
  });
```

In `renderPreview()`, after `previewBox.appendChild(scaler);` and the `previewBox._stage = stage;` line, draw the outline for the current selection:
```javascript
    if (state.selectedRef) {
      const sel = state.selectedRef.startsWith('block:')
        ? stage.querySelector(`[data-ps-block="${state.selectedRef.slice(6)}"]`)
        : stage.querySelector(`[data-ps-el="${state.selectedRef}"]`);
      if (sel) { sel.style.outline = '3px solid #38bdf8'; sel.style.outlineOffset = '4px'; }
    }
```

Add `selectRef` and a placeholder `renderInspector` (filled in later tasks) before `// init`:
```javascript
  function selectRef(ref) {
    state.selectedRef = ref;
    renderPreview();
    renderInspector();
  }

  function renderInspector() {
    inspectorSlot.innerHTML = '';
    inspectorSlot.dataset.psSelected = state.selectedRef || '';
    if (!state.selectedRef) {
      inspectorSlot.appendChild(el('p', { text: 'Select an element to edit.' },
        { margin: '0', opacity: '0.7', fontSize: '0.9em' }));
    }
  }
```

Call `renderInspector()` once at init — change the init block:
```javascript
  // init
  renderPreview();
  renderInspector();
  refreshGallery();
  rootEl.dataset.psReady = '1';
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (existing two tests + the new selection test).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/editor.js
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): editor selection plumbing — click-to-select, outline, inspector slot"
```

---

### Task 5: Text inspector (inspector.js) + wire headline/subline/doctor; remove global font picker

**Files:**
- Create: `static/post_studio/inspector.js`
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `FONT_OPTIONS` (fonts.js), `SIZE_MIN`/`SIZE_MAX` (composition.js), `themePalette` (themes.js); `setText`/`setTypography` (composition.js); render hooks (Task 3).
- Produces:
  - `inspector.js`: `weightsFor(family) -> number[]`; `buildTextInspector(run, opts) -> HTMLElement` where `run = {text, font, size, weight, color}` and `opts = {lang, palette, onText(value), onTypography(patch), onFont(family)}`. The returned root has `data-ps-inspector-text`; its controls carry `data-ps-field` of `text|font|size|weight|color`.
  - `editor.js`: `renderInspector()` builds the text inspector for a text-run selection; the global headline-font picker (`fontGroup`/`setHeadlineFont`) is removed.

- [ ] **Step 1: Write the failing test** — replace `test_editor_theme_and_headline_font_switch` in `tests/e2e/test_editor_flow.py` with an inspector-driven version, and add a text-edit test:

```python
def test_headline_font_via_inspector_and_text_edit():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # switch to light_luxury (Playfair default) so a Manrope pick is non-vacuous
        page.click("[data-ps-theme='light_luxury']")
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('[data-ps-stage]')).backgroundImage === 'none'")
        # select the headline -> text inspector appears
        page.click("[data-ps-el='title.headline']")
        page.wait_for_selector("[data-ps-inspector-text]")
        # pick Manrope in the inspector font dropdown -> headline font-family updates
        page.select_option("[data-ps-inspector-text] [data-ps-field='font']", "Manrope")
        page.wait_for_function(
            "() => /Manrope/.test(getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily)")
        # edit the headline text -> the rendered headline updates
        page.fill("[data-ps-inspector-text] [data-ps-field='text']", "Veneers")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-headline]').textContent === 'Veneers'")
        # the global font picker is gone
        assert page.query_selector("[data-ps-fontopt]") is None
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_headline_font_via_inspector_and_text_edit -q`
Expected: FAIL — no `[data-ps-inspector-text]`.

- [ ] **Step 3: Create `static/post_studio/inspector.js`**

```javascript
// inspector.js — pure DOM builders for the Post Studio selection inspector.
// No serialization touches this; it builds editor-chrome controls only.
import { FONT_OPTIONS } from './fonts.js';
import { SIZE_MIN, SIZE_MAX } from './composition.js';

export const WEIGHTS_BY_FAMILY = {
  'Manrope': [400, 700, 800],
  'Playfair Display': [700],
  'Cairo': [400, 700],
  'Poppins': [400, 700],
};

export function weightsFor(family) {
  return WEIGHTS_BY_FAMILY[family] || [400, 700];
}

function elt(tag, attrs = {}, styles = {}) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
  }
  Object.assign(n.style, styles);
  return n;
}

function fieldLabel(text) {
  return elt('label', { text }, { display: 'block', fontSize: '0.8em', opacity: '0.75', marginBottom: '2px' });
}

function colorRow(palette, current, onColor) {
  const row = elt('div', {}, { display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' });
  for (const hex of palette) {
    const sw = elt('button', { type: 'button', 'data-ps-swatch': hex }, {
      width: '22px', height: '22px', borderRadius: '50%', cursor: 'pointer',
      background: hex, border: hex.toUpperCase() === String(current).toUpperCase()
        ? '2px solid #38bdf8' : '1px solid rgba(0,0,0,.25)' });
    sw.addEventListener('click', () => onColor(hex));
    row.appendChild(sw);
  }
  const custom = elt('input', { type: 'text', 'data-ps-field': 'color', placeholder: '#______',
    value: current || '' }, { width: '92px', marginInlineStart: '4px' });
  custom.addEventListener('input', () => onColor(custom.value));
  row.appendChild(custom);
  return row;
}

// run: { text, font, size, weight, color }
// opts: { lang, palette, onText, onTypography, onFont }
export function buildTextInspector(run, opts) {
  const ar = opts.lang === 'ar';
  const root = elt('div', { 'data-ps-inspector-text': '' },
    { display: 'flex', flexDirection: 'column', gap: '10px' });

  const text = elt('input', { type: 'text', 'data-ps-field': 'text', value: run.text || '' }, { width: '100%' });
  text.addEventListener('input', () => opts.onText(text.value));
  const textWrap = elt('div'); textWrap.appendChild(fieldLabel(ar ? 'النص' : 'Text')); textWrap.appendChild(text);
  root.appendChild(textWrap);

  const font = elt('select', { 'data-ps-field': 'font' }, { width: '100%' });
  for (const o of FONT_OPTIONS) {
    const opt = elt('option', { value: o.family, text: ar ? o.label_ar : o.label });
    if (o.family === run.font) opt.selected = true;
    font.appendChild(opt);
  }
  font.addEventListener('change', () => opts.onFont(font.value));
  const fontWrap = elt('div'); fontWrap.appendChild(fieldLabel(ar ? 'الخط' : 'Font')); fontWrap.appendChild(font);
  root.appendChild(fontWrap);

  const size = elt('input', { type: 'range', 'data-ps-field': 'size',
    min: String(SIZE_MIN), max: String(SIZE_MAX), value: String(run.size || 40) }, { width: '100%' });
  size.addEventListener('input', () => opts.onTypography({ size: Number(size.value) }));
  const sizeWrap = elt('div');
  sizeWrap.appendChild(fieldLabel((ar ? 'الحجم' : 'Size') + ': ' + (run.size || 40)));
  sizeWrap.appendChild(size);
  root.appendChild(sizeWrap);

  const weight = elt('select', { 'data-ps-field': 'weight' }, { width: '100%' });
  for (const w of weightsFor(run.font)) {
    const opt = elt('option', { value: String(w), text: String(w) });
    if (w === run.weight) opt.selected = true;
    weight.appendChild(opt);
  }
  weight.addEventListener('change', () => opts.onTypography({ weight: Number(weight.value) }));
  const weightWrap = elt('div'); weightWrap.appendChild(fieldLabel(ar ? 'السماكة' : 'Weight')); weightWrap.appendChild(weight);
  root.appendChild(weightWrap);

  const colorWrap = elt('div'); colorWrap.appendChild(fieldLabel(ar ? 'اللون' : 'Color'));
  colorWrap.appendChild(colorRow(opts.palette, run.color, (hex) => opts.onTypography({ color: hex })));
  root.appendChild(colorWrap);

  return root;
}
```

- [ ] **Step 4: Wire it into editor.js + remove the global font picker**

In `static/post_studio/editor.js`:

Add imports:
```javascript
import { TEMPLATES, defaultComposition, serialize, deserialize, applyTheme,
         setText, setTypography } from './composition.js';
import { THEME_OPTIONS, themePalette } from './themes.js';
import { buildTextInspector, weightsFor } from './inspector.js';
```
(Leave the existing `FONT_OPTIONS, ensureFontsLoaded` import from fonts.js — `ensureFontsLoaded` is still used; `FONT_OPTIONS` is now used by inspector.js, so drop `FONT_OPTIONS` from the editor import: `import { ensureFontsLoaded } from './fonts.js';`)

Delete the global headline-font picker block (the `// ── Headline font picker ──` group: `fontGroup` creation through `fontGroup.appendChild(fontRow);`), delete `controls.appendChild(fontGroup);`, and delete the `setHeadlineFont` function. Remove the now-unused `headline_font` keys from both `STR.en` and `STR.ar`.

Add a `currentRun` helper and flesh out `renderInspector` for text runs. Replace the placeholder `renderInspector` from Task 4 with:
```javascript
  function currentRun(ref) {
    const title = state.comp.elements.find((e) => e.id === 'title');
    const doctor = state.comp.elements.find((e) => e.id === 'doctor');
    if (ref === 'title.headline') return title && title.headline;
    if (ref === 'title.subline') return title && title.subline;
    if (ref === 'doctor') return doctor;
    return null;
  }

  function renderInspector() {
    inspectorSlot.innerHTML = '';
    inspectorSlot.dataset.psSelected = state.selectedRef || '';
    const ref = state.selectedRef;
    if (!ref) {
      inspectorSlot.appendChild(el('p', { text: s.select_hint },
        { margin: '0', opacity: '0.7', fontSize: '0.9em' }));
      return;
    }
    if (ref.startsWith('block:')) return;   // block inspector arrives in Task 6
    const run = currentRun(ref);
    if (!run) return;
    inspectorSlot.appendChild(buildTextInspector(
      { text: run.text, font: run.font, size: run.size, weight: run.weight, color: run.color },
      {
        lang,
        palette: themePalette(state.comp.theme),
        onText: (v) => { state.comp = setText(state.comp, ref, v); renderPreview(); },
        onTypography: (patch) => { state.comp = setTypography(state.comp, ref, patch); renderPreview(); },
        onFont: (family) => {
          const allowed = weightsFor(family);
          const w = allowed.includes(run.weight) ? run.weight : allowed[0];
          state.comp = setTypography(state.comp, ref, { font: family, weight: w });
          renderPreview(); renderInspector();
        },
      }));
  }
```

Add the `select_hint` string to both languages of `STR`:
```javascript
// en:
        select_hint: 'Select an element to edit.',
// ar:
        select_hint: 'اختر عنصرًا لتعديله.',
```
(and update the Task 4 placeholder text reference, now `s.select_hint`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (template/save/reopen, selection, the new inspector font+text test).

- [ ] **Step 6: Syntax-check and commit**

```bash
node --check static/post_studio/inspector.js && node --check static/post_studio/editor.js
git add static/post_studio/inspector.js static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): text inspector (text/font/size/weight/color); retire global font picker"
```

---

### Task 6: Block inspector + wire label/photo/order ops + immutable onAddPhotos

**Files:**
- Modify: `static/post_studio/inspector.js`
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `addBlock`/`removeBlock`/`reorderBlock`/`MAX_BLOCKS` (existing), `setBlockLabel`/`setBlockPhoto`/`setTypography` (Task 1), `buildTextInspector` building blocks; `host.pickPhotos`.
- Produces:
  - `inspector.js`: `buildBlockInspector(block, labelStyle, opts) -> HTMLElement` with `data-ps-inspector-block`; `opts = {lang, palette, index, count, maxBlocks, onLabel(value), onLabelTypography(patch), onLabelFont(family), onReplace, onRemove, onMoveLeft, onMoveRight, onAdd}`. Buttons carry `data-ps-action` of `replace|remove|move-left|move-right|add-block`; Remove disabled when `count<=1`; Move disabled at the ends; Add disabled when `count>=maxBlocks`.
  - `editor.js`: `renderInspector()` handles `block:N`; `onAddPhotos` uses `setBlockPhoto` (no in-place mutation).

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
def test_block_inspector_label_move_add_remove():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # select block 0 -> block inspector
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-inspector-block]")
        # edit its label -> the rendered label/pill text updates
        page.fill("[data-ps-inspector-block] [data-ps-field='label']", "Day 1")
        page.wait_for_function(
            "() => document.querySelector('[data-ps-stage]').textContent.includes('Day 1')")
        # add a block -> 3 blocks, badges renumber 1..3
        page.click("[data-ps-inspector-block] [data-ps-action='add-block']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-block]').length === 3")
        # remove the currently selected block -> back to 2
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-inspector-block]")
        page.click("[data-ps-inspector-block] [data-ps-action='remove']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-block]').length === 2")
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_block_inspector_label_move_add_remove -q`
Expected: FAIL — no `[data-ps-inspector-block]`.

- [ ] **Step 3: Add `buildBlockInspector`** — append to `static/post_studio/inspector.js`

```javascript
function actionBtn(label, action, disabled, onClick) {
  const b = elt('button', { type: 'button', 'data-ps-action': action, text: label });
  b.className = 'btn';
  if (disabled) { b.disabled = true; b.style.opacity = '0.5'; }
  else b.addEventListener('click', onClick);
  return b;
}

// block: { photo, badge, label }; labelStyle: shared { font,size,weight,color }
// opts: { lang, palette, index, count, maxBlocks,
//         onLabel, onLabelTypography, onLabelFont, onReplace, onRemove,
//         onMoveLeft, onMoveRight, onAdd }
export function buildBlockInspector(block, labelStyle, opts) {
  const ar = opts.lang === 'ar';
  const root = elt('div', { 'data-ps-inspector-block': '' },
    { display: 'flex', flexDirection: 'column', gap: '10px' });

  const label = elt('input', { type: 'text', 'data-ps-field': 'label', value: block.label || '' }, { width: '100%' });
  label.addEventListener('input', () => opts.onLabel(label.value));
  const labelWrap = elt('div');
  labelWrap.appendChild(fieldLabel(ar ? 'التسمية' : 'Label'));
  labelWrap.appendChild(label);
  root.appendChild(labelWrap);

  // shared label typography (applies to ALL labels)
  const note = elt('div', { text: ar ? '(يطبَّق على كل التسميات)' : '(applies to all labels)' },
    { fontSize: '0.75em', opacity: '0.6' });
  root.appendChild(note);
  root.appendChild(buildTextInspector(
    { text: undefined, font: labelStyle.font, size: labelStyle.size, weight: labelStyle.weight, color: labelStyle.color },
    { lang: opts.lang, palette: opts.palette,
      onText: () => {}, onTypography: opts.onLabelTypography, onFont: opts.onLabelFont }));

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

The text inspector inside the block inspector edits a run with no `.text` (the label text input is separate); its `onText` is a no-op. To keep the shared-label text input from being shadowed, the `buildTextInspector` call above passes `text: undefined`, so its text field renders empty and is unused — acceptable, but to avoid confusion the implementer may pass a variant. (Verified acceptable: the block inspector's own `data-ps-field='label'` input is the label-text control; the nested text inspector supplies font/size/weight/color only.)

- [ ] **Step 4: Wire it into editor.js**

In `static/post_studio/editor.js`:

Extend imports:
```javascript
import { TEMPLATES, MAX_BLOCKS, defaultComposition, serialize, deserialize, applyTheme,
         setText, setTypography, setBlockLabel, setBlockPhoto,
         addBlock, removeBlock, reorderBlock } from './composition.js';
import { buildTextInspector, buildBlockInspector, weightsFor } from './inspector.js';
```

In `renderInspector()`, replace the `if (ref.startsWith('block:')) return;` line with a block-inspector branch:
```javascript
    if (ref.startsWith('block:')) {
      const i = Number(ref.slice(6));
      const strip = state.comp.elements.find((e) => e.id === 'strip');
      if (!strip || i < 0 || i >= strip.blocks.length) { state.selectedRef = null; inspectorSlot.dataset.psSelected = ''; return; }
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
      return;
    }
```

Rewrite `onAddPhotos` to be immutable:
```javascript
  async function onAddPhotos() {
    const picked = await host.pickPhotos();
    if (!picked || !picked.length) return;
    const strip = state.comp.elements.find((e) => e.id === 'strip');
    if (!strip) return;
    let next = state.comp; let pi = 0;
    strip.blocks.forEach((b, i) => {
      if (!b.photo && pi < picked.length) { next = setBlockPhoto(next, i, picked[pi++].dataUrl); }
    });
    state.comp = next;
    renderPreview();
  }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (all editor-flow tests including the block inspector test).

- [ ] **Step 6: Syntax-check and commit**

```bash
node --check static/post_studio/inspector.js && node --check static/post_studio/editor.js
git add static/post_studio/inspector.js static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): block inspector (label/typography/replace/remove/move/add) + immutable add-photos"
```

---

### Task 7: Live EN/AR re-render hook + inspector localization

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: existing `mountEditor`; `STR` map.
- Produces: `mountEditor(rootEl, host, opts = {})` accepting `opts.initialComp` (a composition to seed instead of the default). A single `MutationObserver` on `document.documentElement`'s `lang` re-mounts the editor in the new language, preserving `state.comp`.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
def test_language_toggle_rerenders_and_preserves_comp():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # set a custom headline via the inspector
        page.click("[data-ps-el='title.headline']")
        page.wait_for_selector("[data-ps-inspector-text]")
        page.fill("[data-ps-inspector-text] [data-ps-field='text']", "Implants")
        page.wait_for_function("() => document.querySelector('[data-ps-headline]').textContent === 'Implants'")
        # flip the document language to Arabic
        page.evaluate("() => document.documentElement.setAttribute('lang', 'ar')")
        # editor re-mounts in Arabic (a known Arabic chrome string appears) ...
        page.wait_for_function("() => document.body.textContent.includes('القالب اللوني')")
        # ... and the custom composition survives the re-mount
        page.wait_for_function("() => document.querySelector('[data-ps-headline]').textContent === 'Implants'")
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_language_toggle_rerenders_and_preserves_comp -q`
Expected: FAIL — language change does not re-render the editor.

- [ ] **Step 3: Implement the hook** — edit `static/post_studio/editor.js`:

Change the signature and seed:
```javascript
export function mountEditor(rootEl, host, opts = {}) {
  ensureFontsLoaded();
  const lang = document.documentElement.lang === 'ar' ? 'ar' : 'en';
  const s = STR[lang];
  const tl = TPL_LABEL[lang];
  const state = { comp: opts.initialComp || defaultComposition('before_after'), selectedRef: null };
```

At the end of `mountEditor`, just before the `// init` block, install a single lang observer that re-mounts preserving the composition:
```javascript
  if (rootEl._psLangObserver) { rootEl._psLangObserver.disconnect(); rootEl._psLangObserver = null; }
  const langObserver = new MutationObserver(() => {
    const cur = document.documentElement.lang === 'ar' ? 'ar' : 'en';
    if (cur !== lang) {
      langObserver.disconnect();
      rootEl._psLangObserver = null;
      mountEditor(rootEl, host, { initialComp: state.comp });
    }
  });
  langObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  rootEl._psLangObserver = langObserver;
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py -q`
Expected: PASS (all editor-flow tests including the language toggle test).

- [ ] **Step 5: Syntax-check and commit**

```bash
node --check static/post_studio/editor.js
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): live EN/AR re-render hook preserving the composition (P2b carry)"
```

---

### Task 8: Export-after-edit regression + phase gate

**Files:**
- Test: `tests/e2e/test_editor_flow.py`
- (verification only — no source changes expected)

**Interfaces:**
- Consumes: everything above; the fake host's `__lastPng`/`__savedCount` flags in `editor_harness.html`.
- Produces: a regression test proving that after content edits the export is still a non-empty (untainted) PNG; a green phase gate across `node --test`, `node --check`, and the full pytest suite.

- [ ] **Step 1: Write the regression test** — append to `tests/e2e/test_editor_flow.py`

```python
def test_export_after_edits_is_untainted():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # edit text + add photos, then save -> the fake host gets a non-empty PNG
        page.click("[data-ps-el='title.headline']")
        page.wait_for_selector("[data-ps-inspector-text]")
        page.fill("[data-ps-inspector-text] [data-ps-field='text']", "Crowns")
        page.click("[data-ps-action='add-photos']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length === 2")
        page.click("[data-ps-action='save']")
        page.wait_for_function("() => window.__savedCount === 1")
        assert page.evaluate("() => window.__lastPng") is True   # PNG produced => canvas not tainted
        browser.close()
```

- [ ] **Step 2: Run the regression test**

Run: `rtk proxy python -m pytest tests/e2e/test_editor_flow.py::test_export_after_edits_is_untainted -q`
Expected: PASS.

- [ ] **Step 3: Run the JS unit gate**

Run: `node --test tests/js/`
Expected: PASS (all suites green).
Then: `node --check static/post_studio/composition.js && node --check static/post_studio/themes.js && node --check static/post_studio/render.js && node --check static/post_studio/inspector.js && node --check static/post_studio/editor.js`
Expected: all OK.

- [ ] **Step 4: Run the full suite gate**

Run: `rtk proxy python -m pytest -q`
Expected: EXIT 0 (1 pre-existing `X` xpass / `s` skip acceptable; no `F`/`E`).

- [ ] **Step 5: Commit the regression test**

```bash
git add tests/e2e/test_editor_flow.py
git commit -m "test(post-studio): export-after-edit stays untainted; P4a phase gate green"
```

---

## Self-Review

**1. Spec coverage:**
- Select + side-panel inspector → Tasks 4 (selection) + 5 (text inspector) + 6 (block inspector). ✓
- Type your own headline/subline/labels/doctor → `setText` (T1), text inspector (T5), block label (T6). ✓
- Per-element typography curated + custom (font/size/weight/color, clamp, palette) → `setTypography` (T1), `themePalette` (T2), inspector controls (T5). ✓
- Photo blocks add/remove/replace/reorder-by-arrows + renumber → block inspector (T6) reusing existing block ops. ✓
- Immutable `setBlockPhoto` replacing in-place mutation → T1 + T6 `onAddPhotos`. ✓
- Live EN/AR re-render hook (P2b carry) → T7. ✓
- Selection never serialized; render `data-*` hooks export-safe → T3 + Global Constraints. ✓
- Remove global headline-font picker → T5. ✓
- Export-after-edit untainted → T8. ✓

**2. Placeholder scan:** No "TBD"/"add error handling"/bare "write tests" — every code step shows complete code; the one intentional `onText: () => {}` no-op in the block inspector's nested typography control is explained inline. ✓

**3. Type consistency:** Ref strings (`title.headline`/`title.subline`/`doctor`/`strip.label`/`block:N`) are used identically in `composition.js` helpers (T1), `render.js` `data-ps-el` (T3), and `editor.js` selection/inspector (T4–6). Helper signatures (`setText(comp,ref,value)`, `setTypography(comp,ref,patch)`, `setBlockLabel(comp,index,value)`, `setBlockPhoto(comp,index,photo)`, `themePalette(name)`, `weightsFor(family)`, `buildTextInspector(run,opts)`, `buildBlockInspector(block,labelStyle,opts)`) match across their defining and consuming tasks. ✓
