# Post Studio — P4b-2: Shape & Per-Element Style (Design Spec)

**Date:** 2026-07-04
**Branch:** `feat/post-studio`
**Phase:** P4b-2 (second of two slices splitting the original "P4b free drag-layout")
**Status:** Approved design — ready for implementation plan.

## Context

P4b-1 shipped the absolute coordinate model: every element (title, doctor, each
panel, each pill) is independently draggable, with smart guides/snap and
keyboard nudge, and `dark_premium`'s layout tokens reproduce the `go.png`
flagship's exact geometry. But three things from the original "P4b free
drag-layout" scope were explicitly deferred to this slice (see the P4b-1 spec's
`## Non-goals`, `docs/superpowers/specs/2026-07-01-post-studio-p4b1-layout-fidelity.md`):

1. **Resize handles for panels.** Panel size (`strip.panelW`/`panelH`) is
   currently *shared* across every block in a strip — set once by `seedLayout`,
   applied uniformly. There is no way to make one panel bigger than another,
   and no drag-to-resize affordance at all.
2. **A pill-width editing UI.** P4b-1 added the `pill.width: 'single' | 'double'`
   data field and render support (a double pill is `2×panelW + gap` wide,
   reaching into the next block's slot) so the `go.png` flagship could ship
   pixel-exact — but there is no UI to toggle it, and nothing suppresses the
   *next* block's own pill, which still renders in the same space.
3. **Per-block label typography.** P4a's block inspector edits `strip.labelStyle`
   — ONE typography style (font/size/weight/color) shared by every label in the
   strip. There's no way to make one block's label bigger, bolder, or a
   different color than the rest.

## Goal

Let every panel be independently resized (not just repositioned), let a pill's
single/double width be toggled from the inspector (with its covered neighbor
handled automatically), and let each block's label carry its own typography.

## Decisions (all user-approved 2026-07-04)

1. **Per-panel independent resize.** `panelW`/`panelH` move from shared
   `strip`-level fields to per-block fields (`blocks[i].panelW`/`panelH`).
   Resizing one panel does not affect any other panel. This matches the P4b-1
   precedent — every element already drags independently; size becomes
   independent too.
2. **4 corner resize handles, free aspect.** Selecting a panel shows 4 small
   corner squares (editor-only chrome, like the P4a/P4b-1 selection outline).
   Dragging any corner resizes width+height from that corner; the opposite
   corner's on-canvas position stays fixed (so top-left-corner drags also
   update `panelPos`). No aspect-ratio lock — panels already render photos
   with `object-fit: cover`, so any width/height just recrops the visible
   photo, consistent with how real design tools behave by default.
3. **Freeform resize, clamp only — no snap-while-resizing.** Resize is not
   snapped to guides this slice (drag-move already snaps; that's enough to
   align a panel after resizing). Width/height are clamped to a sane range so
   a panel can't shrink to invisible or blow past the canvas (exact numbers
   below). Snap-while-resizing is a possible future polish pass, not required
   here.
4. **Pill width: single toggle button, auto-hides the covered neighbor.** The
   block inspector gets one "Double width" toggle. Turning it on sets
   `block.pill.width = 'double'`; turning it off reverts to `'single'`. The
   toggle is disabled on the *last* block (nothing to cover). Whether the next
   block's own pill renders is a **computed** render-time check
   (`blocks[i-1]?.pill?.width === 'double'` → block `i`'s pill is skipped),
   not a stored flag — so toggling double on/off is fully reversible with no
   extra state to keep in sync or migrate.
5. **Double-pill width reaches the covered panel's actual right edge**, not a
   fixed `2×ownPanelW+gap` formula. Since panels can now differ in size
   (decision 1), the old P4b-1 formula (which assumed uniform panel width)
   would visually undershoot or overshoot once panels are resized
   independently. The double pill's width is computed from geometry:
   `(nextBlock.panelPos.x + nextBlock.panelW) − ownBlock.pillPos.x`.
6. **Per-block label typography, seeded from the old shared style, no
   bulk-apply UI.** `strip.labelStyle` (shared) becomes `blocks[i].labelStyle`
   (per-block). Existing/legacy posts get every block seeded with a *copy* of
   the old shared style on load, so nothing visually changes until the user
   edits one block. Selecting a block's typography controls (already built in
   `inspector.js` from P4a) edits only that block. No "apply to all" button —
   YAGNI; can be added later if users actually ask for it.

## Architecture

### Data model changes (`composition.js`)

- `blocks[i].panelW`, `blocks[i].panelH` — fractional (of canvas width/height
  respectively), replacing the shared `strip.panelW`/`panelH` as the
  **rendered** size. `strip.panelW`/`panelH` are **kept** as the *template
  default* — the size a newly-`addBlock`-ed block starts at — but are no
  longer read by `render.js` for existing blocks.
