# Post Studio — P4b-1: Layout & Fidelity (Design Spec)

**Date:** 2026-07-01
**Branch:** `feat/post-studio`
**Phase:** P4b-1 (first of two slices splitting the original "P4b free drag-layout")
**Status:** Approved design — ready for implementation plan.

## Context

P4a turned the editor into a real content editor (select-then-inspect: edit any
text run or photo block's copy, typography, and photo). But **layout is still
fixed**: text elements get a vertical-only fractional `y` + `align`, and the
photo strip is hardcoded to vertical-center with 6% side margins
(`render.js buildStrip`: `left:6%; right:6%; top:50%; translateY(-50%)`, flex
row / grid). There is no `x`, no free placement, and no drag.

Because of that, the navy_gold flagship — the whole redesign's fidelity anchor
(`C:\Users\MSI\Desktop\go.png`, spec `docs/superpowers/specs/2026-06-29-template-navy-gold.md`)
— matches on *styling* but not on *position*: the reference puts the panel row
at y=360 (sized 250×320), the pill row at y=708 with a **516px double-span
pill**, and the doctor name at y=920, whereas the shipped flagship centers the
panels, renders single-width pills, and sits the doctor at y≈0.93.

The original "P4b free drag-layout" bundles seven capability areas (absolute
coordinate model, free drag, smart guides + snap, keyboard nudge, exact
navy_gold defaults, variable-width pills, per-block label typography, resize
handles). Per the decomposition decision (2026-07-01) it is split into two
stacked slices:

- **P4b-1 (this spec) — Layout & Fidelity:** the absolute coordinate model, free
  drag, smart guides + snap, keyboard nudge, and the navy_gold flagship baked
  pixel-exact to `go.png` (including the double-span pill as a *default* data
  property). This fully delivers the user's "exact default + drag freedom" goal.
- **P4b-2 (next slice) — Shape & per-element style:** resize handles for
  panels/pills, a pill-width editing UI, and per-block label typography. The
  heavier freeform-editing surface, built on P4b-1's coordinate model.

## Goal

Replace the fixed-layout renderer with a **free-positioning canvas**: every
element (title, doctor, each panel, each pill) is independently placeable via
pointer drag, with smart alignment guides, snapping, and keyboard nudge. Seed a
fresh post so it looks identical to today, and seed the navy_gold flagship to
its exact reference pixels so a new dark_premium post reproduces `go.png` out of
the box.

## Decisions (all user-approved in brainstorming, 2026-07-01)

1. **P4b-1 goal = exact default + drag freedom.** The navy_gold flagship renders
   pixel-exact to `go.png` on creation, AND the user can then drag any element
   anywhere to adjust. Fidelity is the starting point; drag is the tool.
2. **Everything is independently draggable.** Title (as one unit), doctor, each
   panel, and each pill — all placeable on their own. (Not just the strip as a
   group.)
3. **Smart guides + nudge.** Free drag with alignment guides that snap to canvas
   center, safe margins, and other elements' edges/centers (live guide lines on
   snap); arrow-key nudge (1px, Shift = 10px). Not a fixed grid; not free-with-
   no-help.
4. **Split P4b → P4b-1 (layout/fidelity) + P4b-2 (shape/style).** Resize handles,
   pill-width editing UI, and per-block label typography defer to P4b-2.
5. **Title moves as one unit** (headline + subline + divider positioned
   together; per-line placement is unchanged from the already-accepted navy_gold
   stacking). Splitting the two title lines is not needed in this slice.
6. **Sizes stay theme-driven in this slice** (panel = theme width × aspect; pill
   height 56px; pill width is a `'single' | 'double'` property). Free resize is
   P4b-2.

## Architecture

### Coordinate model — "always explicit, seeded from layout"

- Every positionable element carries an absolute fractional position
  `pos: { x, y }`, where `x` ∈ [0,1] is a fraction of canvas **width** and `y` ∈
  [0,1] is a fraction of canvas **height**. The anchor is the element's **center**
  for text elements (title, doctor) and its **top-left** for box elements (panel,
  pill). Rationale: text is naturally centered on the canvas; boxes have definite
  corners. The drag controller and snap engine operate on each element's *rendered
  bounding box* (measured), so the stored anchor only matters for applying drag
  deltas and seeding defaults.
- **`pos` is serialized** into `template_json` (it is real composition state,
  unlike P4a's editor-only selection). The export path (`renderComposition` →
  fresh off-screen stage) is faithful because positions live in `comp`.
