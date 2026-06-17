# UI Overhaul Phase 3 — Editorial Dashboard + Color-Coded Badges (Design)

**Date:** 2026-06-17
**Branch:** `feat/ui-overhaul-p3` (off `main`, which includes Phase 0 PR #8, Phase 1 PR #9, Phase 2 PR #10)
**Phase:** 3 of 4 — the **final** UI/UX-overhaul phase. (4-phase plan; see prior phase specs in this directory.)
**Status:** Approved design (brainstormed via superpowers + visual companion, 2026-06-17).

---

## 1. Problem

Two surfaces still read as "default", undoing some of the P0–P2 elevation:

1. **Status badges are a mess under the hood.** Two redundant hardcoded palettes coexist — a semantic set (`badge-success/warning/danger/info`, `templates.py` ~945) and a near-identical status set (`badge-active/pending/secondary/blocked/neutral/muted`, ~1708). Same hex values, duplicated. **None use P0 tokens.** There are **no `body[data-theme="dark"]` badge rules**, so light pastel chips sit on the dark slate cards and look unfinished. And `renderStatusBadge()` (~5170) maps statuses incoherently: `cancelled` → `badge-pending` (amber, reads like a warning) while `pending` → `badge-secondary` (blue).

2. **The dashboard is a default grid.** `#dashboard` (~2213) is a uniform 4-column `.stats-grid` of KPI cards followed by a single full-width "Recent Appointments" table. No hierarchy, no point of view, no "today at a glance" focus — exactly the "dashboard-by-numbers" anti-pattern.

## 2. Goals / Non-Goals

**Goals**
- **Badges:** collapse to **one semantic palette on P0 tokens** with dark-theme variants (WCAG-AA contrast) and a **coherent status mapping** (cancelled ≠ pending). Single source of truth across appointment status, payment status, and the active/lab badges.
- **Dashboard:** restructure into an **editorial two-column** layout (Option C) — a narrow left rail (stacked KPIs + quick actions) and a wide right column whose centerpiece is a new **Today's Schedule** panel above the (restyled) Recent Appointments.
- **Light additions only, from existing endpoints** — no new server work.
- End state: a dashboard that "looks believable in a real product screenshot," and badges that read correctly at a glance in both themes.

**Non-Goals**
- **Odontogram** — stays hidden (`ODONTOGRAM_ENABLED = false`, ~7109; data/endpoints intact). A redraw is a separate, later spec→plan→PR if pursued. Explicitly **not** in P3.
- **No new backend endpoints, no DB/API changes, no charting library.**
- **Mobile (Flutter)** — out of scope; P0–P3 are all desktop-web (`templates.py`).
- Re-theming non-dashboard tabs (patients/appointments/billing/reports) beyond the badge change.

## 3. Existing infrastructure to build on

- **Badge base** `.badge` (~934) + the two palettes (~945, ~1708). Call sites: `renderStatusBadge(status, text)` (~5170) used by recent-appointments (~5289) and the appointments table (~5483); literal `badge-pending`/`badge-muted` and `badge-active`/`badge-blocked` for the procedure **requires-lab** and **active/inactive** chips (~4480/4483).
- **Dashboard markup** (~2213): `.section-card` header (title + Download Backup) → `.stats-grid#stats-grid` with 4 gradient KPI cards (`stat-card-teal/blue/green/amber`, ~2227) → `.section-card.table-shell` with `#recent-appointments-table` / `#recent-appointments-body` (~2258). Loader: `loadDashboard()` (~5218) already toggles `.stats-grid.is-loading` and skeletons the recent table (P2).
- **Responsive breakpoints** for `.stats-grid`: 2-col ~1305, 1-col ~1319.
- **Endpoints (all existing):** `GET /api/stats` (KPIs), `GET /api/appointments/recent` (latest 10), `GET /api/appointments` (ALL appointments with `patient_name`, `appointment_date`, `status`, treatment type, ordered by date) — `dental_clinic.py` ~3021 / ~2923. Today's Schedule is a pure client-side filter over `/api/appointments`.
- **P2 skeleton helpers:** `renderSkeletonRows(colSpan, {rows, announce})` (~5205) + `.skeleton`/reduced-motion machinery — reused for the new panel's loading state.
- **P0 tokens:** `--accent #38bdf8`, `--accent-strong #1d7fb7`, `--accent-gradient`, `--danger #d9434e`, `--warning #d89e1f`, `--surface`, `--surface-border`, `--radius-*`, `--elev-raised`, `--ease`.

## 4. Design

### 4.1 Badge consolidation (Option A)

**One semantic palette**, defined once on P0 tokens, with light + dark variants:

| Semantic class | Meaning | Light (bg / text) | Dark (translucent bg / lighter text) |
|---|---|---|---|
| `badge-success` | completed, paid, active procedure | green | `rgba(green,.16)` / light green |
| `badge-warning` | pending payment, postponed, requires-lab | amber (`--warning`) | `rgba(amber,.20)` / light amber |
| `badge-danger`  | cancelled, no-show, inactive procedure (via `badge-blocked`) | red (`--danger`) | `rgba(red,.18)` / light red |
| `badge-info`    | scheduled, confirmed | blue (`--accent`) | `rgba(accent,.18)` / light blue |
| `badge-neutral` | unknown / other / "no lab" (`badge-muted`) | slate | `rgba(slate,.18)` / light slate |

- The exact dark RGBA/text values are finalized in the plan against WCAG-AA (≥ 4.5:1 for the badge text on its chip) using the values previewed in the companion as the starting point.
- **Legacy aliases stay as thin alias rules.** `badge-active → success`, `badge-secondary → info`, `badge-pending/muted → warning|neutral`, `badge-blocked → danger`. This means the literal-class call sites (~4480/4483) and any other consumers keep working **untouched** — no call-site churn, no behavior change there. The redundant duplicate *definitions* are removed; the names survive as aliases.
- **`renderStatusBadge()` remapped** to the coherent mapping: `scheduled|confirmed → badge-info`; `completed|paid|active → badge-success`; `pending|postponed → badge-warning`; `cancelled|no_show|no-show → badge-danger`; else `badge-neutral`. **Cancelled is no longer amber** — it was `badge-pending`, now red `badge-danger`. `postponed` stays amber (a recoverable deferral, matching its expense-payment meaning), so it does not collide with the terminal cancelled/no-show states.

### 4.2 Dashboard — editorial two-column (Option C)

Replace the single-column `#dashboard` body with a **two-column shell** inside the existing `.screen-shell`:

- **Left rail (narrow, ~280–320px):**
  - The 4 KPIs **stacked vertically** (Patients, Today's Appointments, Today's Visits, Today's Revenue), keeping their P0 gradient treatment and existing element IDs (`#total-patients`, `#today-appointments`, `#total-visits`, `#total-revenue`) so `loadDashboard()` keeps populating them unchanged.
  - A **Quick Actions** cluster: Add Patient, New Appointment, Download Backup — wired to the **existing** handlers (`showAddPatientModal()`, the appointment add flow, `downloadBackup()`).
- **Right column (wide, focal):**
  - **Today's Schedule** panel (new) — the editorial centerpiece: today's appointments, time-ascending, each row showing time · patient · treatment · status badge. Empty state when none today.
  - **Recent Appointments** — the existing table, moved beneath and restyled to match (keeps `#recent-appointments-table`/`-body`).
- Bento feel via varied tile sizing, the P0 elevation/depth tokens, and the gradient KPIs anchoring the rail. **No new colors** beyond the P0 token set.

### 4.3 Data flow (existing endpoints only)

- **KPIs:** unchanged — `loadDashboard()` → `GET /api/stats`, writes the same element IDs.
- **Today's Schedule:** new `loadTodaySchedule()` → `GET /api/appointments`, filter rows whose `appointment_date` falls on the local "today", sort ascending by time, render via the same field accessors the recent renderer uses + `renderStatusBadge`. Loading state uses `renderSkeletonRows(...)`; failure degrades to an inline error row (reusing `renderStateRow` error kind); empty → a friendly "No appointments today" state.
- **Recent:** unchanged — `GET /api/appointments/recent`.
- Both new fetches run **in parallel** with the stats fetch in `loadDashboard()` (no waterfall).

## 5. Cross-cutting

- **Dark theme:** badges get explicit `[data-theme="dark"]` variants; the two-column shell uses existing themed surfaces. Both themes must look intentional.
- **EN/AR (RTL):** any new strings ("Today's Schedule", "Quick Actions", quick-action labels, empty/loading text) added to **both** the `en` and `ar` translation dicts. The two-column shell must mirror under `dir="rtl"` (use logical properties / `inset-inline`, as the badge alias rules already do).
- **Reduced-motion:** no new always-on motion; any hover/elevation transitions respect the existing `prefers-reduced-motion` block. Skeleton shimmer already silenced there.
- **Responsive:** below ~720px the two columns **stack** (left rail on top), reusing/extending the existing `.stats-grid` breakpoints (~1305/~1319). KPIs may return to a horizontal row on narrow widths.
- **JS-escaping trap:** all new inline JS avoids backslash escapes (normal Python string); verified by the render sweep (see `reference_templates_js_escaping`).

## 6. Testing (same shape as P0–P2)

- **pytest substring sentinels** — new `tests/test_ui_phase3.py`:
  - Badges: each semantic class present; `body[data-theme="dark"] .badge-` dark variants present; legacy aliases still defined; `renderStatusBadge` maps `cancelled`→`badge-danger` (and NOT to `badge-pending`/`badge-warning`); duplicate hardcoded definitions removed.
  - Dashboard: two-column container class present; `Today's Schedule` panel + `function loadTodaySchedule(` present; quick-actions block present; KPI element IDs preserved.
  - i18n: new keys present in both `en` and `ar` dicts (count ≥ 2 each).
- **Render/escaping sweep:** `python -c "import templates; ..."` — template imports; dialog invariant unchanged (`alert(`=0, `confirm(`=0, `prompt(`=2).
- **Full suite:** `python -m pytest tests/` exit 0, no regressions.
- **Playwright behavioral smoke** (gated on a seeded active license; see `reference_web_visual_smoke`): dashboard renders two-column; Today's Schedule populates from `/api/appointments`; badge colors correct in light **and** dark; RTL mirrors; <720px stacks; **zero JS console errors**.

## 7. Risks / open questions

- **"Today" boundary:** filter on the client's local date from `appointment_date`. Acceptable for a single-clinic desktop app; documented.
- **Left-rail width vs. small laptops:** validate the rail doesn't crowd the schedule at 1024px; the stack breakpoint is the safety valve.
- **Badge alias coverage:** the plan must grep every `badge-*` consumer to confirm the alias set is complete before deleting duplicate definitions (avoid an uncolored chip).
- This is the **last** overhaul phase; on merge the 4-phase initiative is complete (odontogram redraw remains an optional separate effort).