- `blocks[i].labelStyle` — `{font, size, weight, color}`, replacing the shared
  `strip.labelStyle` as the **rendered** typography for that block's label.
  `strip.labelStyle` is dropped entirely once every block carries its own (no
  reason to keep a shared default once per-block seeding covers it — new
  blocks seed from the theme's label token directly, same as today's initial
  seed source).
- `seedLayout(comp)` extended: alongside `panelPos`/`pillPos`, stamps each
  block's `panelW`/`panelH` (from the theme's layout tokens — same numbers
  P4b-1 already computes, just written per-block instead of once) and
  `labelStyle` (from `themeTokens(theme).label`). `hasLayout` is extended to
  also check the first block has `panelW` and `labelStyle` (a comp seeded
  pre-P4b-2 is *not* considered fully seeded) so `ensureLayout` correctly
  migrates P4b-1-era saved posts on `deserialize`.
  **`applyTheme`'s existing photoStrip branch changes**: today it writes
  `el.labelStyle = {...el.labelStyle, ...t.label}` (the shared field); since
  that field goes away, this branch is removed from `applyTheme` and
  per-block `labelStyle` stamping happens exclusively in `seedLayout` (which
  `applyTheme` already calls last) — one source of truth instead of two
  writers touching label typography.
- **New immutable helper:** `setSize(comp, blockIndex, {w, h})` — mirrors
  `setPosition`'s shape (`structuredClone`, clamp, return new comp) but is a
  dedicated function rather than extending the `ref` string scheme, because
  panels are the *only* resizable target this slice (YAGNI: no generic
  `ref`-parsing layer for one case). Clamp range: width
  `[40/1080, 1 − 2·margin]` (fractional of canvas width, `margin` from the
  active theme's `themeLayout`), height `[40/1080, 0.9]` (fractional of canvas
  height). Throws on an out-of-range block index.
- **New immutable helper:** `setPillWidth(comp, blockIndex, 'single'|'double')`
  — clones, writes `blocks[i].pill = {width}`, throws on an out-of-range index
  or invalid width value. (`setBlockLabel`/`setTypography` already exist from
  P4a/P4b-1 for label text/typography — `setTypography(comp, 'strip.label', …)`
  is retargeted to accept a block-scoped ref; see below.)
- **`setTypography` ref scheme extended:** P4a's `setTypography(comp, ref, patch)`
  currently accepts `'title.headline' | 'title.subline' | 'doctor' | 'strip.label'`
  (the last being the shared label style). `'strip.label'` is replaced with
  `'block:N.label'`, addressing one block's `labelStyle` — consistent with the
  existing `'block:N'` selection-ref family used elsewhere in the editor.

### Render changes (`render.js`)

- `buildPanel` reads `b.panelW`/`b.panelH` (per-block) instead of
  `el.panelW`/`el.panelH` (shared).
- `buildPill`'s single-width case reads `b.panelW` (its own block's width).
  The double-width case computes the geometry formula from decision 5 (needs
  the next block's `panelPos`/`panelW`, passed down from `buildStrip`, which
  already iterates `el.blocks` with the index available).
- `buildStrip` skips appending block `i`'s pill when
  `el.blocks[i-1]?.pill?.width === 'double'`.
- `buildPanel`'s label (non-pill themes) reads `b.labelStyle` instead of
  `el.labelStyle`; `buildPill`'s text likewise reads `b.labelStyle`.

### Editor changes (`editor.js`)

- **Resize handles:** when a panel (`block:N`) is selected, `renderPreview()`
  draws 4 small corner-square `data-ps-resize-handle` elements (editor-only,
  positioned over the selected panel's rendered corners, cleared/redrawn each
  render like the existing selection outline). A `pointerdown` on a handle
  begins a resize drag (distinct from the existing move-drag: it computes a
  new `{w,h}` from the pointer delta relative to the fixed opposite corner,
  calls `setSize`, and — because the corner being dragged is not always the
  anchor corner — also calls `setPosition('panel:N', …)` when the drag
  originates from a top or left handle, keeping the opposite corner visually
  anchored).
- **Block inspector additions** (`inspector.js` `buildBlockInspector`): a
  "Double width" toggle button (disabled when `index === count - 1`), wired to
  `setPillWidth`. The existing shared-label-typography sub-panel now reads
  and writes `blocks[i].labelStyle` (its "applies to all labels" note is
  removed — it now only applies to the selected block).

### Files

- `static/post_studio/composition.js` — per-block `panelW/panelH/labelStyle`
  in `seedLayout`/`hasLayout`/`ensureLayout`; new `setSize`, `setPillWidth`;
  `setTypography`'s block-label ref.
- `static/post_studio/render.js` — `buildPanel`/`buildPill`/`buildStrip` read
  per-block size/style; double-pill geometry formula; neighbor auto-hide.
- `static/post_studio/editor.js` — resize-handle overlay + resize-drag
  controller (extends the P4b-1 pointer-drag machinery).
