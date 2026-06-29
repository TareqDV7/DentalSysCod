# Post Studio — P3 (Premium Themes + Templates + Fonts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the neutral P2b structural renderer into 4 distinct **premium themes** with a bundled offline font set, so the Dark Premium × Before/After post matches the reference `go.png`, and the user can pick the theme and the headline font when creating a post.

**Architecture:** A single pure-data `themes.js` is the source of truth for theme tokens (background, per-role typography, card/badge/divider styling, accent). `composition.js` gains `applyTheme(comp, name)` that stamps a theme's per-element typography onto the editable spec (preserving text/photos/positions). `render.js` consumes the theme's non-per-element tokens (bg, card, badge, divider) and the per-element typography already on the elements — still **inline-styles only**. Fonts are base64-embedded as `@font-face` in `fonts.js`, injected into the editor document AND into the export SVG (the P2a spike's hard-won lesson: custom fonts only rasterize if their `@font-face` rules travel inside the `<foreignObject>`). The editor gains a theme picker and a headline-font picker.

**Tech Stack:** Pure-ESM JS modules under `static/post_studio/` (no bundler, no new deps); `node --test` for DOM-free modules; Playwright (already vendored) for DOM/visual/export tests; Python/pytest for the (unchanged) endpoints; in-repo TTF fonts base64-inlined.

## Global Constraints

Every task's requirements implicitly include this section. Values are binding — copy them verbatim.

- **No new dependencies.** No new pip/npm packages, no bundler, no CDN. Fonts come from the in-repo `fonts/` TTFs, base64-inlined. `node --test` (DOM-free) + Playwright (DOM/visual).
- **render.js stays INLINE STYLES ONLY.** Every visual property is an inline `style` attribute (or an inline `<svg>` element). Zero CSS classes, zero `<style>` blocks driving the stage. Theme tokens become inline styles at render time. (The export `<foreignObject>` cannot reach external CSS — classed/stylesheet-driven elements export UNSTYLED.)
- **Custom fonts MUST be embedded in the export SVG.** `rasterize.js` injects the `@font-face` rules (with base64 `src`) into the serialized `<foreignObject>` document. Relying on `document.fonts.ready` alone is NOT sufficient — a data:-URL SVG image does not inherit the host document's fonts. (P2a spike decision: `docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md`.)
- **Host-agnostic editor.** `editor.js` depends only on the composition/render/rasterize/themes/fonts modules and the `PostStudioHost` adapter — never on desktop-only globals except the existing `typeof`-guarded `window.showConfirm`/`window.showToast`. (The P6 mobile host must drop in unchanged.)
- **Curated font set = in-repo only (the user's choice):** `Manrope` (400/700/800), `Playfair Display` (700), `Cairo` (400/700 — Arabic). No fetched/expanded faces. The per-element font picker offers families: **Manrope (sans), Playfair (serif), Cairo (Arabic).**
- **Dark Premium default headline = Manrope ExtraBold (matches `go.png`), but user-switchable.** The user explicitly wants to choose the headline font when creating a post, so a fresh post seeds to the go.png look yet the editor exposes a headline-font picker.
- **Theme switch resets per-element typography to the theme defaults** (v1 behavior — text/photos/positions are preserved; font/size/weight/color are restyled). Document this; do not build override-preservation in P3.
- **Scope boundary:** P3 = theme tokens + fonts + theme/headline-font pickers. **NOT in P3** (these are P4): drag-positioning, snap guides, per-element size/weight/color inspector, add/remove/reorder phase UI, editable title/subline text fields, the exact go.png "pill label spanning two cards" layout. Restyling within the existing structural layout is P3; re-architecting the layout is P4.
- **EN/AR bilingual + RTL-sane** for all new editor controls (labels keyed off `<html lang>`, consistent with the existing `STR` map in `editor.js`).
- **Frozen-exe safe.** New modules live under `static/post_studio/` and are served by the existing `/post_studio/<file>` route + bundled via the existing `('static','static')` entry in `DentaCare.spec`. Fonts are base64-embedded in `fonts.js`, so the raw `fonts/` TTFs are build-time only (no runtime dependency on them).

---

## File Structure

- **Create** `tools/gen_post_studio_fonts.py` — one-shot generator: reads `fonts/*.ttf`, writes `static/post_studio/fonts.js`. Committed for reproducibility.
- **Create** `static/post_studio/fonts.js` — GENERATED. Exports `FONT_FACE_CSS` (base64 `@font-face` string), `FONT_OPTIONS` (pickable families), `ensureFontsLoaded(doc?)` (idempotent `<style>` injector).
- **Create** `static/post_studio/themes.js` — pure data. Exports `THEMES` (4 themes), `THEME_OPTIONS` (pickable list), `themeTokens(name)` (safe lookup, defaults to dark_premium).
- **Modify** `static/post_studio/composition.js` — add `applyTheme(comp, name)`; route `defaultComposition` through it; element factories use family names.
- **Modify** `static/post_studio/render.js` — consume theme tokens (bg/card/badge/divider), set `fontFamily` per element, add the tooth divider + `data-ps-headline` hook.
- **Modify** `static/post_studio/rasterize.js` — embed `FONT_FACE_CSS` into the export SVG.
- **Modify** `static/post_studio/editor.js` — `ensureFontsLoaded()` at mount; theme picker; headline-font picker; EN/AR labels.
- **Modify** `static/post_studio/spike/render_harness.html` — import + `ensureFontsLoaded`, add `bg`/`hasDivider` to `__describe`, add `__fontLoaded` hook.
- **Modify** `tests/js/composition.test.mjs` — add `applyTheme` tests.
- **Modify** `tests/e2e/test_editor_render.py` — theme background + divider + custom-font-load + export-still-untainted tests.
- **Modify** `tests/e2e/test_editor_flow.py` — theme switch + headline-font switch test.
- **Create** `tests/e2e/test_theme_visual.py` — per-theme screenshot smoke (human-review artifacts + invariants).

---

## Task 1: Curated offline font bundle (`fonts.js`)

**Files:**
- Create: `tools/gen_post_studio_fonts.py`
- Create (generated): `static/post_studio/fonts.js`
- Test: `tests/js/fonts.test.mjs`

**Interfaces:**
- Produces: `FONT_FACE_CSS: string`, `FONT_OPTIONS: Array<{id, label, label_ar, family}>`, `ensureFontsLoaded(doc=document): void`. Family CSS names: `'Manrope'`, `'Playfair Display'`, `'Cairo'`.
- Consumes: in-repo `fonts/Manrope-Regular.ttf`, `Manrope-Bold.ttf`, `Manrope-ExtraBold.ttf`, `PlayfairDisplay-Bold.ttf`, `Cairo-Regular.ttf`, `Cairo-Bold.ttf`.

- [ ] **Step 1: Write the generator** `tools/gen_post_studio_fonts.py`

```python
"""Generate static/post_studio/fonts.js from the in-repo TTFs (base64 @font-face).
Run once (and whenever the font files change): python tools/gen_post_studio_fonts.py
The generated fonts.js is committed; this script exists for reproducibility."""
import base64
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONTS = ROOT / "fonts"
OUT = ROOT / "static" / "post_studio" / "fonts.js"

# (css family, weight, filename)
FACES = [
    ("Manrope", 400, "Manrope-Regular.ttf"),
    ("Manrope", 700, "Manrope-Bold.ttf"),
    ("Manrope", 800, "Manrope-ExtraBold.ttf"),
    ("Playfair Display", 700, "PlayfairDisplay-Bold.ttf"),
    ("Cairo", 400, "Cairo-Regular.ttf"),
    ("Cairo", 700, "Cairo-Bold.ttf"),
]


def _face(family: str, weight: int, fname: str) -> str:
    b64 = base64.b64encode((FONTS / fname).read_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'%s';font-style:normal;font-weight:%d;"
        "font-display:swap;src:url(data:font/ttf;base64,%s) format('truetype');}"
        % (family, weight, b64)
    )


def main() -> None:
    css = "\n".join(_face(*f) for f in FACES)
    assert "`" not in css and "${" not in css, "css would break the JS template literal"
    js = (
        "// fonts.js — curated offline font bundle for Post Studio (base64 @font-face).\n"
        "// GENERATED by tools/gen_post_studio_fonts.py from fonts/*.ttf — do not hand-edit.\n"
        "export const FONT_FACE_CSS = `" + css + "`;\n\n"
        "export const FONT_OPTIONS = [\n"
        "  { id: 'manrope', label: 'Manrope', label_ar: 'مانروب', family: 'Manrope' },\n"
        "  { id: 'playfair', label: 'Playfair', label_ar: 'بلايفير', family: 'Playfair Display' },\n"
        "  { id: 'cairo', label: 'Cairo', label_ar: 'القاهرة', family: 'Cairo' },\n"
        "];\n\n"
        "let _injected = false;\n"
        "export function ensureFontsLoaded(doc = document) {\n"
        "  if (_injected || doc.getElementById('ps-font-faces')) { _injected = true; return; }\n"
        "  const style = doc.createElement('style');\n"
        "  style.id = 'ps-font-faces';\n"
        "  style.textContent = FONT_FACE_CSS;\n"
        "  (doc.head || doc.documentElement).appendChild(style);\n"
        "  _injected = true;\n"
        "}\n"
    )
    OUT.write_text(js, encoding="utf-8")
    print(f"wrote {OUT} ({len(js)} bytes, {len(FACES)} faces)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate `fonts.js`**

Run: `python tools/gen_post_studio_fonts.py`
Expected: prints `wrote .../static/post_studio/fonts.js (NNNN bytes, 6 faces)` (NNNN ≈ 300–340 KB). The file now exists.

- [ ] **Step 3: Verify it parses as ESM**

Run: `node --check static/post_studio/fonts.js`
Expected: no output, exit 0. (The `static/post_studio/package.json` `{"type":"module"}` marker lets node treat `.js` as ESM.)

- [ ] **Step 4: Write the failing test** `tests/js/fonts.test.mjs`

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FONT_FACE_CSS, FONT_OPTIONS, ensureFontsLoaded }
  from '../../static/post_studio/fonts.js';

test('FONT_FACE_CSS bundles all three families as base64 data URLs', () => {
  for (const fam of ['Manrope', 'Playfair Display', 'Cairo']) {
    assert.ok(FONT_FACE_CSS.includes(`font-family:'${fam}'`), `missing ${fam}`);
  }
  assert.ok(FONT_FACE_CSS.includes('url(data:font/ttf;base64,'), 'fonts not inlined');
  assert.ok(FONT_FACE_CSS.includes('font-weight:800'), 'Manrope ExtraBold missing');
});

test('FONT_OPTIONS exposes the curated families with required keys', () => {
  assert.ok(FONT_OPTIONS.length >= 3);
  const ids = FONT_OPTIONS.map((o) => o.id);
  assert.deepEqual(ids, ['manrope', 'playfair', 'cairo']);
  for (const o of FONT_OPTIONS) {
    for (const k of ['id', 'label', 'label_ar', 'family']) {
      assert.ok(o[k], `option ${o.id} missing ${k}`);
    }
  }
});

test('ensureFontsLoaded is DOM-only (callable with a fake doc, idempotent)', () => {
  let appended = 0;
  const fakeStyle = {};
  const fakeDoc = {
    _byId: {},
    getElementById(id) { return this._byId[id] || null; },
    createElement() { return fakeStyle; },
    head: { appendChild(node) { appended += 1; fakeDoc._byId['ps-font-faces'] = node; } },
  };
  ensureFontsLoaded(fakeDoc);
  ensureFontsLoaded(fakeDoc);     // second call must no-op
  assert.equal(appended, 1, 'must inject the <style> exactly once');
  assert.equal(fakeStyle.id, 'ps-font-faces');
  assert.equal(fakeStyle.textContent, FONT_FACE_CSS);
});
```

> Note: `ensureFontsLoaded` uses a module-level `_injected` latch. Because this test calls it twice in one process the latch alone would pass, but the `getElementById` guard is what makes it safe across editor remounts in a real document — the test exercises both by checking exactly one append.

- [ ] **Step 5: Run the test**

Run: `node --test tests/js/fonts.test.mjs`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/gen_post_studio_fonts.py static/post_studio/fonts.js tests/js/fonts.test.mjs
git commit -m "feat(post-studio): bundle curated offline fonts (Manrope/Playfair/Cairo) as base64 @font-face"
```

---

## Task 2: Theme tokens (`themes.js`)

**Files:**
- Create: `static/post_studio/themes.js`
- Test: `tests/js/themes.test.mjs`

**Interfaces:**
- Produces: `THEMES: Record<string, ThemeToken>`, `THEME_OPTIONS: Array<{id, label, label_ar}>`, `themeTokens(name): ThemeToken`.
- `ThemeToken` shape: `{ bg, headline, subline, label, doctor, card, badge, divider, accent }` where each of `headline|subline|label|doctor` is `{ font, size, weight, color, letterSpacing }`; `card` is `{ borderRadius:number, border, boxShadow, background }`; `badge` is `{ shape:'circle'|'square', background, color, border }`; `divider` is `{ enabled:boolean, color, icon:'tooth' }`.
- Consumes: nothing (pure data — the font family names must match Task 1's `FONT_OPTIONS[].family`).

- [ ] **Step 1: Write the failing test** `tests/js/themes.test.mjs`

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { THEMES, THEME_OPTIONS, themeTokens }
  from '../../static/post_studio/themes.js';

const NAMES = ['dark_premium', 'light_luxury', 'clinical_premium', 'bold_editorial'];

test('THEME_OPTIONS lists the four themes with bilingual labels', () => {
  assert.deepEqual(THEME_OPTIONS.map((o) => o.id), NAMES);
  for (const o of THEME_OPTIONS) {
    assert.ok(o.label && o.label_ar, `${o.id} needs label + label_ar`);
  }
});

test('every theme has the full token shape', () => {
  for (const name of NAMES) {
    const t = THEMES[name];
    assert.ok(t, `missing theme ${name}`);
    assert.ok(t.bg, `${name}.bg`);
    for (const role of ['headline', 'subline', 'label', 'doctor']) {
      const r = t[role];
      for (const k of ['font', 'size', 'weight', 'color', 'letterSpacing']) {
        assert.ok(r[k] !== undefined, `${name}.${role}.${k} missing`);
      }
    }
    assert.equal(typeof t.card.borderRadius, 'number');
    assert.ok(['circle', 'square'].includes(t.badge.shape));
    assert.equal(typeof t.divider.enabled, 'boolean');
    assert.ok(t.accent);
  }
});

test('dark_premium matches go.png: sans white headline, gold accents, tooth divider', () => {
  const t = THEMES.dark_premium;
  assert.equal(t.headline.font, 'Manrope');        // bold sans, per go.png
  assert.equal(t.headline.color, '#ffffff');
  assert.equal(t.subline.color, '#c9a86a');        // gold subline (go.png)
  assert.equal(t.doctor.color, '#c9a86a');
  assert.equal(t.divider.enabled, true);
  assert.equal(t.divider.icon, 'tooth');
  assert.ok(t.bg.includes('radial-gradient'));     // navy glow, not a flat fill
});

test('light_luxury uses a serif headline', () => {
  assert.equal(THEMES.light_luxury.headline.font, 'Playfair Display');
});

test('themeTokens falls back to dark_premium for unknown names', () => {
  assert.equal(themeTokens('nope'), THEMES.dark_premium);
  assert.equal(themeTokens('clinical_premium'), THEMES.clinical_premium);
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `node --test tests/js/themes.test.mjs`
Expected: FAIL — `Cannot find module '.../themes.js'`.

- [ ] **Step 3: Write `static/post_studio/themes.js`**

```javascript
// themes.js — pure theme tokens for Post Studio. Single source of truth for
// background + per-role typography + card/badge/divider styling. render.js reads
// bg/card/badge/divider; composition.applyTheme stamps the per-role typography
// onto elements. Font family names match fonts.js FONT_OPTIONS[].family.

export const THEME_OPTIONS = [
  { id: 'dark_premium', label: 'Dark Premium', label_ar: 'فاخر داكن' },
  { id: 'light_luxury', label: 'Light Luxury', label_ar: 'فاخر فاتح' },
  { id: 'clinical_premium', label: 'Clinical Premium', label_ar: 'طبي فاخر' },
  { id: 'bold_editorial', label: 'Bold Editorial', label_ar: 'جريء تحريري' },
];

export const THEMES = {
  // The reference (go.png): navy radial glow, white sans headline, gold subline +
  // doctor name, gold-bordered glowing cards, gold circle badges, tooth divider.
  dark_premium: {
    bg: 'radial-gradient(62% 52% at 50% 34%, #163a59 0%, #0c2336 52%, #060f1c 100%)',
    headline: { font: 'Manrope', size: 88, weight: 800, color: '#ffffff', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 52, weight: 700, color: '#c9a86a', letterSpacing: 0 },
    label: { font: 'Manrope', size: 30, weight: 600, color: '#cdd6e0', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 40, weight: 800, color: '#c9a86a', letterSpacing: 6 },
    card: {
      borderRadius: 28, border: '1px solid rgba(201,168,106,.55)',
      boxShadow: '0 0 42px rgba(40,90,120,.25) inset', background: 'rgba(255,255,255,.04)',
    },
    badge: { shape: 'circle', background: 'transparent', color: '#c9a86a', border: '2px solid #c9a86a' },
    divider: { enabled: true, color: '#c9a86a', icon: 'tooth' },
    accent: '#c9a86a',
  },
  // Warm cream, ink + gold, serif headline, soft-shadow white cards, thin gold badges.
  light_luxury: {
    bg: '#f6f1e7',
    headline: { font: 'Playfair Display', size: 84, weight: 700, color: '#2a2620', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 46, weight: 600, color: '#b08d3c', letterSpacing: 0 },
    label: { font: 'Manrope', size: 28, weight: 600, color: '#6b6256', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 36, weight: 700, color: '#b08d3c', letterSpacing: 5 },
    card: {
      borderRadius: 20, border: '1px solid rgba(0,0,0,.08)',
      boxShadow: '0 18px 40px rgba(0,0,0,.12)', background: '#ffffff',
    },
    badge: { shape: 'circle', background: 'transparent', color: '#b08d3c', border: '1px solid #b08d3c' },
    divider: { enabled: true, color: '#c2a25a', icon: 'tooth' },
    accent: '#b08d3c',
  },
  // Crisp white, DentaCare blue, airy bold sans, filled blue badges, clean cards.
  clinical_premium: {
    bg: '#ffffff',
    headline: { font: 'Manrope', size: 80, weight: 800, color: '#0f2a3f', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 46, weight: 600, color: '#0ea5e9', letterSpacing: 0 },
    label: { font: 'Manrope', size: 28, weight: 600, color: '#33506a', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 34, weight: 700, color: '#0ea5e9', letterSpacing: 4 },
    card: {
      borderRadius: 16, border: '1px solid #d7e3ee',
      boxShadow: '0 10px 28px rgba(14,165,233,.10)', background: '#f4f9fc',
    },
    badge: { shape: 'circle', background: '#0ea5e9', color: '#ffffff', border: 'none' },
    divider: { enabled: false, color: '#0ea5e9', icon: 'tooth' },
    accent: '#0ea5e9',
  },
  // High-contrast dark, oversized type, punchy accent, solid square badges, square cards.
  bold_editorial: {
    bg: '#121212',
    headline: { font: 'Manrope', size: 100, weight: 800, color: '#ffffff', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 52, weight: 700, color: '#ff5a3c', letterSpacing: 0 },
    label: { font: 'Manrope', size: 30, weight: 700, color: '#ffffff', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 38, weight: 800, color: '#ffffff', letterSpacing: 4 },
    card: {
      borderRadius: 4, border: '4px solid #ffffff',
      boxShadow: 'none', background: '#1f1f1f',
    },
    badge: { shape: 'square', background: '#ff5a3c', color: '#ffffff', border: 'none' },
    divider: { enabled: false, color: '#ff5a3c', icon: 'tooth' },
    accent: '#ff5a3c',
  },
};

export function themeTokens(name) {
  return THEMES[name] || THEMES.dark_premium;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/themes.test.mjs`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/themes.js tests/js/themes.test.mjs
git commit -m "feat(post-studio): themes.js — 4 premium theme tokens (dark/light/clinical/editorial)"
```

---

## Task 3: `applyTheme` in `composition.js`

**Files:**
- Modify: `static/post_studio/composition.js`
- Test: `tests/js/composition.test.mjs`

**Interfaces:**
- Produces: `applyTheme(comp, themeName): Composition` — a NEW comp with `theme` set and each element's typography stamped from the theme (text/photos/positions/badges/labels preserved). `defaultComposition(template, opts)` now applies `opts.theme || 'dark_premium'`.
- Consumes: `themeTokens` from `themes.js` (Task 2).

- [ ] **Step 1: Write the failing tests** — append to `tests/js/composition.test.mjs`

```javascript
import { applyTheme } from '../../static/post_studio/composition.js';

test('applyTheme stamps per-element typography from the theme, preserves content', () => {
  const c0 = defaultComposition('before_after', { doctorName: 'DR. X' });
  const c = applyTheme(c0, 'light_luxury');
  assert.equal(c.theme, 'light_luxury');
  const title = c.elements.find((e) => e.id === 'title');
  assert.equal(title.headline.font, 'Playfair Display');   // serif headline
  assert.equal(title.headline.text, 'Procedure Title');    // content preserved
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.equal(doctor.text, 'DR. X');                      // content preserved
  assert.equal(doctor.color, '#b08d3c');                  // restyled by theme
});

test('defaultComposition applies dark_premium (go.png) by default: Manrope sans headline', () => {
  const c = defaultComposition('before_after');
  assert.equal(c.theme, 'dark_premium');
  const title = c.elements.find((e) => e.id === 'title');
  assert.equal(title.headline.font, 'Manrope');
  assert.equal(title.headline.color, '#ffffff');
});

test('applyTheme preserves strip blocks (photos/badges/labels)', () => {
  let c = addBlock(defaultComposition('before_after'), 'Follow-up'); // 3 blocks
  c = applyTheme(c, 'clinical_premium');
  const s = c.elements.find((e) => e.id === 'strip');
  assert.deepEqual(s.blocks.map((b) => b.badge), [1, 2, 3]);
  assert.deepEqual(s.blocks.map((b) => b.label), ['Before Treatment', 'After Treatment', 'Follow-up']);
});

test('applyTheme does not mutate its input', () => {
  const c0 = defaultComposition('before_after');
  const before = JSON.stringify(c0);
  applyTheme(c0, 'bold_editorial');
  assert.equal(JSON.stringify(c0), before);
});
```

- [ ] **Step 2: Run to confirm failure**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `applyTheme` is not exported.

- [ ] **Step 3: Implement in `composition.js`**

Add the import at the top (after the header comment, before `MAX_BLOCKS`):

```javascript
import { themeTokens } from './themes.js';
```

Change the three element factories to use family names (so a pre-theme comp is still valid; `applyTheme` overwrites these anyway). In `titleElement()` change `font: 'playfair'` → `font: 'Playfair Display'` and `font: 'manrope'` → `font: 'Manrope'`. In `stripElement()` change `font: 'manrope'` → `font: 'Manrope'`. In `doctorElement()` change `font: 'manrope'` → `font: 'Manrope'`.

Add `applyTheme` (place it directly after `deserialize`):

```javascript
// Returns a NEW comp with `themeName` applied: each element's typography fields
// are set from the theme tokens; text, photos, positions, badges, labels are
// preserved. v1 behavior: switching themes resets per-element typography.
export function applyTheme(comp, themeName) {
  const t = themeTokens(themeName);
  const next = structuredClone(comp);
  next.theme = themeName;
  for (const el of next.elements) {
    if (el.type === 'title') {
      el.headline = { ...el.headline, ...t.headline };
      el.subline = { ...el.subline, ...t.subline };
    } else if (el.type === 'photoStrip') {
      el.labelStyle = { ...el.labelStyle, ...t.label };
    } else if (el.type === 'doctorName') {
      Object.assign(el, t.doctor);
    }
  }
  return next;
}
```

Route `defaultComposition` through it — replace the existing `return { ... }` body:

```javascript
export function defaultComposition(template, opts = {}) {
  const seed = SEEDS[template];
  if (!seed) throw new Error(`unknown template: ${template}`);
  const base = {
    version: 1,
    size: 'square',
    theme: DEFAULT_THEME,
    elements: [
      titleElement(),
      stripElement(seed.labels, seed.layout),
      doctorElement(opts.doctorName),
    ],
  };
  return applyTheme(base, opts.theme || DEFAULT_THEME);
}
```

- [ ] **Step 4: Run the full composition suite**

Run: `node --test tests/js/composition.test.mjs`
Expected: all tests pass (the pre-existing ones still hold — `applyTheme` changes typography only, not ids/blocks/badges/text).

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): composition.applyTheme — stamp theme typography onto the editable spec"
```

---

## Task 4: `render.js` consumes theme tokens (bg, cards, badges, divider, fonts)

**Files:**
- Modify: `static/post_studio/render.js`
- Modify: `static/post_studio/spike/render_harness.html`
- Test: `tests/e2e/test_editor_render.py`

**Interfaces:**
- Consumes: `themeTokens` from `themes.js`; reads `comp.theme` for bg/card/badge/divider and each element's (already-themed) typography for text.
- Produces: a stage whose background, card frames, badges, and (when `theme.divider.enabled`) a tooth divider reflect the theme; headline carries `data-ps-headline` for selection.

- [ ] **Step 1: Write the failing tests** — append to `tests/e2e/test_editor_render.py`

```python
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
```

> The existing `_COMP` carries explicit per-element typography but no `font` on the headline; render.js falls back to the theme's family, so the light_luxury assertion checks the theme-driven `fontFamily`. The badge-detection in `test_render_structure_before_after` still passes because dark_premium badges stay circular (`borderRadius:'50%'`).

- [ ] **Step 2: Update the harness** `static/post_studio/spike/render_harness.html`

In the `<script type="module">`, extend the imports and `__describe` (and load fonts so computed `fontFamily` resolves):

Change the import block to:
```javascript
  import { renderComposition } from '../render.js';
  import { rasterizeToPngBlob } from '../rasterize.js';
  import { ensureFontsLoaded } from '../fonts.js';
  ensureFontsLoaded();
```

Replace the `window.__describe` body's returned object with one that also reports background + divider:
```javascript
  window.__describe = function (comp) {
    const stage = window.__buildStage(comp) && window.__stage;
    return {
      size: [stage.offsetWidth, stage.offsetHeight],
      bg: stage.style.background || stage.style.backgroundImage || '',
      hasDivider: !!stage.querySelector('svg'),
      imgs: stage.querySelectorAll('img').length,
      badges: Array.from(stage.querySelectorAll('div'))
        .filter((d) => /^[0-9]+$/.test(d.textContent.trim()) && d.style.borderRadius === '50%')
        .map((d) => d.textContent.trim()),
      hasDoctor: stage.textContent.includes('DR.'),
    };
  };
```

- [ ] **Step 3: Run to confirm failure**

Run: `python -m pytest tests/e2e/test_editor_render.py -k "theme or headline_uses" -v`
Expected: FAIL (render.js doesn't yet apply theme bg/divider/font).

- [ ] **Step 4: Implement `render.js`**

Add the import after the header comment:
```javascript
import { themeTokens } from './themes.js';
```

Make `typoStyle` set the family:
```javascript
function typoStyle(t) {
  if (!t) return {};
  return {
    fontFamily: t.font ? `"${t.font}", system-ui, "Segoe UI", sans-serif` : 'inherit',
    color: t.color || '#ffffff',
    fontSize: px(t.size || 32),
    fontWeight: String(t.weight || 600),
    letterSpacing: px(t.letterSpacing || 0),
    lineHeight: '1.2',
    margin: '0',
  };
}
```

Add the tooth icon + divider builders (place above `buildTitle`):
```javascript
const SVG_NS = 'http://www.w3.org/2000/svg';
// Simple outlined tooth (refine glyph in QA if needed — exports as inline SVG).
const TOOTH_PATH =
  'M12 2.2c-1.7 0-2.6.9-4.4.9S4.6 2.2 3.4 4c-1.1 2.8-.2 6.7.8 10.6.5 2 .9 5.6 2.3 5.6 ' +
  '1.1 0 1.2-2.8 1.9-4.8.3-.9.8-1.4 1.6-1.4s1.3.5 1.6 1.4c.7 2 .8 4.8 1.9 4.8 1.4 0 ' +
  '1.8-3.6 2.3-5.6 1-3.9 1.9-7.8.8-10.6-1.2-1.8-2.4-.9-4.2-.9s-2.7-.9-4.4-.9z';

function toothIcon(color) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '46');
  svg.setAttribute('height', '46');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', TOOTH_PATH);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', color);
  path.setAttribute('stroke-width', '1.4');
  path.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(path);
  return svg;
}

function buildDivider(theme) {
  const row = document.createElement('div');
  setStyle(row, {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    gap: '20px', marginTop: '20px',
  });
  const rule = () => {
    const r = document.createElement('div');
    setStyle(r, { height: '1px', width: '130px', background: theme.divider.color, opacity: '.75' });
    return r;
  };
  row.appendChild(rule());
  row.appendChild(toothIcon(theme.divider.color));
  row.appendChild(rule());
  return row;
}
```

Update `buildTitle` to accept the theme and mark the headline + append the divider:
```javascript
function buildTitle(el, theme) {
  const box = document.createElement('div');
  setStyle(box, {
    position: 'absolute', left: '0', right: '0',
    top: `${(el.y ?? 0.10) * 100}%`, transform: 'translateY(-50%)',
    textAlign: el.align || 'center', padding: '0 6%', boxSizing: 'border-box',
  });
  const head = document.createElement('div');
  head.setAttribute('data-ps-headline', '');
  head.textContent = el.headline ? (el.headline.text || '') : '';
  setStyle(head, typoStyle({ ...theme.headline, ...el.headline }));
  const sub = document.createElement('div');
  sub.textContent = el.subline ? (el.subline.text || '') : '';
  setStyle(sub, typoStyle({ ...theme.subline, ...el.subline }));
  box.appendChild(head);
  box.appendChild(sub);
  if (theme.divider && theme.divider.enabled) box.appendChild(buildDivider(theme));
  return box;
}
```

Update `buildCard` to use theme card + badge tokens:
```javascript
function buildCard(b, el, theme) {
  const card = document.createElement('div');
  setStyle(card, {
    position: 'relative', flex: '1 1 0', display: 'flex',
    flexDirection: 'column', gap: '14px', alignItems: 'center', minWidth: '0',
  });
  const frame = document.createElement('div');
  setStyle(frame, {
    position: 'relative', width: '100%', aspectRatio: '1 / 1',
    borderRadius: px(theme.card.borderRadius), overflow: 'hidden',
    border: theme.card.border, boxShadow: theme.card.boxShadow,
    background: theme.card.background,
  });
  if (b.photo) {
    const img = document.createElement('img');
    img.src = b.photo;
    img.alt = '';
    setStyle(img, { width: '100%', height: '100%', objectFit: 'cover', display: 'block' });
    frame.appendChild(img);
  }
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
  const label = document.createElement('div');
  label.textContent = b.label || '';
  setStyle(label, { ...typoStyle({ ...theme.label, ...el.labelStyle }), textAlign: 'center' });
  card.appendChild(frame);
  card.appendChild(label);
  return card;
}
```

Update `buildStrip` to thread the theme:
```javascript
function buildStrip(el, theme) {
  const wrap = document.createElement('div');
  const blocks = el.blocks || [];
  const isGrid = el.layout === 'grid' || blocks.length > 3;
  setStyle(wrap, {
    position: 'absolute', left: '6%', right: '6%', top: '50%',
    transform: 'translateY(-50%)',
    display: isGrid ? 'grid' : 'flex',
    gridTemplateColumns: isGrid ? 'repeat(2, minmax(0, 1fr))' : '',
    gap: '32px', justifyItems: 'stretch', alignItems: 'stretch',
  });
  for (const b of blocks) wrap.appendChild(buildCard(b, el, theme));
  return wrap;
}
```

Update `renderComposition` to resolve the theme and pass it down:
```javascript
export function renderComposition(comp) {
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
    if (el.type === 'title') stage.appendChild(buildTitle(el, theme));
    else if (el.type === 'photoStrip') stage.appendChild(buildStrip(el, theme));
    else if (el.type === 'doctorName') stage.appendChild(buildDoctor(el, theme));
  }
  return stage;
}
```

Update `buildDoctor` to resolve its typography over the theme defaults (so a raw, un-themed comp still renders with the theme font — element values override):
```javascript
function buildDoctor(el, theme) {
  const t = { ...theme.doctor, ...el };   // theme defaults; element values override
  const box = document.createElement('div');
  box.textContent = el.text || '';
  setStyle(box, {
    position: 'absolute', left: '0', right: '0',
    top: `${(el.y ?? 0.93) * 100}%`, transform: 'translateY(-50%)',
    textAlign: el.align || 'center', textTransform: 'uppercase',
    fontFamily: t.font ? `"${t.font}", system-ui, "Segoe UI", sans-serif` : 'inherit',
    color: t.color || '#c9a86a',
    fontSize: px(t.size || 34),
    fontWeight: String(t.weight || 700),
    letterSpacing: px(t.letterSpacing || 4),
  });
  return box;
}
```

Delete the now-unused `THEME_BG` constant (themes.js owns backgrounds).

> **Typography resolution model (important):** for per-element TEXT, render.js merges `{ ...theme.<role>, ...element }` so the theme supplies defaults and any explicit element value wins. This is the SAME `themeTokens` source `applyTheme` uses, so there is no drift: in the normal flow `applyTheme` has already copied the theme values onto the element (the merge is a no-op); for a raw comp that only set `theme` (the render tests' `_COMP`), the theme still drives the fonts. bg/card/badge/divider come straight from `themeTokens(comp.theme)` (they are not per-element).

- [ ] **Step 5: Run the render tests**

Run: `python -m pytest tests/e2e/test_editor_render.py -v`
Expected: all tests pass (the 3 pre-existing + the 2 new). `node --check static/post_studio/render.js` exits 0.

- [ ] **Step 6: Commit**

```bash
git add static/post_studio/render.js static/post_studio/spike/render_harness.html tests/e2e/test_editor_render.py
git commit -m "feat(post-studio): render.js applies theme tokens — bg, cards, badges, tooth divider, fonts"
```

---

## Task 5: `rasterize.js` embeds `@font-face` into the export SVG

**Files:**
- Modify: `static/post_studio/rasterize.js`
- Modify: `static/post_studio/spike/render_harness.html`
- Test: `tests/e2e/test_editor_render.py`

**Interfaces:**
- Consumes: `FONT_FACE_CSS` from `fonts.js` (Task 1).
- Produces: `rasterizeToPngBlob` unchanged signature, but the serialized `<foreignObject>` now contains a `<style>` with the base64 `@font-face` rules so custom fonts rasterize.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_render.py`

```python
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
```

- [ ] **Step 2: Add the `__fontLoaded` hook to the harness** `static/post_studio/spike/render_harness.html`

After `ensureFontsLoaded();` (added in Task 4), add a hook just before `window.__harnessReady = true;`:
```javascript
  window.__fontLoaded = function (spec) {
    return !!(document.fonts && document.fonts.check(spec));
  };
```

> `document.fonts.check` returns true only once the face is loaded/usable. Because `ensureFontsLoaded()` injects the base64 `@font-face` and the browser eagerly loads `font-display:swap` faces, this resolves true shortly after navigation; the test reads it after `__harnessReady`.

- [ ] **Step 3: Run to confirm the export test passes for the document, then implement the embed**

Run: `python -m pytest tests/e2e/test_editor_render.py::test_custom_fonts_available_and_export_still_untainted -v`
Expected at this point: the font-load asserts may pass (harness injects fonts), but the test's intent — fonts inside the **export** — is only guaranteed once Step 4 lands. Proceed to implement.

- [ ] **Step 4: Implement the embed in `rasterize.js`**

Add the import after the header comment:
```javascript
import { FONT_FACE_CSS } from './fonts.js';
```

In `rasterizeToPngBlob`, after `const xhtml = new XMLSerializer().serializeToString(node);`, build a style tag and inject it inside the foreignObject `<div>`:
```javascript
  // Custom fonts only rasterize if their @font-face rules (with base64 src) live
  // INSIDE the foreignObject — a data:-URL SVG image does not inherit page fonts.
  const fontStyle = '<style>' + FONT_FACE_CSS + '</style>';
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' +
      '<foreignObject x="0" y="0" width="100%" height="100%">' +
        '<div xmlns="http://www.w3.org/1999/xhtml">' + fontStyle + xhtml + '</div>' +
      '</foreignObject>' +
    '</svg>';
```

(Delete the previous `const svg = ...` that lacked the font style.)

- [ ] **Step 5: Run the full render suite**

Run: `python -m pytest tests/e2e/test_editor_render.py -v`
Expected: all pass (the original untainted-export test still passes — the PNG is larger but well over 20 KB). `node --check static/post_studio/rasterize.js` exits 0.

- [ ] **Step 6: Commit**

```bash
git add static/post_studio/rasterize.js static/post_studio/spike/render_harness.html tests/e2e/test_editor_render.py
git commit -m "fix(post-studio): embed @font-face in export SVG so custom fonts rasterize (P2a spike lesson)"
```

---

## Task 6: Editor theme picker + headline-font picker

**Files:**
- Modify: `static/post_studio/editor.js`
- Test: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `applyTheme` from `composition.js`; `THEME_OPTIONS` from `themes.js`; `FONT_OPTIONS`, `ensureFontsLoaded` from `fonts.js`.
- Produces: editor controls `[data-ps-theme='<id>']` (theme buttons) and `[data-ps-fontopt='<id>']` (headline-font buttons); fonts injected at mount so the preview renders them.

- [ ] **Step 1: Write the failing test** — append to `tests/e2e/test_editor_flow.py`

```python
def test_editor_theme_and_headline_font_switch():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        # default theme is dark_premium -> radial-gradient background
        bg0 = page.evaluate(
            "() => getComputedStyle(document.querySelector('[data-ps-stage]')).backgroundImage"
        )
        assert "gradient" in bg0
        # switch to light_luxury -> solid cream background (no gradient image)
        page.click("[data-ps-theme='light_luxury']")
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('[data-ps-stage]'))"
            ".backgroundImage === 'none'"
        )
        # pick Playfair for the headline -> headline font-family updates
        page.click("[data-ps-fontopt='playfair']")
        page.wait_for_function(
            "() => /Playfair Display/.test("
            "getComputedStyle(document.querySelector('[data-ps-headline]')).fontFamily)"
        )
        browser.close()
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/e2e/test_editor_flow.py::test_editor_theme_and_headline_font_switch -v`
Expected: FAIL — no `[data-ps-theme]` controls.

- [ ] **Step 3: Implement in `editor.js`**

Extend the imports:
```javascript
import { TEMPLATES, defaultComposition, serialize, deserialize, applyTheme } from './composition.js';
import { renderComposition, EXPORT_PX } from './render.js';
import { rasterizeToPngBlob } from './rasterize.js';
import { THEME_OPTIONS } from './themes.js';
import { FONT_OPTIONS, ensureFontsLoaded } from './fonts.js';
```

Add the two new label keys to both `STR.en` and `STR.ar` (place beside the existing keys):
- en: `theme: 'Theme', headline_font: 'Headline font',`
- ar: `theme: 'القالب اللوني', headline_font: 'خط العنوان',`

At the very top of `mountEditor` (before building DOM), inject the fonts so the preview renders them:
```javascript
  ensureFontsLoaded();
```

In the controls column, after the existing `tplGroup` (template buttons) and before `addBtn`, add a theme group and a headline-font group:

```javascript
  // ── Theme picker ──
  const themeGroup = el('div', {});
  themeGroup.appendChild(el('label', { text: s.theme }, { display: 'block', marginBottom: '6px', fontWeight: '600' }));
  const themeRow = el('div', {}, { display: 'flex', flexWrap: 'wrap', gap: '8px' });
  for (const opt of THEME_OPTIONS) {
    const b = el('button', { type: 'button', 'data-ps-theme': opt.id,
      text: lang === 'ar' ? opt.label_ar : opt.label }, {});
    b.className = 'btn';
    b.addEventListener('click', () => { state.comp = applyTheme(state.comp, opt.id); renderPreview(); });
    themeRow.appendChild(b);
  }
  themeGroup.appendChild(themeRow);

  // ── Headline font picker (the element the user chooses at creation) ──
  const fontGroup = el('div', {});
  fontGroup.appendChild(el('label', { text: s.headline_font }, { display: 'block', marginBottom: '6px', fontWeight: '600' }));
  const fontRow = el('div', {}, { display: 'flex', flexWrap: 'wrap', gap: '8px' });
  for (const opt of FONT_OPTIONS) {
    const b = el('button', { type: 'button', 'data-ps-fontopt': opt.id,
      text: lang === 'ar' ? opt.label_ar : opt.label }, {});
    b.className = 'btn';
    b.addEventListener('click', () => { setHeadlineFont(opt.family); });
    fontRow.appendChild(b);
  }
  fontGroup.appendChild(fontRow);
```

Append them to `controls` (between `tplGroup` and `addBtn`):
```javascript
  controls.appendChild(tplGroup);
  controls.appendChild(themeGroup);
  controls.appendChild(fontGroup);
  controls.appendChild(addBtn);
  controls.appendChild(actions);
```
(Replace the existing three `controls.appendChild(...)` lines with the five above.)

Add a `setHeadlineFont` helper (place beside `onAddPhotos`), immutably updating the title element's headline font:
```javascript
  function setHeadlineFont(family) {
    const next = structuredClone(state.comp);
    const title = next.elements.find((e) => e.id === 'title');
    if (title && title.headline) title.headline = { ...title.headline, font: family };
    state.comp = next;
    renderPreview();
  }
```

- [ ] **Step 4: Run the editor flow suite**

Run: `python -m pytest tests/e2e/test_editor_flow.py -v`
Expected: both tests pass (the original template→add→save→reopen, plus the new theme/font switch). `node --check static/post_studio/editor.js` exits 0.

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/editor.js tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): editor theme picker + headline-font picker (EN/AR), inject fonts at mount"
```

---

## Task 7: Per-theme visual smoke + phase gate

**Files:**
- Create: `tests/e2e/test_theme_visual.py`

**Interfaces:**
- Consumes: the render harness; produces screenshots for human review + asserts cross-theme invariants.

- [ ] **Step 1: Write the visual smoke** `tests/e2e/test_theme_visual.py`

```python
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
            {"id": "title", "type": "title", "x": 0.5, "y": 0.12, "align": "center",
             "headline": {"text": headline, "size": 84, "weight": 800, "color": "#fff", "letterSpacing": 0},
             "subline": {"text": subline, "size": 48, "weight": 700, "color": "#c9a86a", "letterSpacing": 0}},
            {"id": "strip", "type": "photoStrip", "layout": "row",
             "blocks": [{"photo": _DATA_PNG, "badge": 1, "label": "Before Treatment"},
                        {"photo": _DATA_PNG, "badge": 2, "label": "After Treatment"}],
             "labelStyle": {"size": 28, "weight": 600, "color": "#cfd8e3"}},
            {"id": "doctor", "type": "doctorName", "x": 0.5, "y": 0.93, "align": "center",
             "text": doctor, "size": 36, "weight": 800, "color": "#c9a86a", "letterSpacing": 6},
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
        for theme in THEMES:
            info = page.evaluate("(c) => window.__describe(c)", _comp(theme))
            backgrounds[theme] = info["bg"]
            assert info["imgs"] == 2, f"{theme}: expected 2 photos"
            assert info["hasDoctor"] is True, f"{theme}: doctor name missing"
            # screenshot the native-size stage element for human fidelity review
            page.locator("[data-ps-stage]").screenshot(path=str(_ARTIFACTS / f"theme_{theme}.png"))
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
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/e2e/test_theme_visual.py -v`
Expected: PASS; `tests/e2e/_artifacts/theme_*.png` written (5 screenshots: 4 themes + 1 Arabic) for human fidelity review.

- [ ] **Step 3: Gitignore the artifacts (don't commit screenshots)**

Append to `.gitignore` (create the entry if missing):
```
tests/e2e/_artifacts/
```

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_theme_visual.py .gitignore
git commit -m "test(post-studio): per-theme visual smoke + screenshot artifacts (EN/AR)"
```

- [ ] **Step 5: Phase gate (controller-inline — no subagent)**

Run all gates and confirm green:
```bash
node --test tests/js/                      # composition + host + fonts + themes
node --check static/post_studio/fonts.js
node --check static/post_studio/themes.js
node --check static/post_studio/composition.js
node --check static/post_studio/render.js
node --check static/post_studio/rasterize.js
node --check static/post_studio/editor.js
node --check static/post_studio/host.js
python -m pytest tests/test_post_studio_ui.py tests/test_post_studio_api.py tests/e2e/ -q
```
Expected: node --test all green; every `node --check` exit 0; pytest exit 0 (Post Studio deliverables pass; the full-portal smoke skips). Then run the **full** suite once (`python -m pytest tests/ -q`, allow a long timeout for the Chromium e2e tests) and confirm exit 0 with no new failures.

> Frozen-exe note: `fonts.js`, `themes.js`, and the rest live under `static/post_studio/`, already served by the `/post_studio/<file>` route and bundled by the existing `('static','static')` entry in `DentaCare.spec` — no spec change needed. The raw `fonts/` TTFs are build-time only (base64 is embedded in `fonts.js`). Record this in the ledger; no exe rebuild is required to validate P3 (it's validated by tests), but the user-side exe rebuild remains an open item for the eventual single PR.

---

## Self-Review (planner checklist — completed)

**Spec coverage:** P3 spec line = "the 4 themes + 4 templates, matching the reference; finalize the bundled font set." → 4 themes (Task 2), font set finalized + bundled (Task 1), reference match for Dark Premium (Tasks 2+4, validated in Task 7 screenshots). The 4 templates already exist (P2a `composition.js` SEEDS); P3 themes them via `applyTheme`. Per-element font choice (the user's explicit ask) → headline-font picker (Task 6).

**Placeholder scan:** every code step contains complete code; the tooth SVG path is a real (refine-able) path, flagged for QA polish, not a placeholder.

**Type/name consistency:** family names (`'Manrope'`, `'Playfair Display'`, `'Cairo'`) are identical across `fonts.js` `FONT_OPTIONS[].family`, `themes.js` role tokens, and `composition.js` factories. `applyTheme` is exported from `composition.js` and imported by `editor.js`. `themeTokens` is imported by both `composition.js` and `render.js`. Data hooks (`data-ps-theme`, `data-ps-fontopt`, `data-ps-headline`, `data-ps-stage`) are consistent between render/editor and their tests. `__describe` returns `bg`/`hasDivider`; `__fontLoaded` added to the harness — both consumed by the render tests.

**Scope discipline:** drag/snap/per-element inspector/phase-UI/exact-pill-layout explicitly deferred to P4 in Global Constraints; theme switch resets typography (v1) is documented, not worked around.
