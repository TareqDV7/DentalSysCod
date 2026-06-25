# Post Studio — Case-Showcase Post Generator + Clinic Branding

**Date:** 2026-06-25
**Branch:** `feat/post-studio`
**Status:** Design approved, ready for implementation planning

## Summary

A built-in tool that turns 1–4 clinical photos into a single branded, themed
social-media image (a before/during/after case showcase), plus a reusable
**clinic branding** identity (doctor name, logo, default theme) that feeds it.

Inspired by the user's reference tool `Template.exe` ("Dental X-Ray Post
Generator" — a small tkinter app: upload Before/During/After X-rays, enter the
doctor's name, "Generate Post"). This feature reimplements that idea natively in
DentaCare, expanded with flexible photo counts, a clinic logo, multiple themes,
multiple output sizes, a saved gallery, and read-only mobile viewing.

The composition is done **server-side with Pillow** (already a dependency),
matching `Template.exe`'s Python/PIL approach and keeping output deterministic
and testable.

## Goals

- Generate a polished, branded marketing image from 1–4 clinical photos.
- Reuse a clinic identity (doctor name EN/AR, logo, default theme) set once and
  editable anytime.
- Ship 4 themes and 3 output sizes.
- Persist generated posts to a gallery that syncs to mobile (read-only there).
- Stay within the existing stack: Flask + WebView2 desktop, Pillow, the
  `app_settings` key-value store, the `UPLOAD_FOLDER` bundle-sync path, and the
  Flutter mobile app.

## Non-Goals (deliberate v1 scope calls)

- **No contact/phone footer bar** on posts (not selected; easy to add later).
- **Posts are not patient-linked** — standalone marketing tool; photos are
  uploaded fresh, not pulled from a patient's `medical_images`. "Import from
  patient" is a future enhancement.
- **No client-side/Canvas rendering** — server-side Pillow only.
- **Mobile does not generate** — read-only view + OS share only.

## User Flow

