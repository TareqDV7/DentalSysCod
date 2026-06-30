# Post Studio — P4a: Content Editing (Design Spec)

**Date:** 2026-06-30
**Branch:** `feat/post-studio`
**Phase:** P4a (first of two slices splitting the original "P4 deep customize")
**Status:** Approved design — ready for implementation plan.

## Context

The Post Studio redesign replaced the retired server-side Pillow renderer with a
client-side WYSIWYG editor (P2b) and a premium theme system (P3 + the navy_gold
exact-fidelity pass). The editor as shipped can pick a template, pick a theme,
pick a global headline font, add photos, and save — but it **cannot change any
text**. Every saved post still reads "Root Canal Treatment / for Lower Molar /
DR. WASFY BARZAQ" from the template defaults. The block add/remove/reorder logic
exists in `composition.js` but is wired to no UI. Element positioning is fixed
(text gets a vertical-only fractional `y` + `align`; the photo strip is hardcoded
to vertical-center with 6% margins) — there is no `x`, no drag, no free layout.

The original "P4 deep customize" bundles two fairly independent capability
clusters. Per the sequencing decision (2026-06-30), they are split:

- **P4a (this spec) — Content editing:** type your own copy, per-element
  typography (guardrailed), photo-block management. The table-stakes layer — a
  designer that cannot change text is not usable.
- **P4b (next slice) — Free drag-layout:** an absolute coordinate model, drag-to
  -position, snapping, the double-span 516px pill, and the navy_gold exact pixel
  positions. Builds on the selection mechanism P4a introduces.

## Goal

Turn the editor into a real content editor — type your own headline / subline /
labels / doctor name, adjust per-element typography within curated guardrails,
and manage photo blocks (add / remove / replace / reorder-by-arrows) — via a
**select-then-inspect** side panel. Also land the P2b-carried live EN/AR
re-render hook.

## Decisions (all user-approved in brainstorming, 2026-06-30)

1. **Split P4 → P4a content first, P4b free drag-layout next.**
2. **Edit model = select + side-panel inspector.** Click an element on the
   canvas to select it (outline highlight); the left panel becomes a contextual
   inspector for that element. Click empty canvas to deselect. This is the
   standard design-tool model and gives P4b's drag a selection to build on.
3. **Typography controls = curated + custom (guardrailed).** Text field, font
   picker (reuses `FONT_OPTIONS`), size slider clamped to a sane range, weight
   dropdown limited to the font's real weights, color = theme-palette swatches +
   optional custom hex. Keeps posts on-brand per the anti-template design rules
   while staying flexible.
4. **Photo blocks = inspector + arrow-reorder.** Click a block → block inspector
   (edit label with the curated text controls, Replace photo, Remove, Move ◄/►).
   Global `+ Add block` (cap 6). Badges auto-renumber. Drag-to-reorder is
   deferred to P4b with the rest of dragging.

## Architecture

- **Selection is editor-only state, never serialized.** `state.selectedId` and
  `state.selectedBlockIndex` live in `editor.js`. They never enter
  `template_json` — the saved/exported composition must stay clean.
- **`render.js` gains element-identity hooks.** The independently selectable text
  runs each get their own `data-ps-el`: the headline (`title.headline`), the
  subline (`title.subline`), and the doctor name (`doctor`) — the `title` element
  is a positioning container for the headline+subline pair, but for *content*
  editing each run is selected and styled on its own (they already carry separate
  theme typography roles). Each photo block root gets `data-ps-block="<index>"`;
  a block's label is edited *inside the block inspector*, not selected separately.
  These are inert `data-*` attributes — no className, no style, no visual effect,
  no external reference. The INLINE-STYLES-ONLY invariant and the untainted-PNG
  export invariant are both fully preserved: `data-*` attributes do not render
  and cannot taint a canvas, and the export path already re-renders a fresh,
  selection-free stage from `state.comp`. (In P4a the headline and subline keep
  their shared container position — one fractional `y`; independent positioning
  is P4b.)
- **The selection outline is applied post-render to the on-screen stage only.**
  `exportBlob()` calls `renderComposition(state.comp)` to build its own stage with
  no selection, so no outline or selection artifact ever reaches a PNG.

## Files

- **`static/post_studio/inspector.js` (NEW)** — pure builders for the text
  inspector and block inspector, plus the curated config (size clamp range,
  weight options, palette resolution). Keeps `editor.js` under the file-size
  limit (many-small-files discipline).
