# UI/UX Overhaul — Phase 0: Foundation + Shared Chrome

**Date:** 2026-06-15
**Status:** Design approved (shell + accent, both themes); spec pending final user sign-off
**Branch (planned):** `feat/ui-overhaul-p0` (fresh branch off `main`)
**Predecessors:** Approved 4-phase overhaul plan (memory `project_ui_overhaul_plan.md`). This is Phase 0 of 4.

---

## 1. Context & Why

The desktop portal (`templates.py`, single ~7.9k-line Flask template string) already uses Space Grotesk + Manrope, blur, gradients, and CSS custom properties — so the overhaul is an **elevation**, not a greenfield rebuild. But the foundation is uneven:

- **Fonts load from the Google CDN** (`@import` at `templates.py:16`) — an external dependency the offline-first desktop app should not have.
- **Design tokens are split across two `:root` blocks** (`:16` colors, `:756` spacing) and incomplete — there is no radius, elevation, or motion *scale* (only a single `--shadow`).
- **The accent is teal (`--accent: #13b5a7`)**, which clashes with the blue DentaCare logo.
- **Dark theme is ~50+ per-component hardcoded-hex overrides** (`body[data-theme="dark"] .foo { background:#111c30 }`), not token-driven — every new surface re-hardcodes its dark colors.
- **There is no icon system** — controls are emoji/text (4 total glyph occurrences in the file).

Phase 0 hardens this foundation and reskins the **shared chrome** (top header + left sidebar) into the approved "Editorial Slate" direction, so Phases 1–3 build on solid tokens instead of re-deriving them.

---

## 2. Goals & Non-Goals

### Goals (what Phase 0 ships)
1. **Self-host fonts** — bundle Space Grotesk + Manrope locally; remove the Google CDN `@import`.
2. **Self-host an icon system** — an inlined Phosphor subset (the ~13 icons the shell uses), Regular weight with Fill reserved for the active item. No CDN, no runtime web font.
3. **Consolidate & harden tokens** — one `:root` block: color, spacing, radius, elevation, motion scales, plus a complete dark-theme token set. Re-accent from teal to logo-matched blue.
4. **Reskin the shared chrome** — restyle the existing header (`.header`) and left sidebar (`.nav-tabs` / `.nav-tab` / `.nav-subtab`) to Editorial Slate, in both light and dark, **without changing layout or markup structure**.

### Non-Goals (explicitly deferred to later phases)
- Redesigning page/surface *content* — dashboard layout (Phase 3), billing math preview (Phase 1), destructive-action modals / skeletons (Phase 2), odontogram (Phase 3, currently hidden).
- De-hardcoding *every* per-component dark override in the file. Phase 0 converts only the **shell's** dark styling to tokens; deeper surfaces are converted as their phase touches them.
- Any mobile (Flutter) change. Phase 0 is desktop `templates.py` only.
- Any behavioral/JS change. This is CSS + static assets + markup-class reskin only.

---

## 3. Locked Design Decisions (from brainstorm)

| Decision | Choice |
|---|---|
| Shell direction | **B — "Editorial Slate"**: dark slate chrome (header + sidebar) + light content canvas + solid white data surfaces |
| Core rule | **"Glass for chrome, solid for data"** — blur/translucency allowed on the chrome only; data surfaces stay opaque and high-contrast (legible under surgical glare) |
| Brand mark | **Keep the real DentaCare logo** (`/logo` = `DentaCare.PNG`, blue shield) — NOT the Phosphor tooth |
| Accent | **Solid blue for ink, teal→blue gradient for fills.** Ink (text, rails, focus rings, icons) = solid logo-blue `#38bdf8`. Fills (CTAs, avatar, active-item pill) = `--accent-gradient` teal→blue `linear-gradient(135deg,#14b8a6,#2563eb)`. Solid accent is NOT teal; teal appears only as a gradient stop on fills |
| Fonts | Keep **Space Grotesk** (display) + **Manrope** (body), self-hosted |
| Icons | **Phosphor**, self-hosted subset, **Regular weight + Fill on the active item only** |
| Header controls | **Keep all originals**: system + clinic name, editable doctor badge, theme toggle, EN/AR language, logout, patient search |
| Sidebar | **Keep structure + section labels** (`.nav-group-label`); recolor to dark slate |
| Dark theme | Chrome stays slate in both themes; in dark the content canvas drops to slate-950 and data surfaces become solid slate-800 (still opaque) |