- **The model is always fully explicit.** `render.js` becomes a single
  absolute-placement path (no flex/grid auto-centering). To preserve visual
  continuity, a deterministic `seedLayout(comp)` materializes every element's
  `pos` from a formula that mirrors today's row/grid intent — so a fresh
  non-flagship post looks the same as P4a until dragged. The navy_gold default
  seeds the **exact reference coordinates** instead. Saved posts that predate
  `pos` are seeded on `deserialize` (backward compatibility).
- **Seed geometry (formula, non-flagship):** side margin `m = 0.06`; content
  width `cw = 1 − 2m`; for `n` panels in a row, `panelW = (cw − (n−1)·gap) / n`
  (fractional gap ≈ `0.03`). The theme card aspect (width:height, e.g. `250:320`)
  gives the fractional height `panelH = panelW · (canvasW / canvasH) · (aspH /
  aspW)` (for the square canvas this is `panelW · 320/250`); panels centered
  vertically (`panelY = 0.5 − panelH/2`), `panelX_i = m + i·(panelW+gap)`; each
  pill single-width directly
  below its panel (`pillY = panelY + panelH + gap`, `pillX = panelX`); title
  center `(0.5, templateTitleY)`; doctor center `(0.5, templateDoctorY)`. Grid
  templates (>3 blocks) seed a 2-column arrangement analogously. The plan pins
  exact constants.
- **Flagship exact override (navy_gold / dark_premium default):** all values as
  `px / 1080` since the flagship targets the 1080² square (see the navy_gold
  spec §4): panels `250×320` at `y=360`, `panelX_i = (16 + i·266)/1080`; pills
  `y=708`, single width `250/1080`, double width `516/1080`; **the spanning pair
  is a double-width pill** (per the reference "[pill] [pill] [ pill spans 2 ]");
  doctor center `y=920/1080`; title unit positioned so its stacked headline/
  subline/divider reproduce the accepted navy_gold placement (center ≈
  `172/1080`). The plan pins the full table.

### What's draggable

Four element kinds become independently positionable:

- **title** — the headline + subline (+ divider) block, moved as one unit by its
  center.
