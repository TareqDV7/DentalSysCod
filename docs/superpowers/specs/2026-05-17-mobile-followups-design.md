# Mobile follow-up sheet — design

## Goal

Bring the desktop's per-patient follow-up sheet to the Flutter mobile app so a doctor can log treatment entries during a visit (not just review them after). Today the mobile silently drops follow-ups from sync because there is no local model.

## Server reference (do not change)

- Table: `patient_followups` — columns: `id, patient_id, followup_date, tooth_no, diagnosis, treatment_procedure, procedure_id, price, discount, lab_expense, clinic_profit, payment, remaining_amount, notes, created_at, updated_at, is_deleted, entry_type, tooth_number, price_expr, discount_expr, lab_expense_expr, payment_expr`.
- Running balance (`remaining_amount`) is rewritten on every read and after every write by `_recompute_followup_balances(cursor, patient_id)`: cumulative `Σ (price − discount − payment)` walked in `(followup_date ASC, id ASC)` order. **Can be negative** (patient credit).
- Lab expense auto-creates a postponed `expenses` row with `source_type='followup'`, `reference_id=followup_id` — but only when the linked procedure has `requires_lab=1` and `lab_expense > 0`. Deleting the followup cascades the expense delete.
- The phone is allowed to write `clinic_profit` and `remaining_amount` — the server overwrites them on import via the recompute.

## Mobile scope — v1

Full CRUD on the follow-up sheet. Scoping concessions for v1 (parked, not removed):

| In v1 | Deferred |
|-------|----------|
| date, procedure (free-text), tooth_no, price, discount, lab_expense, payment, notes | procedure picker tied to `treatment_procedures` table |
| local recompute of `remaining_amount` | expression preservation in money fields (`*_expr`) |
| sync glue (register in `localToRemoteTable`, field mapping) | lab-expense auto-create on mobile (server creates it on sync re-pull) |
| edit + delete with confirmation | patient credit balance derived display |
|  | printable invoice on mobile |

Deferred items still sync correctly when the server is the source of truth — mobile just doesn't display/edit those derived/optional fields yet.

## Architecture

- **Model** `lib/models/followup.dart` — Dart class mirroring server columns.
- **DB schema** — bump `DatabaseService` version, add `followups` table + index on `patient_id`.
- **Service** `lib/services/followup_service.dart` — list/get/create/update/delete + local recompute helper. Recompute walks rows in `(followup_date ASC, id ASC)` and rewrites `remaining_amount` in a single sqflite transaction.
- **Sync glue** in `database_service.dart` — add `followups` to `localToRemoteTable`; the existing `internet_sync_service.dart` `_toServerRow` / `_fromServerRow` handle most of it; explicit field name fixes where needed.
- **UI** — new Follow-ups tab on `PatientDetailScreen`: list of rows (date · procedure · running balance) with row-tap → edit, FAB → add. Add/Edit screen `lib/screens/followup_edit_screen.dart` with the v1 fields.

## Sync semantics

- Mobile recomputes `remaining_amount` locally for immediate UX.
- On push, mobile sends rows with its locally-computed `remaining_amount`. The server's `_apply_sync_import` writes the rows and the server's next read fires its own recompute — server is canonical.
- On pull, the server-canonical `remaining_amount` overwrites the local cache.
- LWW by `updated_at` is unchanged.

## Local recompute algorithm (port from server)

```dart
double running = 0.0;
for (final row in entries sorted by (followup_date, id)) {
  running += (row.price - row.discount - row.payment);
  row.remaining_amount = (running * 100).round() / 100;
}
```

No clamp — negative values represent patient credit, same as server.

## Tests

- Unit test for `FollowupService._recompute` covering: empty list, single entry, multiple entries in order, out-of-order insertion, deletion, edit changing the date (re-order), patient-credit (negative balance).
- Widget test for the list rendering a known set of rows with the correct running balances.
- No live-API integration test (existing pattern — sync paths are covered server-side).

## Out of scope (v1)

- Expression preservation (`price_expr` etc.). Mobile sets to null on push; server preserves whatever it had locally if the mobile push is older by `updated_at`.
- Treatment procedure picker. Free-text only; `procedure_id` left null. Catalog picker is a v2 item.
- Mobile lab-expense auto-row. Server creates it on its side; phone re-pulls.
- Invoice print / patient statement / credit balance display.
