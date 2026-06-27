# Post Studio — Premium Template Designer (Redesign)

**Date:** 2026-06-27
**Branch:** `feat/post-studio`
**Status:** Design approved, ready for implementation planning
**Supersedes:** `docs/superpowers/specs/2026-06-25-post-studio-design.md`

## Why a redesign

The first Post Studio (built on this branch, **never merged to main** — so this is a
clean slate with no data to migrate) renders **server-side with Pillow**: 1–4 photos,
one of 4 flat themes, a fixed doctor-name header slot, a clinic logo. It works but is
**rigid** — you cannot move the name, change its font/size/color, write a title, or
compose a layout.

The user wants a **premium, fully customizable template designer**: create a complete
before/after (and multi-phase) marketing post in one go, place every element freely,
control all typography, and produce output that looks like the reference image
`go.png` (a "Root Canal Treatment" dental X-ray showcase). This redesign delivers that.

## Reference design language (`go.png`)

The flagship look we are matching — far beyond today's flat themes:

- **Deep navy background with a soft radial glow** (brighter teal-blue center, dark
  vignette edges). Not a flat fill.
- **Two-tone headline**: bold white line ("Root Canal Treatment") + a lighter teal
  second line ("for Lower Molar"), with a small inline tooth icon. A *procedure title*
  — a concept the current engine lacks entirely.
- **Rounded-corner photo cards** with a faint border/inner glow on the dark background.
- **Circular numbered badges** (①②) each paired with a label ("Before Treatment" /
  "After Treatment") instead of a solid color strip.
- **Doctor-name footer**: gold, uppercase, letter-spaced, centered
  ("DR. WASFY BARZAQ"). **No logo anywhere.**

This becomes the **Dark Premium** theme + the **Before/After Showcase** starter template.

## Goals

- A **live WYSIWYG template designer** in the desktop WebView: what you see is exactly
  what you export.
- **Templates as starting points, not cages** — seed from a premium template, then
  customize deeply (drag-position any element, full type control).
- **Before/After + multi-phase**: a repeatable strip of photo blocks you can
  add / remove / reorder / insert between, with auto-numbered badges and editable labels.
- **4 redesigned premium themes**: Dark Premium (reference), Light Luxury,
  Clinical Premium, Bold Editorial.