- **doctor** — the doctor-name text, moved by its center.
- **panel** — each photo card (`blocks[i]`'s image frame + badge), moved by its
  top-left.
- **pill** — each number-pill label (pill-style themes), moved by its top-left,
  independent of its panel.

The **photo strip stops being an auto-flex/grid container** and becomes an
absolute-positioning container. Blocks still live in the `strip.blocks` array, so
all of P4a's block management is preserved: add / remove / replace / arrow-
reorder and badge renumber still work. Arrow-reorder now reorders **badge
numbering** only (spatial position is independent). A block's panel and pill
carry their own positions: `blocks[i].panelPos` and `blocks[i].pillPos`
(fractional, top-left); non-pill themes render only the panel + inline label
(the label follows the panel, no separate `pillPos`).

### Drag + smart guides + nudge (editor-only)

- **Drag:** pointer-down on an element selects it (reusing P4a's selection +
  `#38bdf8` outline) and begins a move; pointer-move converts the display-px
  delta to a fractional delta (÷ preview scale ÷ canvas size) and updates the
  element's `pos` live; pointer-up commits. Dragging is on the on-screen preview
  stage only.
- **Smart guides:** during a drag, the dragged element's left/center/right and
  top/middle/bottom are tested against snap targets = canvas center-x, center-y,
  the safe side margins, and every *other* element's left/center/right and top/
  middle/bottom (all read from rendered bounding boxes). Within a threshold
  (~6 display-px) the position snaps and a guide line is drawn on the stage. Guide
  lines are editor chrome — created after render, never serialized, never in the
  export stage.
- **Nudge:** with an element selected, ArrowLeft/Right/Up/Down move it 1 canvas-
  px; Shift+Arrow moves 10 canvas-px. Positions clamp so the element's anchor
  stays within [0,1].
- **Invariants preserved from P4a:** selection, outline, guide lines, and any
  drag affordance are editor-only and never serialized; `render.js` stays
  INLINE-STYLES-ONLY (positions are inline `left`/`top`/`transform`); the
  untainted-PNG export path is unchanged (`exportBlob` re-renders a fresh,
  chrome-free stage from `state.comp`).

## Files

- **`static/post_studio/composition.js`** — add `pos` to the element model;
  `seedLayout(comp)` (deterministic position materialization, called from
  `defaultComposition`/`applyTheme` and `deserialize` for legacy posts); immutable
  `setPosition(comp, ref, {x,y})` and `nudgePosition(comp, ref, dxPx, dyPx, canvas)`
  (clamped, `structuredClone`, never mutate input); a `pill.width`
  (`'single' | 'double'`) property with the flagship default marking the spanning
  pill `double`. `ref` extends the P4a scheme to address panels/pills
  (`title`, `doctor`, `panel:N`, `pill:N`).
- **`static/post_studio/render.js`** — replace the hardcoded strip flex/center
  with a single absolute-placement path driven by each element's `pos`; keep
  `data-ps-block="<i>"` on panels and add an indexed pill hook
  (`data-ps-pill-block="<i>"`); render `pill.width` (single 250 / double 516 @
  1080). Still pure, inline-styles-only; the P4a `data-ps-el` text hooks and the
  navy_gold builders (wave footer, divider, gold-rim panels) are preserved.
- **`static/post_studio/editor.js`** — a pointer-drag controller (select →
  move → commit) layered on the P4a selection/inspector; a guide-overlay renderer
  (draw snap lines during drag, clear after); a nudge key handler; a small
  "Position" readout in the inspector (x/y shown; editing is via drag/nudge in
  this slice). `mountEditor` keeps its P4a shape (host-agnostic, EN/AR,
  `initialComp`, lang re-mount hook).
- **`static/post_studio/spike/*_harness.html`** — extend the render/editor
  harness probes to expose element bounding boxes / `pos` for e2e assertions.

The seed geometry + snap math are small, pure, and testable in isolation
(node --test); the drag/guide wiring is exercised via Playwright, consistent with
the existing test topology.

## Layout & data flow

1. `defaultComposition(template)` builds the base and `seedLayout` stamps explicit
   positions; `applyTheme(comp, 'dark_premium')` overrides with the exact flagship
   coordinates + the double-span pill. Legacy saved posts (no `pos`) are seeded on
   `deserialize`.
2. `renderPreview()` renders the stage from `state.comp` (every element absolutely
   placed), then attaches the editor-only pointer-drag + guide overlay + the P4a
   selection outline.
3. Pointer drag / nudge → the matching immutable `composition` helper
   (`setPosition` / `nudgePosition`) → `state.comp = next` → `renderPreview()`
   (selection + position preserved).
4. Save/Download → `exportBlob()` → `renderComposition(state.comp)` on a fresh
   off-screen stage → untainted PNG. No selection, outline, or guide reaches the
   export.

## Interaction spec

- **Select:** click an element (P4a). Outline `3px solid #38bdf8`.
- **Move:** drag a selected (or directly pointer-down) element; live snap to
  guides; guide lines shown while snapping; release commits.
- **Nudge:** Arrow = 1px, Shift+Arrow = 10px (canvas px), clamped to canvas.
- **Blocks:** P4a inspector actions unchanged (label, replace, remove [≥1], move
  ◄►, +Add [cap 6]); arrows reorder badge numbering only.

## Error handling

- Positions clamp to keep the element anchor within [0,1] (no off-canvas loss).
- Drag delta math guards against a zero or unknown preview scale (falls back to
  no-op rather than jumping).
- Photo add/replace reuse the existing staging upload + validation (P4a); failures
  surface via the existing toast.
- Legacy-post seeding is idempotent (seeding an already-seeded comp is a no-op).

## Testing (TDD)

- **`composition.test.mjs`** (node --test, DOM-free): `seedLayout` produces
  in-range fractional positions for every element and is idempotent;
  `setPosition`/`nudgePosition` are immutable and clamp; `pill.width` defaults and
  the flagship override are correct; the navy_gold default seeds the exact
  reference coordinates (assert the key px/1080 values).
- **e2e (Playwright)** over the editor/render harnesses: dragging an element
  updates its `pos` and moves it on the stage; snap engages at canvas center and
  at a margin (guide line appears); nudge moves 1px / 10px; the dark_premium
  default renders panels at y=360, the double-span pill at y=708 (width 516), and
  the doctor at y=920 (assert measured coordinates); **export-after-drag stays
  untainted (PNG produced).**

## Non-goals (YAGNI — deferred to P4b-2 or later)

- Resize handles for panels/pills; a pill-width editing UI; per-block label
  typography (all P4b-2).
- Splitting the two title lines into independently positioned runs.
- Per-size (portrait/story) bespoke layouts — positions are fractional and
  reposition proportionally; the flagship targets the 1080² square.
- No new runtime dependencies. INLINE-STYLES-ONLY and the
  @font-face-embedded-in-export invariants are preserved. **PR remains HELD** —
  stack P4b-1 on `feat/post-studio`; one PR only once the editor is the full
  premium designer replacing Pillow. Do not open a PR or push to origin
  unprompted.