### Generate (desktop)
1. Open the **Post Studio** tab → "New Post".
2. Add **1–4 photos** (drag/drop or file picker). Each photo has an editable
   label (defaults *Before / During / After /* blank; freely editable, EN/AR).
3. Doctor's name auto-fills from branding (editable per post). Clinic logo
   auto-applied.
4. Pick a **theme** (Dark Premium / Clean Clinical / Soft Mint / Bold Editorial)
   and a **size** (Square / Portrait / Story).
5. Live preview shows the real rendered PNG, re-rendered on change (debounced).
6. **Save to Gallery** (persists + syncs) and/or **Download**.

### Gallery (desktop)
Grid of past posts → re-download, delete.

### Mobile (read-only)
A **Posts** screen lists synced posts, shows the full PNG, offers OS **share**.
No generation.

## Architecture & Components

### `post_studio.py` (new, pure module — no Flask)
The render engine. Deterministic, unit- and golden-image-testable. Target
< ~500 lines.
- `layout_slots(count, size) -> list[Rect]` — photo slot rectangles for each
  photo count (1–4) × size (square/portrait/story).
- `render_post(spec) -> PIL.Image` — composes header (logo + doctor name),
  photo grid (center-cropped to slots, per-slot labels), footer accent bar.
- One renderer/palette per theme (theme data lives in a small `post_themes.py`).
- `shape_arabic(text) -> str` — reshape + bidi for correct Arabic rendering in
  PIL.

### Endpoints (in `dental_clinic.py`)
All desktop-only → added to the auth-required set; CSRF handled by the existing
`window.fetch` interceptor.
- `GET /api/branding` — current branding.
- `PUT /api/branding` — doctor name (EN/AR), default theme.
- `POST /api/branding/logo` — logo upload.
- `POST /api/posts/preview` — accepts photos + spec, returns a PNG (not saved).
- `POST /api/posts` — generate + save to gallery.
- `GET /api/posts` — list gallery.
- `GET /api/posts/<id>/image` — serve a saved post image.
- `DELETE /api/posts/<id>` — delete.

### UI
- **Post Studio** tab in `templates.py`; JS/CSS in `web_assets.py`, following
  existing tab/patterns. Left: photos + labels + doctor name + theme + size.
  Right: live preview. Actions: Save to Gallery, Download.
- **Settings → Branding** panel (edit anytime).
- **First-run branding wizard** (one-time after activation).
- EN/AR throughout, consistent with the rest of the app.

### Dependencies
- Bundle TTF fonts in a `fonts/` directory (Latin + Arabic with Arabic glyph
  coverage; serif for Dark Premium, bold sans for Bold Editorial), included in
  the PyInstaller `.spec`.
- Add `arabic-reshaper` and `python-bidi` (tiny, pure-Python) for Arabic
  shaping in PIL.

## Data Model

### Branding → existing `app_settings` (key-value)
- Reuses `doctor_name`, `doctor_name_ar`.
- Adds `clinic_logo_path`, `post_default_theme`, and a one-time
  `branding_wizard_done` flag.
- Device-local; already excluded from the cloud-settings overwrite path.

### `marketing_posts` (new table)
`id, title, theme, size, doctor_name_snapshot, photo_count, labels_json,
file_path, created_at`. Rows sync via the existing DB sync.

### Files (under `UPLOAD_FOLDER`)
- `branding/logo.png`
- `posts/<id>.png` (+ source photos)
- `UPLOAD_FOLDER` is part of the export/import **bundle** → posts sync to mobile
  automatically; no new sync code.

## Render Engine Detail

- **Adaptive layouts** by photo count:
  - 1 = full feature image.
  - 2 = side-by-side (square/portrait) or stacked (story).
  - 3 = row-of-3 or stacked.
  - 4 = 2×2 grid.
  - Photos are center-cropped to slot aspect; labels drawn per slot.
- **Common zones**: header (logo + doctor name), photo grid, footer accent bar.
  No contact bar.
- **Themes** (palette + fonts + decoration):
  - **Dark Premium** — charcoal background, gold accents, serif heading.
  - **Clean Clinical** — white background, DentaCare blue, airy sans.
  - **Soft Mint** — mint gradient, rounded cards, friendly.
  - **Bold Editorial** — big type, color-block header, high contrast.
- **Sizes**: 1080×1080 (Square), 1080×1350 (Portrait), 1080×1920 (Story); all
  rendered at full resolution for crisp export.

## Branding Wizard + Settings

- **First-run wizard** (gated by `branding_wizard_done` in `app_settings`,
  shown after activation): doctor name EN/AR → logo upload → default theme →
  done. Skippable; never auto-re-runs (editable later in Settings).
- **Settings → Branding panel**: same fields, editable anytime, EN/AR.

## Mobile (read-only)

Flutter **Posts** screen: lists synced `marketing_posts`, shows the full PNG
from synced uploads, OS share. No generation. Minimal surface.

## Error Handling & Security

- Validate uploads at the boundary: image type only (reject non-images), enforce
  the existing size cap, downscale oversized inputs, require 1–4 photos. Corrupt
  image → clear error.
- Text is rendered via PIL (no HTML-injection path).
- Endpoints behind auth + CSRF. `secure_filename` + server-generated names
  (reuses the existing safe upload pattern).

## Testing (TDD)

- **Unit**: `layout_slots` rect math for every count × size; the Arabic
  reshaping helper.
- **Golden-image**: render each theme × size with fixed inputs → assert correct
  dimensions and compare against committed reference PNGs with a small
  perceptual tolerance.
- **Endpoint/integration**: branding CRUD, preview returns a PNG, save → list →
  serve → delete, auth required, bad-input rejection.
- Target ≥ 80% coverage on new code; the full pytest suite stays green.

## Suggested Build Order (one spec, phased plan)

1. Branding store + logo upload + Settings panel.
2. `post_studio.py` engine + 4 themes + golden tests.
3. Generator UI + live preview + Gallery.
4. First-run branding wizard.
5. Mobile read-only viewer.

## Open Follow-ups (future, out of scope for v1)

- Contact/phone footer bar option.
- "Import from patient" (reuse a patient's `medical_images`).
- Hybrid HTML/CSS live preview (Approach C) if server preview ever feels slow.
- Mobile post generation.
