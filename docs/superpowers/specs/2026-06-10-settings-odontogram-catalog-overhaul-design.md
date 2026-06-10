# Settings, Odontogram & Catalog Overhaul — Design

**Date:** 2026-06-10
**Branch:** `feat/licensing-overhaul`
**Status:** Approved (design) — pending spec review

## Summary

Four largely independent workstreams requested by the doctor:

1. **Settings redesign (desktop)** — regroup the flat `#support` tab into labelled
   sections with one consistent card style; make the **Audit Log foldable**.
2. **Odontogram chart fix (desktop + mobile)** — fix what reads as "wrong" in the
   tooth chart: redraw the four tooth silhouettes so they're clearly distinct and
   recognizable, label FDI numbers cleanly, add a quadrant midline, ensure
   upper/lower alignment, and stop the arch mirroring under Arabic RTL.
3. **Multiple conditions per tooth (desktop + mobile)** — a single tooth can carry
   several findings at once (e.g. cavity **and** crown), each describable.
4. **Empty the catalogs (desktop + mobile)** — ship fresh installs with no demo
   procedures/conditions, and clear the catalogs in the current (live) database,
   propagating the wipe to cloud + phone via sync. Patient data is preserved.

Non-goals: no changes to billing, follow-up ledger math, licensing, or sync
transport. Mobile Settings is untouched (it has no Audit Log). Tooth-surface
(mesial/occlusal/…) charting was explicitly **out of scope** — whole-tooth
multi-tags only.

---

## 1. Settings redesign + foldable Audit Log (desktop only)

### Current state
`templates.py` `#support` tab is a flat stack of `<h3>` + `section-card` blocks:
`Account → Cloud Sync → Bluetooth sync → Data Tools → Audit Log (always-open full
table) → Help`, with inconsistent `<h3>` margins and no grouping.

### Design
Regroup into **four labelled groups**, one consistent card style, even spacing:

| Group | Contains |
|---|---|
| **Account** | Change password |
| **Sync & Connectivity** | Cloud Sync status + Bluetooth sync |
| **Data** | Data Tools (export / merge / replace), **Clear catalogs** (§4), **Audit Log** |
| **Help** | Support content + Refresh Help |

- **Audit Log** is wrapped in a **collapsed-by-default `<details>`** reusing the
  existing `form-panel` / `<summary>` pattern (same as the expense & payment
  forms). Its rows load on first expand (the existing
  `/api/audit-logs?limit=200` fetch is moved into the expand handler / kept lazy).
- A lightweight group heading style (existing `page-header` / `<h3>` tokens, no new
  framework). Dark mode + Arabic RTL theming preserved via existing `data-i18n` /
  `data-en` / `data-ar` attributes.
- **No behavior change** to any setting/action — layout and disclosure only.

### Files
- `templates.py` — restructure the `#support` block; add i18n keys for any new
  group headings (EN + AR objects).

---

## 2. Odontogram chart fix — numbering + shapes (desktop + mobile)

