# Unified Clinic Gross Profit (Design Spec)

**Date:** 2026-07-11
**Status:** Approved design — ready for implementation plan.
**Sequencing:** fourth of 5 planned sub-projects (security → testing → recall/reminder
system → **unified clinic gross profit** → multi-dentist support). Security, testing,
and recall/reminder are all DONE — see memory `project_security_hardening_2`.

## Context

Two different, inconsistent "profit" numbers already exist in the codebase, both
returned by `/api/reports/summary` and `/api/reports/weekly`
(`dental_clinic.py:4260-4310`):

1. `clinic_gross_profit` = `SUM(patient_followups.clinic_profit)`, where
   `clinic_profit = price − discount − lab_expense` per row. **Follow-up-sheet-only**
   — `billing` table revenue is not represented at all.
2. `profit` = `revenue − expenses_total`, where `revenue` is the already-unified
   figure from the 2026-06-12 unified-ledger project (follow-up payments + billing
   `paid_amount`, both ledgers). This omits `lab_expense` entirely.

Both numbers are rendered **side by side** in the desktop Reports tab today
(`templates.py:2757` "Clinic Gross Profit" stat-card, `templates.py:2762` "Profit"
stat-card) — a real, visible inconsistency, not just an internal API quirk. The
`billing` table (`dental_clinic.py:1085-1101`) has zero cost fields (only
`amount`/`subtotal`/`discount`/`paid_amount`/`balance_due`), so billing-sourced
revenue currently contributes to any profit figure with implicitly $0 cost.

The mobile app (`clinic_mobile_app/lib/services/report_service.dart`) has a
**third**, independent formula: an offline fallback (`_localWeeklyReport`/
`_localMonthlyReport`, used only when the API is unreachable) that computes
`profit = revenue − expenses − labExp` from its local `visits` table (the synced
mirror of `patient_followups`) — no billing involved at all.

Depo/inventory (`inventory.py`, `unit_cost`/`pack_cost` per item,
`dental_clinic.py:992, 3639-3647`) tracks consumable cost but nothing currently
subtracts it from any profit calculation.

## Goal

One correct, consistent gross-profit figure, computed the same way everywhere it's
shown: desktop API, desktop UI, mobile API-backed view, and mobile's offline
fallback.

## Decisions (2026-07-11, all user-approved during brainstorming)

1. **Cost scope: discounts + lab expense + general clinic expenses.** Inventory
   consumable cost is explicitly **out of scope** — no link exists today between a
   treatment and the inventory items consumed for it, and adding one is a much
   larger project. A dedicated billing-side cost/lab-expense field is also **out of
   scope** — billing revenue's cost stays at $0 for now, same as today; only the
   *aggregation* is being fixed, not adding new cost tracking. Both are reasonable
   later follow-ups, not blockers for this pass.

2. **Formula (charge-based, not cash-collected-based):**
   ```
   gross_profit = (Σ followup.price + Σ billing.subtotal)
                − (Σ followup.discount + Σ billing.discount)
                − Σ followup.lab_expense
                − expenses_total
   ```
   Charge-based (what was billed/earned) rather than cash-collected-based (what's
   actually been paid) — chosen because a large unpaid patient balance would make a
   cash-basis "profit" number misleadingly low even though the clinical work was
   done and charged. This also directly extends the existing per-row
   `clinic_profit` formula (`price − discount − lab_expense`) rather than
   introducing a different accounting basis. `expenses_total` (paid + postponed
   from the `expenses` table) is unchanged from today's existing calculation —
   still date-range-filtered the same way — **except that the term feeding this
   formula specifically must exclude `source_type='followup'` rows** (found
   during implementation, not anticipated here): a lab-requiring follow-up
   already auto-mirrors its `lab_expense` into the `expenses` table as a real
   payable, so subtracting both the direct `lab_expense` column AND that mirrored
   `expenses` row would double-count the same cost. The existing
   `expenses`/`expenses_paid`/`expenses_postponed` API fields (used for their own
   display cards) are untouched by this exclusion — only the profit formula's
   internal general-expenses term is filtered.

3. **Surfaces: dashboard tile + Reports tab (both existing surfaces get the fix),
   single number, no cost breakdown.** No new UI element — this replaces what's
   already shown, doesn't add a new view. A cost breakdown (discounts / lab_expense
   / expenses shown separately) was explicitly declined — can be a later ask.

4. **API contract: keep both `clinic_gross_profit` and `profit` keys, same value.**
   Removing either key would break an existing consumer (`profit` is required by
   mobile's `WeeklyReport`/`MonthlyReport` Dart models in `report_service.dart`).
   Both keys return the identical unified figure going forward — the *duplication*
   isn't being removed from the API, only the *divergence*. The desktop UI's
   redundant stat-card is removed (see Decision 5) so a human only ever sees one
   number, even though the API still carries two equal keys for backward
   compatibility.

5. **Desktop UI: collapse the two stat-cards into one.** Delete the "Profit"
   stat-card (`templates.py:2762`, `id="report-profit"`), keep "Clinic Gross
   Profit" (`templates.py:2757`) as the single visible figure — it's the more
   descriptive label of the two. The underlying JS (`setText('report-profit', ...)`)
   is removed along with the card; `setText('report-clinic-gross-profit', ...)`
   stays, now fed the corrected value.

6. **Mobile offline fallback is IN SCOPE** (user's explicit choice over leaving it
   as a known-divergent fallback). `_localWeeklyReport`/`_localMonthlyReport` in
   `report_service.dart` get ported to the same formula, reading from the local
   `visits` and `billing_records` sqflite tables instead of the API.
   **Open question flagged for the implementation plan, not resolved here:**
   mobile's local `visits` table (`database_service.dart:298-311`) has **no
   discount column** — only `price`/`lab_expense`/`payment`. Whether the synced
   `price` value already reflects the post-discount charged amount (in which case
   the local formula needs no discount subtraction for the follow-up side) or the
   pre-discount price (in which case discount data is simply missing locally and
   either needs syncing down or the local fallback accepts a known small
   inaccuracy) must be verified against the actual sync-mapping code before the
   plan writes the Dart query. `billing_records` (`database_service.dart:314-329`)
   DOES have `subtotal`/`discount`/`paid_amount` locally, so the billing side of
   the formula has no such gap.

## Testing

- Desktop: extend/fix whatever existing tests assert today's `profit`/
  `clinic_gross_profit` values (there should be existing coverage on
  `/api/reports/summary` and `/api/reports/weekly` given these fields already
  exist) to assert the new unified formula, with fixtures mixing follow-up-sheet
  AND billing rows so the "billing revenue was previously invisible to profit"
  bug is actually exercised and would fail on the old code.
- Mobile: new Dart test(s) for `_localWeeklyReport`/`_localMonthlyReport`'s
  corrected formula, once the discount-column question (Decision 6) is resolved
  during planning.
- Manual/visual: confirm the Reports tab only shows one profit stat-card after the
  desktop UI change (Decision 5).

## Non-goals (explicitly out of scope for this spec)

- Inventory/consumable cost subtraction (Decision 1) — no treatment↔inventory
  consumption link exists yet; separate future project.
- A cost field on `billing` invoices (Decision 1) — billing revenue's cost stays
  $0 for now, matching today's behavior; only the aggregation bug is fixed.
- A cost breakdown in the API/UI (Decision 3) — single number only, matches
  today's UI shape.
- Multi-dentist profit attribution (roadmap item 5, its own future spec) — this
  spec's unified figure stays clinic-wide, not per-dentist.