- **Remove the clinic logo** entirely. **No branding popup on first run.**
- **New tab icon** (today's bar-chart glyph is wrong for an image tool).
- **Save + reopen for editing** (persist the editable spec, not just the PNG).
- Mobile stays **read-only** (shows the synced exported PNG), unchanged.
- EN/AR throughout; Arabic renders natively (Chromium), no PIL reshaping hack.

## Non-goals (deliberate v1 scope)

- **No mobile generation** — read-only viewer only.
- **No free blank-canvas mode** (mini-Canva) — templates seed every composition.
- **No patient-photo import** — photos uploaded fresh (future enhancement).
- **No arbitrary user-uploaded fonts** — a curated bundled font set only.
- **No clinic logo** — removed by request.

## Architecture

### Rendering: client-side WYSIWYG (the pivot)

The editor and the export share **one renderer**: the live **HTML/CSS composition in
the WebView (Chromium)**. Gradients, glows, rounded cards, letter-spacing,
mixed-weight type, and Arabic all render natively and identically to the export.

- **Preview** = the editable DOM canvas itself (no server round-trip; the old
  `POST /api/posts/preview` is removed).
- **Export** = rasterize that exact DOM node to PNG **client-side**, fully offline
  (bundled, no CDN — consistent with the project's inline-assets rule).
  - **Default approach:** a vendored `html-to-image`-class rasterizer (SVG
    `<foreignObject>` → canvas), with fonts inlined and same-origin images embedded.
  - **Fallback (only if fidelity/taint issues appear):** a hand-rolled Canvas 2D
    renderer mirroring the composition. A short spike in P2 validates the default
    before committing; this is the one open implementation risk and is contained.
  - Wait for `document.fonts.ready` and embed images before capture; render at full
    resolution (1080×1080 / 1080×1350 / 1080×1920) accounting for devicePixelRatio.

### Server role (shrinks to storage/sync)

The server no longer renders. The pure Pillow engine is **retired**:
- Delete `post_studio.py`, `post_themes.py`, and the golden-image tests
  (`test_post_studio_engine.py`).
- `arabic-reshaper` / `python-bidi` are no longer needed for rendering (Chromium
  handles Arabic). Leave the deps installed-but-unused for now (removing them from
  the PyInstaller bundle is a separate low-value cleanup); note in the plan.
- Themes/templates move client-side as CSS/JS theme tokens.

## Composition model (the editable spec — "template JSON")

A saved post **is** its editable spec, so it can be reopened and kept editing.

```jsonc
{
  "version": 1,
  "size": "square",                  // square | portrait | story
  "theme": "dark_premium",
  "elements": [
    { "id": "title", "type": "title",
      "x": 0.5, "y": 0.10, "align": "center",
      "headline": { "text": "Root Canal Treatment",
                    "font": "playfair", "size": 64, "weight": 700,
                    "color": "#ffffff", "letterSpacing": 0 },
      "subline":  { "text": "for Lower Molar",
                    "font": "manrope", "size": 40, "weight": 500,
                    "color": "#5fd3c8", "letterSpacing": 0 },
      "icon": "tooth" },             // optional inline icon | null
    { "id": "strip", "type": "photoStrip",
      "layout": "row",               // row | grid (derived from block count)
      "blocks": [
        { "photo": "posts/<id>/a.jpg", "badge": 1, "label": "Before Treatment" },
        { "photo": "posts/<id>/b.jpg", "badge": 2, "label": "After Treatment" }
      ],
      "labelStyle": { "font": "manrope", "size": 28, "weight": 600, "color": "#cfd8e3" } },
    { "id": "doctor", "type": "doctorName",
      "x": 0.5, "y": 0.93, "align": "center",
      "text": "DR. WASFY BARZAQ",
      "font": "manrope", "size": 34, "weight": 700,
      "color": "#c9a227", "letterSpacing": 4 }
  ]
}
```

- **Positions** are fractional (0–1) so they're size-independent; drag updates them,
  with snap guides (center / thirds).
- **Element types (v1):** `title`, `photoStrip`, `doctorName`. (`text` free-caption
  element is a cheap future add; flagged, not in v1 unless trivial.)
- **Photo/phase blocks** (`photoStrip.blocks`): add / remove / reorder / insert-between;
  badges auto-renumber; labels freely editable (EN/AR). Capped at **6** blocks.
- **Per-element typography:** font (curated set), size, weight, color, alignment,
  letter-spacing. `doctorName` defaults from branding but is movable/restyleable/deletable.
- **Round-trip:** load `template_json` → restore the exact composition for re-editing.

### Starter templates (seed specs)

1. **Before/After Showcase** — the reference (title + 2 cards + numbered badges + gold name).
2. **Multi-Phase** — 3+ blocks (Before / During / After …), insertable phases.
3. **Quad Grid** — 2×2 photo grid for 4 angles.
4. **Single Feature** — one hero photo + title + name.

## Themes (curated premium set of 4 — replaces today's 4)

Each theme = background + accent(s) + default fonts + badge style + card style + name color.

- **Dark Premium** — navy radial-glow bg, gold name, teal accents, rounded glowing
  cards, serif headline (the reference).
- **Light Luxury** — warm off-white/cream, gold + deep-ink, serif headline, thin-ruled
  badges, soft shadow cards.
- **Clinical Premium** — crisp white, DentaCare blue accents, airy bold sans,
  filled blue badges, clean bordered cards. Trustworthy/medical.
- **Bold Editorial** — high-contrast color-block header, oversized type, solid badges,
  square cards.

## Typography / fonts

Curated **bundled, inlined** set (no CDN), each selectable per element:
- **Latin (~6):** Playfair Display (serif display), Manrope (sans), + a small set of
  additional premium faces to be finalized in the plan (e.g., a geometric sans, a
  condensed display, a humanist sans) — exact list confirmed during P3.
- **Arabic (2):** Cairo + one additional Arabic face with good display weight.
- Bundled in `fonts/` and included in `DentaCare.spec`.

## Branding (simplified)

`app_settings` keys:
- **Keep:** `doctor_name`, `doctor_name_ar`, `post_default_theme`.
- **Remove:** `clinic_logo_path`, `branding_wizard_done`, the logo upload endpoint,
  and the **first-run branding wizard** (no popup, ever).
- Branding becomes an **optional Settings panel** (doctor name EN/AR + default theme).
  Device-local; already excluded from the cloud-settings overwrite path.

## Data model

`marketing_posts` (clean slate — pre-release, alter freely):
- **Keep:** `id`, `title`, `theme`, `size`, `doctor_name_snapshot`, `file_path`
  (exported PNG, for mobile), `created_at`.
- **Add:** `template_json` (the full editable spec).
- `photo_count` / `labels_json` are derivable from `template_json` → drop.
- Source photos + exported PNG live under `UPLOAD_FOLDER/posts/<id>/…`, part of the
  export/import bundle → **syncs to mobile with no new sync code**.

## Endpoints (`dental_clinic.py`) — desktop-only, auth + CSRF

- `GET /api/branding` / `PUT /api/branding` — doctor name (EN/AR) + default theme.
  **(logo endpoints removed.)**
- `POST /api/posts/photos` — upload source photo(s); returns stored server-safe paths.
- `POST /api/posts` — save: receives the client-exported **PNG** + `template_json`
  (+ already-uploaded photo refs); persists row + files.
- `GET /api/posts` — list gallery.
- `GET /api/posts/<id>` — return `template_json` (for re-edit).
- `GET /api/posts/<id>/image` — serve the exported PNG.
- `DELETE /api/posts/<id>`.
- **Removed:** `POST /api/posts/preview` (preview is client-side now),
  `POST /api/branding/logo`.

## UI

- **Post Studio tab** (`templates.py`, assets in `web_assets.py`):
  - **Left:** template gallery + photo add/manage + phase add/reorder.
  - **Center:** the live WYSIWYG canvas (drag, select, snap guides).
  - **Inspector (right):** the selected element's typography/position controls.
  - **Actions:** Save to Gallery, Download. **Gallery** view → reopen-to-edit / delete.
- **Tab icon:** swap `#i-chart-bar` → an image/sparkle glyph (reuse a sprite glyph;
  add one if none fits).
- EN/AR + RTL-aware throughout.

## Mobile (read-only, unchanged)

Flutter **Posts** screen lists synced `marketing_posts`, shows the exported PNG from
synced uploads, offers OS share. No generation. The PNG-based contract is unchanged,
so existing mobile code keeps working.

## Error handling & security

- Validate uploads at the boundary: image type only, enforce the size cap, downscale
  oversized inputs, 1–6 photos. Corrupt image → clear error.
- Server stores server-generated filenames (`secure_filename` + the existing safe
  upload pattern). Text only ever becomes pixels (PNG) — no injection sink.
- All endpoints behind auth + the existing CSRF interceptor.

## Testing / QA

- **State-model unit tests** (the composition model as a pure JS module): block
  add/remove/reorder/insert, badge renumbering, default-template construction,
  `template_json` serialization round-trip. Run via `node`.
- **Endpoint tests (pytest):** branding (no logo), posts save → list → get-spec →
  serve → delete, auth required, bad-input rejection. Repurpose
  `test_post_studio_api.py`.
- **Playwright visual + behavioral smoke:** load the editor; screenshot each
  starter-template × theme; drag/type/add-phase smoke; EN/AR. Replaces the retired
  golden-image pixel tests.
- Remove `test_post_studio_engine.py` (engine retired).
- **Gates:** full pytest green; `node --check` clean across edited assets;
  Playwright smoke passes light + dark.

## Build order (resumable portions — each its own PR-able slice)

- **P1 — Cleanups (small, immediate):** new tab icon; remove the clinic logo
  (branding + engine + UI); remove the first-run branding wizard. Ships 3 explicit asks.
- **P2 — Editor core:** WYSIWYG canvas + composition state model + client-side PNG
  export (incl. the rasterizer spike) + save/load/list/delete wired to the new spec;
  retire the Pillow engine.
- **P3 — Premium themes + starter templates:** the 4 themes + 4 templates, matching
  the reference; finalize the bundled font set.
- **P4 — Deep customization:** drag-positioning + snap guides, full per-element type
  controls, numbered badges, add/reorder/insert phases, editable title/subline.
- **P5 — QA & polish:** EN/AR pass, Playwright smoke, mobile read-only verify, full
  pytest green, exe-rebuild note.

## Open follow-ups (future, out of scope)

- Free-caption `text` element; free blank-canvas mode.
- "Import from patient" (reuse `medical_images`).
- Mobile post generation.
- More templates/themes; removing the now-unused Arabic-shaping Python deps from the bundle.
