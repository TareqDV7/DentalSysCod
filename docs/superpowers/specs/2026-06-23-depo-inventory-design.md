# Depo (Inventory / Stock) — Design Spec

**Date:** 2026-06-23
**Branch (proposed):** `feat/depo-inventory`
**Status:** Approved. Expiry confirmed **opt-in per item** (user, 2026-06-23). Ready for `writing-plans` → TDD implementation.

## 1. Problem & Goal

The dentist wants a **Depo** (storeroom / inventory) so the clinic can:

1. Add a stock item (e.g. toothpick, anesthetic, composite) with a starting quantity.
2. Link items to catalog procedures and set **how much each procedure consumes**.
3. Have stock **auto-decrement** when a procedure is recorded, with a **low-stock warning**.
4. See **material cost** as insight — without changing the existing money math.

The feature must fit the existing app: a single-clinic Flask/SQLite desktop server (`dental_clinic.py`), a Flutter mobile companion, and the desktop↔cloud↔mobile sync layer.

## 2. Decisions (locked in brainstorming)

| Area | Decision |
|---|---|
| Deduction | **Auto-deduct on procedure record + warn** when an item hits its low-stock threshold or goes negative. Never block a clinical record over a stale count. |
| Platform | **Desktop = full management. Mobile = read-only view** (stock levels, low-stock, expiring-soon). Procedures recorded on mobile still deduct (server-side, using defaults). |
| Unit model | **Per-item.** Three shapes (see §4.1). The canonical stored unit (`base_unit`) may be a **count** (carpule, compule, piece) or a **measure** (ml, g). |
| Consumption | Each procedure↔item link has a **default consumption**, **adjustable at the point of recording** (desktop). Mobile uses the default. |
| Restock | Simple **"Add stock"** with optional cost + (optional) expiry; updates on-hand and **weighted-average** cost. |
| Cost vs profit | **Insight only.** Material cost is shown in reports; it does **not** touch `clinic_profit` or the `expenses` table. |
| Expiry | **Lightweight, opt-in per item** via a "Track expiry" checkbox. When on: capture expiry per restock batch; surface an **expiring-soon / expired** list. No FEFO/batch-depletion in v1. |
| Corrections | **Recount** ("Adjust count" → posts an adjustment movement) and **Write-off** (breakage / contamination / expired discard). Both are proper ledger movements. |
| Item fields | Plus optional **supplier**, **location**, **reorder quantity** (all nullable). |
| Reports | **Basic** summary: low-stock list, stock-on-hand value, expiring-soon (when expiry on). |

## 3. Clinical grounding (from research)