---

## 4. The Foundation Layer

### 4.1 Tokens (one consolidated `:root`)

Merge the two existing `:root` blocks into one and extend it. **Keep existing token names and spacing values** to avoid churn across hundreds of usages — this is hardening, not renaming.

**Color (light):**
```
--chrome-bg: #0f172a;        /* slate-900 — header + sidebar */
--chrome-bg-2: #0b1220;      /* sidebar well */
--chrome-border: rgba(255,255,255,.06);
--canvas: #f1f5f9;           /* content background */
--surface: #ffffff;          /* solid data card */
--surface-border: rgba(15,23,42,.07);
--ink: #0f172a;
--ink-muted: #64748b;
--ink-subtle: #94a3b8;
--accent: #38bdf8;           /* was #13b5a7 teal → now logo blue */
--accent-strong: #1d7fb7;
--accent-cta-from: #1d7fb7;
--accent-cta-to: #2563eb;
--accent-soft: rgba(56,189,248,.13);
--accent-teal: #14b8a6;      /* gradient start — FILLS ONLY, never used as ink */
--accent-gradient: linear-gradient(135deg, var(--accent-teal), var(--accent-cta-to));  /* CTAs, avatar, active-item pill */
--warning: #d97706;          /* amounts due */
--danger: #d9434e;           /* unchanged */
--ok: #1f9a5f;               /* unchanged */
```

**Spacing** — keep existing `--space-1..6` (6/10/14/18/24/32) values; just relocate into the unified block.

**Radius (new):** `--radius-sm: 8px; --radius-md: 11px; --radius-lg: 14px; --radius-xl: 16px; --radius-pill: 999px;`

**Elevation (new scale; keep `--shadow` as an alias):**
```
--elev-card: 0 10px 30px -16px rgba(15,23,42,.30);
--elev-raised: 0 24px 60px -24px rgba(15,23,42,.50);
```

**Motion (new):** `--dur-fast: 150ms; --dur: 300ms; --ease: cubic-bezier(.16,1,.3,1);`

**Dark theme token set** (`body[data-theme="dark"]`), extending the existing override:
```
--canvas: #020617;           /* slate-950 */
--surface: #1e293b;          /* solid slate-800 — opaque, NOT frosted */
--surface-border: rgba(255,255,255,.07);
--ink: #f1f5f9;
--ink-muted: #64748b;
--ink-subtle: #94a3b8;
--warning: #fbbf24;          /* lightened so it stays legible on dark */
--elev-card: 0 12px 34px -16px rgba(0,0,0,.6);
/* chrome tokens unchanged — chrome is slate in both themes */
```

### 4.2 Fonts — self-host

