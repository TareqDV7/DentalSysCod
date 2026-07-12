# Per-Dentist Profit Reporting (Design Spec)

**Date:** 2026-07-12
**Status:** Approved design — ready for implementation plan.
**Sequencing:** follow-on to the now-complete 5-item roadmap (security →
testing → recall/reminder → unified gross profit → multi-dentist
attribution). Explicitly deferred during two earlier sub-projects:
`docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md` (Decision
6 — no reporting UI in that pass) and
`docs/superpowers/specs/2026-07-12-multi-dentist-attribution-design.md`
(attribution-only slice, no reporting UI). Both are now shipped, making
this possible.

## Context

`dentist_id` (nullable) already exists on `appointments`, `patient_followups`,
and `billing`. `users.is_dentist` and `GET /api/dentists` already exist. The
unified gross-profit formula lives in `dental_clinic.py`'s
`reports_summary()`/`reports_weekly()` routes: charge-based (net-of-discount
price/subtotal, not cash-collected), combining `patient_followups` and
`billing`, minus `lab_expense` and general clinic expenses (excluding the
auto-mirrored lab-expense rows in the `expenses` table, to avoid double
counting — see the gross-profit spec for the full rationale).

General clinic expenses (rent, salaries, etc.) are not attributable to any
one dentist — allocating them per-dentist would need an arbitrary rule
(evenly split? by revenue share?) nobody has asked for.

## Goal

Show, per date range already selectable in the existing Reports tab, a
breakdown table of revenue and margin attributed to each dentist — "who
earned what this period."

## Decisions (2026-07-12, all user-approved during brainstorming)

1. **Full breakdown table, not a single-dentist filter.** One row per
   dentist for the currently-selected period, not a dropdown that narrows
   the existing clinic-wide numbers to one dentist at a time.

2. **Unattributed work (`dentist_id IS NULL`) gets its own "Unassigned"
   row**, not silently excluded. Keeps the table's totals reconciling with
   the clinic-wide numbers already shown above it, and makes attribution
   gaps visible (e.g. old records from before this feature, or front-desk-
   entered work nobody assigned) rather than hiding them.

3. **Surfaces in the existing Reports tab**, as a new table below the
   existing stat-grid, reusing whatever period is currently selected
   (summary date-range or weekly view — same underlying data, both
   endpoints get the same new field). No new tab, no new period-selection
   UI to build.

4. **Formula: revenue minus the dentist's own `lab_expense` only — no
   general-expense allocation.** Each row shows `revenue` (net-of-discount
   charge from their follow-ups + billing) and `gross_margin` (`revenue −
   their lab_expense`). This is deliberately *not* the full
   `clinic_gross_profit` figure (which also subtracts general expenses) —
   general overhead isn't any one dentist's cost to bear, and inventing a
   split would be a guess this spec explicitly declines to make.

## API contract

Both `/api/reports/summary` and `/api/reports/weekly` gain a new
`dentist_breakdown` array field, using the exact same date-range parameters
each route already accepts:

```json
"dentist_breakdown": [
  {"dentist_id": 3, "dentist_name": "Dr. Amy", "revenue": 450.0, "lab_expense": 30.0, "gross_margin": 420.0},
  {"dentist_id": null, "dentist_name": "Unassigned", "revenue": 120.0, "lab_expense": 0.0, "gross_margin": 120.0}
]
```

Sorted by `dentist_name` ascending, **with the Unassigned row always last**
regardless of where it would alphabetically fall — it's a catch-all bucket,
not a named participant, and shouldn't visually blend in with real dentists.

Query shape (conceptually — actual SQL groups `patient_followups` and
`billing` separately per dentist, then merges, since they're two different
tables with independent date-range columns, same pattern
`reports_summary()`/`reports_weekly()` already use for the clinic-wide
totals):

```sql
-- per dentist, per table, within the existing date-range clause:
SELECT dentist_id,
       SUM(price - discount) AS followup_net_charge,
       SUM(lab_expense) AS lab_expense
FROM patient_followups
WHERE is_deleted = 0 AND <existing date clause>
GROUP BY dentist_id

SELECT dentist_id,
       SUM(subtotal - discount) AS billing_net_charge
FROM billing
WHERE <existing date clause>
GROUP BY dentist_id
```
merged in Python by `dentist_id` (including `NULL`), joined against
`users.display_name` for named dentists, with `NULL` labeled `"Unassigned"`.

## UI

New table in the Reports tab, directly below the existing stat-grid,
appearing for both the date-range summary view and the weekly view (same
`renderReportStats`-style render hook, extended to also paint this table
from the same response payload). Columns: Dentist, Revenue, Lab Expense,
Gross Margin. Re-renders whenever the existing report data reloads — no new
fetch, no new period picker.

## Testing

- Desktop only — no mobile Reports-tab UI exists to extend.
- Query correctness: revenue/lab_expense/gross_margin computed correctly per
  dentist across mixed follow-up + billing data; a dentist with follow-ups
  but no billing (and vice versa) still gets a correct combined row; the
  Unassigned bucket correctly aggregates `dentist_id IS NULL` rows from both
  tables and sorts last regardless of name.
- UI presence test (matching this session's established style): the new
  table markup and its render call exist in `templates.py`.

## Non-goals (explicitly out of scope for this spec)

- General-expense allocation per dentist (Decision 4) — no split is
  invented; `gross_margin` is pre-overhead.
- A single-dentist filter/dropdown view (Decision 1) — full breakdown table
  only.
- Mobile Reports-tab equivalent — no such UI exists on mobile today for this
  to extend; out of scope.
- Per-dentist appointment/scheduling views — a separate, larger, not-yet-
  started future spec (the other deferred half of the original
  multi-dentist roadmap item).