- **Anesthetic** is delivered in **carpules of ~1.8 ml, boxed in 50** — counted as whole carpules, not a 100 ml bottle. (The user's "100 ml bottle" wording is corrected: the only true bottle/gram anesthetic chairside is topical gel.)
- The **"composite finger"** is a **compule/tip (~0.25 g)**, a single-use cartridge; composite also ships as a 4 g syringe. The clinic stocks one form per item.
- Many high-use items are **single-use whole units** (needle = 1/patient, gloves = 1 pair). Deducting **whole issued units** also models **wastage correctly**: open a compule, use half, discard the rest → the whole unit correctly leaves stock. The deducted amount is therefore framed as **"issued from stock,"** not "used."
- **Fixed vs variable** consumption both exist — fixed (needle, gloves) and variable (composite, anesthetic, impression). This is exactly why "default + adjustable override" is the right model.
- **Expiry** is clinically real for composite, bonding, anesthetic, impression material, sterilants — hence the opt-in expiry feature.
- **Competitive context:** procedure-linked auto-deduct is rare — Open Dental lacks it; Dentrix/Eaglesoft need paid add-ons; only Curve does it natively.

Full research (per-system field tables, per-procedure default material lists, sources) is summarized in the brainstorming thread and can be appended as an appendix on request.

## 4. Data model — 3 new tables

All tables are created idempotently in the schema-init block (next to the existing `treatment_procedures` definition, ~`dental_clinic.py:866`) and registered for migration via `ensure_table_column`.

### 4.1 `inventory_items`

```
id                  INTEGER PK
name                TEXT NOT NULL
name_ar             TEXT                       -- bilingual (app is EN/AR)
category            TEXT                        -- optional grouping (e.g. "Anesthetic", "Restorative")
base_unit           TEXT NOT NULL               -- canonical stored unit: 'piece' | 'ml' | 'g' | 'carpule' | 'compule' | ...
pack_unit           TEXT                        -- purchase-unit label: 'box' | 'bottle' | 'cartridge' | NULL
pack_size           REAL NOT NULL DEFAULT 1     -- base units per pack (1 for single-unit items)
quantity            REAL NOT NULL DEFAULT 0     -- CACHED on-hand in base_unit (derived from movements)
cost_per_unit       REAL NOT NULL DEFAULT 0     -- weighted-average cost per base_unit (insight only)
low_stock_threshold REAL NOT NULL DEFAULT 0     -- reorder point, base_unit
reorder_qty         REAL                        -- optional suggested top-up
supplier            TEXT                        -- optional
location            TEXT                        -- optional bin/shelf
track_expiry        INTEGER NOT NULL DEFAULT 0  -- per-item opt-in checkbox
earliest_expiry     TEXT                        -- cached MIN upcoming expiry across restock batches (for fast alerting)
active              INTEGER NOT NULL DEFAULT 1  -- soft-delete (like catalogs)
created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

**Three item shapes** (`base_unit` is never forced to be a fractional measure):

| Shape | Example | base_unit | pack_unit | pack_size |
|---|---|---|---|---|
| Single unit | toothpick, needle, gauze | piece | NULL | 1 |
| Pack → counted units | anesthetic, composite compules, GP points | carpule / compule | box | 50 / 20 / 100 |
| Pack → measured units | bonding, impression, etchant | ml | bottle / cartridge | 6 / 50 / 3 |

"Packs remaining" = `quantity / pack_size`, **derived for display only**.

### 4.2 `procedure_materials` (the link)

```
id           INTEGER PK
procedure_id INTEGER NOT NULL  -- FK treatment_procedures(id)
item_id      INTEGER NOT NULL  -- FK inventory_items(id)
default_qty  REAL NOT NULL DEFAULT 0  -- consumption per procedure, in item.base_unit
active       INTEGER NOT NULL DEFAULT 1
created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
UNIQUE(procedure_id, item_id)
```

### 4.3 `stock_movements` (append-only ledger — source of truth)

```
id          INTEGER PK
item_id     INTEGER NOT NULL                 -- FK inventory_items(id)
change_qty  REAL NOT NULL                    -- SIGNED, in base_unit (+restock, -consumption/-writeoff)
reason      TEXT NOT NULL                    -- 'restock' | 'consumption' | 'adjustment' | 'writeoff' | 'reversal'
unit_cost   REAL                             -- base-unit cost snapshot at post time (set on restock; valuation)
source_type TEXT                             -- 'followup' | 'manual' | 'count' | NULL
source_id   INTEGER                          -- e.g. followup_id — enables idempotent reversal
expiry_date TEXT                             -- restock-batch expiry (when item.track_expiry)
note        TEXT
created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- INDEX(item_id), INDEX(source_type, source_id)
```

**Invariant:** for every item, `quantity == SUM(change_qty WHERE item_id = ?)`. The cached `quantity` is a denormalized convenience, never an independent second source of truth.

## 5. Core mechanics

### 5.1 Single write choke-point

One function — `post_movement(cursor, item_id, change_qty, reason, *, unit_cost=None, source_type=None, source_id=None, expiry_date=None, note=None)` — is the **only** code that writes a movement. It, atomically within the caller's transaction:

1. inserts the `stock_movements` row (storing `change_qty` in base units and `unit_cost` snapshot),
2. updates `inventory_items.quantity += change_qty`,
3. on `reason='restock'`, recomputes weighted-average cost (§5.2),
4. on `track_expiry` + restock with `expiry_date`, refreshes `earliest_expiry`,
5. returns a low/zero-stock warning flag if the resulting `quantity <= low_stock_threshold` or `< 0`.

Nothing else mutates `quantity` or `cost_per_unit`. A `recompute_item_quantity(item_id)` helper (`SUM(change_qty)`) backs a reconcile/verify routine and the test invariant.

### 5.2 Weighted-average cost (restock only)

```
on_hand = max(quantity, 0)
denom   = on_hand + add_qty
if denom > 0:
    cost_per_unit = (on_hand * cost_per_unit + add_qty * received_unit_cost) / denom
# else: keep last known cost
```

- `received_unit_cost` is in **base units** (pack cost ÷ pack_size).
- Only **restock** changes the average; consumption/adjustment/write-off are valued at the current average and do not change it.
- Guard: if on-hand is negative, **reset** the average to the receipt's unit cost rather than blending into a negative base.

### 5.3 Deduction on procedure (the trigger)

Mirrors the existing lab-expense auto-insert in the follow-up POST (`dental_clinic.py:2899`), which already tags `expenses` rows with `source_type='followup', reference_id=followup_id`.

`apply_followup_consumption(cursor, followup_id, procedure_id, overrides=None)`:

- Resolves linked materials from `procedure_materials` for `procedure_id`.
- For each item, consumed qty = override (if the desktop form sent one) else `default_qty`.
- Calls `post_movement(..., change_qty=-qty, reason='consumption', source_type='followup', source_id=followup_id)`.
- Collects warnings → returned in the API response → toast.
- **Idempotent:** keyed on `(source_type='followup', source_id=followup_id)`. Safe to call more than once.

No `procedure_id` (free-text procedure) or no links → no movement.

### 5.4 Edit / delete a follow-up

- **PUT (edit):** `reverse_followup_consumption(followup_id)` then `apply_followup_consumption(...)` with the new procedure/overrides. Reversal posts compensating movements (`reason='reversal'`, opposite sign) — append-only, full history preserved.
- **DELETE (soft, `is_deleted=1`):** `reverse_followup_consumption(followup_id)` restores stock.

### 5.5 Manual corrections

- **Recount / Adjust:** doctor enters the real physical count → `post_movement(change = counted - current, reason='adjustment', source_type='count')`. Reconciles drift visibly.
- **Write-off:** `post_movement(change = -qty, reason='writeoff', note=...)` for breakage / contamination / expired discard.

### 5.6 Restock

`POST /api/inventory/items/<id>/restock` with `{pack_qty | base_qty, unit_cost | pack_cost, expiry_date?, note?}` → one `reason='restock'` movement (base qty + base unit_cost), updating on-hand + weighted-average, and `earliest_expiry` when applicable.

### 5.7 Expiry (lightweight)

When `track_expiry=1`: restock captures `expiry_date` on the movement; `earliest_expiry` on the item = MIN upcoming expiry across restock batches. The report lists batches expiring within 30/60 days or already expired (item, batch qty added, date). **No batch depletion / FEFO** in v1 — that is the Phase-2 lot model and is explicitly deferred.

## 6. API endpoints (desktop)

All added to `_AUTH_REQUIRED_EXACT` (`dental_clinic.py:1986`).

| Method & path | Purpose |
|---|---|
| `GET /api/inventory/items?include_inactive=` | list (also served read-only to mobile) |
| `POST /api/inventory/items` | create |
| `PUT /api/inventory/items/<id>` | edit / activate-deactivate / toggle track_expiry |
| `POST /api/inventory/items/<id>/restock` | add stock |
| `POST /api/inventory/items/<id>/adjust` | recount → adjustment movement |
| `POST /api/inventory/items/<id>/writeoff` | write-off movement |
| `GET /api/inventory/items/<id>/movements` | per-item history (used by Full report; optional in v1) |
| `GET /api/inventory/report` | summary: low-stock, on-hand value, expiring-soon |
| `GET/POST/DELETE /api/treatment-procedures/<id>/materials` | manage links + default_qty |

Follow-up endpoints (`/api/patients/<id>/followups` POST/PUT/DELETE) are extended to accept an optional `materials` override array and to drive §5.3–5.4.

## 7. UI

### Desktop (full)
- **New "Depo" section** (مخزن): item list with on-hand, derived packs-remaining, low-stock highlight, optional expiring-soon badge, total stock value. Item editor (name EN/AR, category, units, pack, threshold, reorder_qty, supplier, location, **Track expiry** checkbox, cost). Actions: **Add stock**, **Adjust count**, **Write-off**, deactivate.
- **Materials sub-panel** on the existing treatment-procedures (catalog) editor: add item + default_qty (the linking the user asked for).
- **Follow-up form:** when a procedure with linked materials is selected, show editable consumption rows pre-filled with defaults (the point-of-use override). Wording: "issued from stock."
- **Basic report** panel: low-stock list, on-hand value, expiring-soon.

### Mobile (read-only, Flutter)
- Depo screen: item list (name, on-hand + packs-remaining, low-stock highlight, expiring-soon badge). Reads `GET /api/inventory/items` / `/report`. **No create/edit.**
- EN/AR via the existing `AppStrings` catalog.

UI lives in `templates.py` / `web_assets.py` (desktop) and the Flutter app (`clinic_mobile_app/`). Exact placement (top-level tab vs. Settings section) confirmed at implementation.

## 8. Sync & multi-device durability

**These are the silent-failure risks; they are in-scope, not afterthoughts.**

1. **Register the 3 tables in `SYNC_TABLES`** (`dental_clinic.py:527`) so they sync desktop↔cloud↔mobile.
2. **Replace-DB / merge / backup:** verify `db_merge.py`, `db_import.py`, the replace-DB snapshot/restore path, and the export bundle cover the 3 tables (driven off `SYNC_TABLES` where possible). Memory records prior bugs where new tables were dropped across replace-DB — add a regression test.
3. **Deduction on synced-in follow-ups:** mobile-created follow-ups arrive via the **sync-apply path** (row insert), not the POST endpoint, so deduction would not fire there. **Plan:** invoke the **idempotent** `apply_followup_consumption` from the sync-apply path after `patient_followups` rows merge in, in addition to the API endpoints. Idempotency (source-keyed) makes re-runs safe.
   - **Must verify in planning:** follow-up **id stability** across devices under the current snapshot/merge scheme. If ids are remapped on merge, key consumption on a stable identifier instead of raw id.
   - **Fallback (if id stability is unsafe for v1):** auto-deduct only for follow-ups created on the desktop server; document that mobile-recorded procedures reconcile via Recount. Recommended target is the idempotent sync hook; fallback is the safe default if verification fails.
4. **Mobile is read-only for inventory:** ensure the sync/merge direction does **not** let an empty/stale mobile inventory set delete desktop rows (download-only for these tables, or merge that treats desktop as authoritative). Verify merge semantics during planning.

## 9. Error handling

- Negative/zero stock: **allow + warn** (response flag → toast); surface negatives in the report.
- No `procedure_id` / no links → no deduction (silent, correct).
- Restock: `pack_qty > 0`, `unit_cost >= 0`. Adjust: `counted_qty >= 0`.
- Items: **soft-delete** (`active=0`); block hard-delete when movements exist (deactivate instead) so history resolves.
- Concurrency: do each read-modify-write inside one transaction (SQLite single-writer; `BEGIN IMMEDIATE` for the restock/average path). Never compute the new average from a value read in an earlier transaction.
- Precision: store full precision; round only for display.

## 10. Testing (TDD — write tests first)

**pytest (unit + integration):**
- Create item in each of the 3 shapes; packs-remaining derived.
- Restock updates on-hand + weighted-average (verify the canonical `$5.75` example); restock into zero resets average; restock into negative uses the guard.
- `procedure_materials` CRUD + UNIQUE(procedure_id, item_id).
- Follow-up create with linked materials → consumption movements + cache decremented, for **default** and **override**.
- Follow-up with free-text / unlinked procedure → **no** movement.
- Low-stock warning flag returned on threshold cross / negative.
- Follow-up **edit** → reverse + repost nets correctly; **delete** → reversal restores stock; **idempotency** (re-applying consumption does not double-deduct).
- Recount posts adjustment that reconciles; write-off decrements.
- **Ledger invariant** (property-style): after any sequence of operations, `quantity == SUM(change_qty)` per item.
- **Insight-only guard (regression):** no Depo operation changes `clinic_profit` or rows in `expenses`.
- Expiry: restock with expiry sets `earliest_expiry`; report lists expiring-soon/expired; `track_expiry=0` → no expiry captured.
- Report: low-stock list, on-hand value (`Σ qty × cost`), expiring-soon.
- **Sync regression:** 3 tables in `SYNC_TABLES`; replace-DB preserves inventory; (if implemented) synced-in follow-up deducts once, not twice.

**Flutter:** read-only Depo screen renders list + low-stock highlight + packs-remaining; `dart analyze` clean.

Target: keep the full suite green (~660+ pytest), maintain the project's 80% coverage bar on new modules.

## 11. Out of scope (YAGNI — deferred)

- Full **lot/batch** tracking + **FEFO** + **lot→patient** recall traceability (Phase 2; only essential if implants are placed).
- **Purchase orders** / receiving workflow / supplier catalogs.
- **FIFO / standard** costing (weighted-average chosen).
- **Barcode** scanning.
- **EOQ / statistical safety-stock / lead-time** reorder math.
- Per-procedure **×surfaces / ×canals multiplier** (the point-of-use override covers variability in v1).
- **Mobile editing** / mobile point-of-use override.
- **Profit/expense integration** (explicitly insight-only).

## 12. Suggested module layout

- New pure module `inventory.py` (or `depo.py`): `post_movement`, `recompute_item_quantity`, weighted-average, `apply_followup_consumption`, `reverse_followup_consumption`, validation — unit-testable in isolation, mirroring `patient_import.py` / `patient_dedupe.py`.
- Flask routes in `dental_clinic.py` (thin handlers calling the module).
- Schema/migration in the existing init block; `SYNC_TABLES` + `_AUTH_REQUIRED_EXACT` registration.
- Desktop UI in `templates.py` / `web_assets.py`; mobile UI in `clinic_mobile_app/`.