### Diagnosis first
The FDI arrays are anatomically standard
(`18 17 16 15 14 13 12 11 │ 21 22 23 24 25 26 27 28` upper;
`48 47 46 45 44 43 42 41 │ 31 32 33 34 35 36 37 38` lower) and align 18-over-48 …
28-over-38. Before redrawing, **capture live screenshots** (light/dark, EN/AR) of a
patient's chart to confirm the real defect. Prime suspects:
- crude, near-identical tooth silhouettes that don't read as distinct teeth;
- the SVG arch mirroring under Arabic RTL (clinician's view should never mirror).

### Design
- **Redraw the four tooth shapes** (`TOOTH_PATHS` in `templates.py`; `_buildPath`
  in `odontogram_view.dart`) so molar / premolar / canine / incisor are clearly
  recognizable and distinct.
- **Clean FDI number label** on every tooth; **quadrant midline separator** between
  the two quadrants of each arch; verified upper/lower vertical alignment.
- **Lock the arch to LTR** (`direction: ltr` on the arch container / `Directionality`
  override on the mobile arch) so Arabic does not mirror the anatomical order.
- Keep the existing purple *has-plan* dot and amber *unpaid-balance* dot.

### Files
- `templates.py` — `TOOTH_PATHS`, `buildToothRowSvg`, `buildToothArchSvg`, arch CSS.
- `clinic_mobile_app/lib/screens/odontogram_view.dart` — `_ToothPainter`,
  `_ToothCell`, `_ArchRow`, arch labels.

---

## 3. Multiple conditions per tooth (desktop + mobile)

### Approach (chosen): one table, multiple rows per tooth
`patient_tooth_chart (id, patient_id, tooth_no, condition_id, note, …)` already
exists and is already in `SYNC_TABLES`. Drop the current "dedupe to a single row"
logic so a tooth can hold **N rows — one per condition, each with its own note**.
No new table; rides last-write-wins + tombstones unchanged.

- Duplicate `(patient_id, tooth_no, condition_id)` tags are prevented in app logic
  (SQLite can't cheaply add a UNIQUE constraint to the existing table).

*Rejected alternative:* a separate `tooth_chart_conditions` join table — extra
migration and sync surface for no functional gain.

### API changes (`dental_clinic.py`)
- `POST /api/patients/<id>/tooth-chart` accepts
  `{ "tooth_no": "16", "conditions": [ {"condition_id": 3, "note": "PFM"}, … ] }`
  and **replaces** that tooth's full set: insert new rows, tombstone removed rows,
  update notes on kept rows. `conditions: []` clears the tooth (all rows tombstoned).
  - Backward tolerance: a legacy `{condition_id, note}` body is treated as a
    single-element `conditions` list so older callers don't 500.
- `GET /api/patients/<id>/tooth-chart` returns, per tooth:
  ```json
  "16": {
    "conditions": [
      {"condition_id": 3, "condition_name": "Crown", "color": "#a855f7", "note": "PFM"},
      {"condition_id": 4, "condition_name": "Root canal", "color": "#f59e0b", "note": null}
    ],
    "has_plan": true,
    "unpaid_balance": 120.0,
    "source": "chart"
  }
  ```
  The legacy single `condition_id` / `condition_name` / top-level `color` keys are
  **removed** (deliberate response-shape change; all consumers are in this repo).
- `DELETE /api/patients/<id>/tooth-chart/<tooth_no>` unchanged (clears all rows for
  the tooth + tombstones) — already loops over rows.
- Legacy follow-up / plan auto-adopt still surfaces a tooth with an empty
  `conditions: []` so badges show before any condition is charted.

### Display (both platforms)
- A tooth with **one** condition fills with that color (as today). With **multiple**,
  the silhouette fill is split into **stacked horizontal color bands**, one per
  condition (clip to the tooth path, paint N equal bands top→bottom in catalog
  order). Plan/unpaid dots unchanged.
- Legend unchanged (lists active conditions).

### Tap popup (both platforms)
- **Condition toggle-chips** — every active catalog condition rendered as a
  color-coded chip; tap to select/deselect (multi-select).
- For each **selected** condition, a small inline **note** input so each finding is
  describable ("cavity: distal", "crown: PFM 2024").
- Save → POST the full `conditions` array (replace). "Clear" deselects all.
- Existing **+ Log treatment** and **+ Add to plan** actions preserved.

### Files
- `dental_clinic.py` — `patient_tooth_chart_collection` GET + POST.
- `templates.py` — `buildToothRowSvg` (banded fill), `openToothPopup` +
  save handler (multi-select chips + per-condition notes), small popup markup/CSS.
- `clinic_mobile_app/lib/models/tooth_chart_entry.dart` — `conditions` list.
- `clinic_mobile_app/lib/services/tooth_chart_service.dart` — `parseToothChart`
  (new shape) + `setTooth` → replace-set call.
- `clinic_mobile_app/lib/screens/odontogram_view.dart` — banded `_ToothPainter`,
  multi-select `_ToothSheet`.

---

## 4. Empty the catalogs (desktop + mobile)

### Stop seeding (fresh installs start empty)
- Remove `default_procedures` (9 rows) and `default_tooth_conditions` (8 rows) and
  their `executemany` `INSERT OR IGNORE` calls from `init_database()` in
  `dental_clinic.py`.
- Mobile has **no** local catalog seed (it receives the catalog via sync) — verified;
  nothing to change there.

### Clear the current (live) database
- Add a **"Clear catalogs" action** in **Settings → Data → Data Tools** (desktop),
  behind a confirm dialog. It soft-deletes (`active = 0`) **and tombstones** every
  row in `treatment_procedures` and `tooth_conditions`, so the wipe propagates to
  the cloud node and the phone on the next sync.
  - New endpoint `POST /api/data/clear-catalogs` (login-required, **disabled on the
    cloud node** like the other Data Tools), returning counts cleared.
  - Reuses the existing `record_tombstone` + `active=0` soft-delete path so sync
    semantics are identical to deleting one catalog row from the admin screen.
- Patient data (patients, visits, billing, follow-ups, appointments, tooth charts)
  is **untouched**. Procedure/condition **names already written onto historical
  ledger rows** are stored as text and remain intact.

### Implication (confirmed with user)
With conditions cleared, the odontogram tap popup and the follow-up procedure picker
start **empty until the doctor adds their own entries** — the intended clean slate.

### Files
- `dental_clinic.py` — remove seeds; add `clear-catalogs` endpoint.
- `templates.py` — "Clear catalogs" button + confirm + result line in Data Tools;
  i18n keys.

---

## Testing

**Python (`pytest`)**
- `test_tooth_chart_api.py` — rewrite for the `conditions[]` shape; multi-condition
  set, replace, partial-remove, clear, duplicate-guard, legacy single-body tolerance.
- `test_tooth_chart_badges.py` — badges + empty `conditions[]` on auto-adopt.
- `test_tooth_chart_sync.py` — multiple rows per tooth export/import + tombstones.
- New `test_data_tools_api.py` cases — `clear-catalogs` (auth gate, cloud-disabled,
  soft-delete + tombstone counts, patient data preserved).
- `test_catalog_migration.py` / any seed-count assertion — adjust for empty seed.
- API fuzz (`test_api_fuzz.py`) — the new POST shape never 500s on malformed input.

**Flutter (`flutter test` + `dart analyze`)**
- `tooth_chart_service` parse test — new `conditions[]` shape.
- Odontogram widget test — multi-condition render + multi-select save.

**Manual / visual**
- Screenshot the redesigned Settings (foldable Audit Log) and the redrawn chart
  (single + multi condition, light/dark, EN/AR) per the web-visual-smoke recipe.

Full `pytest`, `flutter test`, `dart analyze`, and `ruff` must stay green.

---

## Build order (for the plan)
1. Catalog clear (seeds removed + endpoint + button) — smallest, unblocks a clean DB.
2. Multi-condition model — API GET/POST + tests (backend contract first).
3. Desktop chart: shape redraw + banded fill + multi-select popup.
4. Mobile parity: models/service + painter + sheet.
5. Settings regroup + foldable Audit Log.
6. Full test + visual sweep.