- Add `static/fonts/` with `woff2` files for **Manrope** (400, 500, 600, 700, 800) and **Space Grotesk** (500, 600, 700) — Latin subset. (Note: weight 500 is added for both; the current CDN import omits it but the shell uses it.)
- Add `@font-face` declarations with `font-display: swap`.
- **Remove the `fonts.googleapis.com` `@import`** at `templates.py:16`.
- Serve via the existing Flask static route. Verify the files are bundled by PyInstaller for the packaged exe (add to the spec's data-files list if not auto-collected).

### 4.3 Icons — self-host Phosphor subset

- Source path data **directly from the `@phosphor-icons/core` package (MIT)** — never hand-typed (the brainstorm hit a truncated hand-inlined gear; this rule prevents a repeat).
- Subset (13): `house` (+ fill), `users`, `calendar-dots`, `receipt`, `gear`, `magnifying-glass`, `bell`, `caret-down`, `moon`, `sun`, `sign-out`, `user`, `user-plus`.
- Deliver as a single **inline SVG sprite** (`<symbol>` defs once at the top of `<body>`), referenced with `<svg class="ic"><use href="#i-house"/></svg>` and sized/colored via CSS (`currentColor`). One small Python helper (e.g. `icon(name, fill=False)`) emits the `<use>` markup.
- No CDN and no `@phosphor-icons/web` font at runtime (the unpkg font was a **mockup-only** convenience).

---

## 5. The Shared Chrome Reskin

Restyle existing classes; **do not change the DOM structure or `.app-body` flex-row layout.**

- **Header (`.header`)** → dark slate bar (`--chrome-bg`, optional `backdrop-filter` blur — allowed on chrome). Real logo + wordmark on the left; search pill, bell, doctor badge, theme toggle, EN/AR, logout on the right, all using the Phosphor subset (Regular).
- **Sidebar (`.nav-tabs`, 196px column)** → recolor from `#f3f7fb` to dark slate (`--chrome-bg` / `--chrome-bg-2`); keep width, section labels (`.nav-group-label` / `.nav-tabs-label`), and grouping.
- **Nav items (`.nav-tab` / `.nav-subtab`)** → slate-muted default; **active item** gets a soft `--accent-gradient` tint background, solid-blue accent text, an `inset` accent rail, and the **Fill-weight** icon (the only Fill usage).
- **Fills use the gradient, ink stays solid blue.** `--accent-gradient` (teal→blue) is applied only to the CTA button, the doctor avatar, and the active-item pill background. All text, rails, focus rings, and icons use the solid `--accent` blue — gradients never touch ink (legibility + logo-match).
- **Content canvas + data cards** → `--canvas` background; cards use `--surface` (solid), `--surface-border`, `--elev-card`, `--radius-lg`. No frosted glass on data.
- **Both themes** verified per the dark token set above.

---

## 6. Risks & Decisions to Confirm

1. **Global accent flip (teal → blue) — RESOLVED (user, 2026-06-15).** Re-pointing the solid `--accent` recolors *every* accent consumer app-wide (active tabs, focus rings, links, profile tabs), not just the shell. **Decision: flip the global solid accent to blue** for app-wide consistency against the blue shell, **and** add `--accent-gradient` (teal→blue) used on fills only (CTAs / avatar / active-pill). Ink stays solid blue everywhere. Stat-card gradient classes (`.stat-card-teal` etc.) are explicit and unaffected. **Verification follow-up:** screenshot inner surfaces (stat cards, tabs, focus rings) in both themes during implementation to catch any teal-specific tuning that the flip exposes.
2. **PyInstaller bundling** of the new `static/fonts/` (and sprite if externalized) for the packaged exe — must be verified, not assumed.
3. **`templates.py` is one giant Python string.** CSS edits are lower-risk than JS, but the file's known JS-escaping trap means any change near inline `<script>` must be render-checked. Phase 0 is CSS/markup, so risk is low — still smoke-render the portal.

---

## 7. Verification

- **Render:** the portal HTML renders without errors; no console errors (the file's escaping trap demands a render sweep even for CSS-only edits).
- **Visual smoke (Playwright):** screenshot the shell in **light + dark** at desktop width; confirm Editorial Slate chrome, blue accent, Fill-active item, solid data cards, legible due-amount in both themes. (Per the web-visual-smoke recipe: fresh temp DB → unlicensed gate needs a seeded active license to reach the portal.)
- **Offline check:** load the portal with no network; fonts and icons must render (proves self-hosting).
- **Tests:** full `python -m pytest tests/` stays green (check `$LASTEXITCODE`; summary is suppressed). No new behavior, so existing suite should be unaffected.
- **Packaged exe:** after the build, the self-hosted fonts/icons render in the WebView2 shell.

---

## 8. Units Touched

- `templates.py` — token consolidation (`:root`), font `@font-face` + remove CDN `@import`, icon sprite + helper, header/sidebar/nav reskin, dark-theme shell tokens.
- `static/fonts/` (new) — self-hosted woff2 subsets.
- (Possibly) static icon sprite file if not inlined; PyInstaller data-files entry for new static assets.
- No mobile, no Python logic, no DB, no API changes.

---

## 9. Next Step After This Spec

On approval → invoke **writing-plans** to produce the implementation plan (ordered, testable steps). Implementation happens on a fresh `feat/ui-overhaul-p0` branch, its own PR.
