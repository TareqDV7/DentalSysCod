# Pre-Overhaul Fixes — Design

- **Date:** 2026-06-15
- **Branch:** `fix/pre-overhaul-ux`
- **Context:** A batch of correctness/UX fixes on existing surfaces, landed *before*
  the UI foundation overhaul. They go first because they touch the same single
  file (`templates.py`, ~7.9k lines) the overhaul will rewrite, and because we
  should not restyle behavior that's still broken.

## Scope (4 items, in build order)

### 1. Toast / notification component  *(keystone — build first)*

The app currently signals everything through native `alert()` / `confirm()` /
`prompt()` (41+ sites). We add a real **toast** (transient, non-blocking) as a
shared primitive. Item 2 depends on it, and it is the same notification system
the overhaul needs in Phase 2 — built once, kept.

- `showToast(message, type='info', opts)` — `type` ∈ `success|error|warning|info`.
- Fixed-position stacking container; auto-dismiss (default ~4s, errors longer /
  sticky); manual close button; max stack with oldest-evicted.
- Uses existing CSS tokens (`--ok`, `--danger`, `--warning`, `--accent`, `--panel`,
  `--line`, `--shadow`); light + dark via `data-theme`.
- RTL-aware (anchors flip with `currentLanguage`); messages passed pre-translated
  via `t()`.
- Compositor-friendly enter/exit (`transform` + `opacity`); honors
  `prefers-reduced-motion`.
- **Not** in scope here: migrating the 41 `confirm()`/`prompt()` blocking calls to
  a modal — that's overhaul Phase 2. New code uses the toast; old blocking dialogs
  stay until the modal sweep.

### 2. Duplicate patient finder + merge

`db_merge.py` copies patients **additively with no dedupe** (line 308) — correct,
because two real people can share a name and auto-fusing records is dangerous. So
this is a **human-reviewed** tool, not an auto-dedupe.

- **Decision (approved):** *merge records* is the primary action — fold the
  duplicate's appointments, visits, treatments, treatment-plan teeth, followups,
  billing, expenses, tooth chart, medical images, and credit transactions into the
  survivor, then delete the empty shell. **Delete** is the fallback for true empty
  duplicates.
- Backend (`dental_clinic.py`):
  - `GET /api/data/duplicate-patients` → groups of likely duplicates keyed on a
    normalized name (trim + collapse whitespace + lowercase), with per-patient
    record counts so the user can tell the empty shell from the real record.
  - `POST /api/data/merge-patients` `{survivor_id, duplicate_ids[]}` →
    reassign FK rows to survivor, recompute balances, delete shells. One
    transaction; roll back on failure.
- UI: Settings → Data Tools → "Find duplicate patients" → grouped review list,
  side-by-side with counts, pick survivor, Merge / Delete. Feedback via the toast.
- Tests: name normalization + grouping, merge reassigns every FK table, balances
  recomputed, delete-empty path, transaction rollback on error.

### 3. Odontogram correctness + add/remove/undo

- **Numbering:** keep FDI (clinician view, patient-right-on-left). Confirm with the
  user *visually* exactly what reads wrong (numbering system vs. label position vs.
  shapes) before changing — do not guess.
- **Drawing:** the tooth silhouettes are explicit placeholder art
  (`"refine visually in Task 9's review"`, templates.py:6331). **Hold the beautiful
  redraw for overhaul Phase 3** so we don't redraw twice; fix only what's *wrong*
  now (e.g. label placement / orientation), not what's merely unpolished.
- **Remove/undo:** the tooth popup toggles condition chips then Saves, so removal
  technically exists but reads as nothing. Make removal explicit (clear "remove"
  affordance on selected conditions), add remove-tooth-from-plan from this surface,
  and surface an undo affordance (toast with Undo) after a destructive save.

## Out of scope (later phases)

- Glassmorphic foundation, token hardening, icon set, self-hosted fonts (overhaul
  Phase 0).
- Real-time billing math preview (overhaul Phase 1).
- Migrating all blocking `confirm()`/`prompt()` to modals (overhaul Phase 2).
- Beautiful odontogram silhouette redraw + asymmetric dashboard (overhaul Phase 3).

## Verification

- `python -m pytest tests/` green (check `$LASTEXITCODE`); add tests for the
  duplicate finder/merge.
- Web visual smoke for toast + odontogram (Playwright recipe).
- No regressions: full pytest + `flutter test` if mobile odontogram is touched.
- Update README per the project working style.