- `static/post_studio/inspector.js` — "Double width" toggle; block label
  typography now scoped to the block, note text removed.
- `static/post_studio/spike/*_harness.html` — extend probes for per-block
  size/style + handle bounding boxes.

## Layout & data flow

1. `defaultComposition`/`applyTheme` → `seedLayout` stamps every block's
   `panelPos`, `pillPos`, `panelW`, `panelH`, `labelStyle` from the active
   theme's tokens. Legacy P4b-1 posts (missing per-block size/style) are
   migrated the same way on `deserialize` via `ensureLayout`.
2. Resize drag → `setSize` (+ `setPosition` if the anchor corner moved) →
   `state.comp = next` → `renderPreview()` (handles redrawn at the new
   corners).
3. "Double width" toggle → `setPillWidth` → `renderPreview()` → `buildStrip`
   recomputes: this block's pill widens to the covered panel's right edge,
   the next block's pill is skipped.
4. Label typography edit → `setTypography(comp, 'block:N.label', patch)` →
   only that block's label restyles.
5. Save/Download unchanged from P4b-1 (`exportBlob` re-renders a fresh,
   chrome-free stage from `state.comp`; resize handles are editor-only DOM,
   never part of the exported/serialized composition).

## Interaction spec

- **Resize:** select a panel (click, as today) → 4 corner handles appear →
  drag a corner → live resize, opposite corner anchored → release commits.
  Clamped to `[40/1080, 1−2·margin]` width / `[40/1080, 0.9]` height
  (fractional).
- **Pill width:** select a block → inspector shows "Double width" (disabled on
  the last block) → click toggles `single`/`double` → the next block's pill
  vanishes/reappears automatically.
- **Label typography:** select a block → the existing font/size/weight/color
  controls (P4a) now apply to that block only.

## Error handling

- `setSize` and `setPillWidth` throw on an out-of-range block index (mirrors
  `setPosition`'s throw-on-bad-ref) — a programming-error guard, not a
  user-facing validation (the editor only ever calls these with an index it
  already knows is valid from the current selection).
- Resize clamps both axes independently so a corner drag can't invert the
  panel (width/height can't go to 0 or negative) or push it fully off-canvas.
- Legacy-post seeding (`ensureLayout` migration) is idempotent — re-seeding an
  already-seeded comp is a no-op, same pattern as P4b-1.

## Testing (TDD)

- **`composition.test.mjs`** (node --test, DOM-free): `seedLayout` stamps
  per-block `panelW`/`panelH`/`labelStyle`; `setSize` clamps both axes
  independently and is immutable; `setPillWidth` validates its enum and is
  immutable; `ensureLayout` migrates a P4b-1-shape legacy comp (shared
  `strip.panelW`/`labelStyle`, no per-block fields) to per-block fields
  without changing rendered geometry; `setTypography(comp, 'block:N.label', …)`
  only changes that block.
- **`render_harness` probes / `test_editor_render.py`:** two panels resized to
  different sizes render at their own distinct widths/heights; a double pill
  reaches exactly the next panel's right edge when panels differ in size;
  the next block's pill is absent (`data-ps-pill-block="N+1"` not present in
  the DOM) when block `N` is double; two blocks with different `labelStyle`
  render visually distinct label typography (assert computed font-size/color).
- **`editor_harness` / `test_editor_flow.py` (Playwright):** dragging a corner
  handle changes the panel's rendered width/height and updates `panelW`/`panelH`
  in the exported `template_json`; the opposite corner's screen position stays
  fixed during a top-left-handle drag; clicking "Double width" removes the
  next block's pill from the DOM and clicking it again restores it (disabled
  on the last block); export-after-resize stays untainted (regression, same
  shape as P4b-1's export-after-drag test).

## Non-goals (YAGNI — deferred)

- Snap-while-resizing (guides only apply to move-drag this slice).
- Aspect-ratio-locked resize (free aspect only; a lock toggle can be added
  later if requested).
- Freeform (continuous) pill width — pills stay a discrete `single`/`double`
  enum; the covered-neighbor auto-hide behavior only makes sense for a
  discrete state.
- A "double" pill covering more than one neighbor (e.g. spanning 3 panels) —
  the data model and auto-hide logic only support covering exactly the next
  block.
- Resize handles on pills, title, or doctor name (pills stay discrete-width;
  title/doctor are text, already resized via P4a's font-size control).
- A bulk "apply to all labels" typography action.
- No new runtime dependencies. INLINE-STYLES-ONLY and the
  @font-face-embedded-in-export invariants (established in earlier phases)
  are preserved — resize handles are DOM chrome exactly like the P4a/P4b-1
  selection outline and snap guides, never serialized. **PR remains HELD** —
  stack P4b-2 on `feat/post-studio`; one PR only once the editor is the full
  premium designer replacing Pillow. Do not open a PR or push to origin
  unprompted.