- **`static/post_studio/composition.js`** — new immutable helpers, each returning
  a fresh composition via `structuredClone`, never mutating input:
  - `setText(comp, ref, value)` — set a text run's content. `ref` addresses a run:
    `title.headline`, `title.subline`, or `doctor` (block labels use
    `setBlockLabel`). Implementation pins the exact addressing scheme.
  - `setTypography(comp, ref, patch)` — merge `{ font?, size?, weight?, color? }`
    overrides onto the run named by `ref`, with size clamped (illustrative range
    ~16–160px; the plan pins the exact bounds) and custom hex validated.
  - `setBlockLabel(comp, index, value)`
  - `setBlockPhoto(comp, index, photo)` — the carried immutable photo setter
    (replaces the P2b in-place `block.photo` mutation).
  - Reuses the existing add / remove / move block ops + badge renumber (cap 6).
- **`static/post_studio/themes.js`** — `themePalette(themeId)` returning named
  swatches derived from the theme's own tokens (navy_gold → gold `#C6A274`,
  white `#F5F5F0`, navy `#08162C`, muted `#D2D7E1`).
- **`static/post_studio/render.js`** — add the two `data-*` identity hooks;
  otherwise untouched (still pure, inline-styles-only).
- **`static/post_studio/editor.js`** — selection state, click-to-select via event
  delegation on the stage, contextual panel switching, persistent global bar
  (template / theme / size / language) + actions (add / save / download), and the
  EN/AR re-render hook. **The P3 global headline-font picker is removed** —
  per-element font now lives in the inspector (one source of truth: select the
  title → pick its font).

## Layout & data flow

Left column, top → bottom:

1. **Global bar (always visible):** template picker, theme picker, post size,
   language toggle.
2. **Contextual inspector (middle):** text inspector, block inspector, or a
   "Select an element to edit" hint when nothing is selected.
3. **Actions (always visible):** add photos / add block, Save, Download.

Flow:

1. `mountEditor` builds global bar + empty inspector + actions + preview.
2. `renderPreview()` renders the stage from `state.comp`, then (editor-only)
   attaches a delegated click handler: a click on `[data-ps-el]` / `[data-ps-block]`
   sets the selection, re-renders, rebuilds the inspector, and draws the outline.
3. An inspector control fires → calls the matching immutable `composition` helper
   → `state.comp = next` → `renderPreview()` (selection preserved) → inspector
   reflects the new values.

## Inspector spec

- **Text run** (headline, subline, doctor — block labels use the same controls
  inside the block inspector): text field · font (`FONT_OPTIONS`) · size slider
  (clamped) · weight dropdown (font's real weights) · color (theme-palette
  swatches + optional validated custom hex).
- **Photo block:** label (curated text controls) · Replace photo (reuses
  `host.pickPhotos` + the existing staging validation) · Remove (disabled when
  only 1 block remains) · Move ◄/► (disabled at the ends) · strip toolbar
  `+ Add block` (cap 6) · badges auto-renumber on any add/remove/move.

## Error handling

- Photo add/replace reuse the existing staging upload + validation; failures
  surface via the existing toast (`notify`).
- Custom hex is validated (`/^#[0-9a-fA-F]{6}$/`); invalid input is ignored.
- Size is clamped to the configured range before apply.
- Remove is disabled below the 1-block minimum; reorder arrows are disabled at
  the ends.

## Testing (TDD)

- **`composition.test.mjs`** (node --test, DOM-free): the new helpers return a new
  composition, never mutate the input, and clamp / validate / renumber correctly.
- **`themes.test.mjs`**: `themePalette(themeId)` returns the expected named swatches
  for each theme.
- **e2e (Playwright)** — a new editor harness mounting `mountEditor` with a fake
  host (injects test photos, no network): click → inspector appears with the
  element's fields; edit text → stage updates; change size / weight / color →
  stage reflects and respects the clamp; select block → edit label, Replace,
  Move ◄/►, Add / Remove, badges renumber; **export after edits is still
  untainted (PNG produced)**; EN/AR toggle re-renders.

## Non-goals (YAGNI — deferred to P4b or later)

- Free dragging, `x` positioning, exact navy_gold pixel placement (panels y=360,
  pills y=708), the double-span 516px pill — all P4b.
- Block drag-reorder (arrows only in P4a).
- No new runtime dependencies. INLINE-STYLES-ONLY and the @font-face-embedded-in
  -export-SVG invariants are preserved. **PR remains HELD** — stack P4a–P6 on
  `feat/post-studio`; one PR only once the editor is the full premium designer
  replacing Pillow. Do not open a PR or push to origin unprompted.
