# Odontogram (tooth chart) — design

## Goal

Give every patient an interactive **odontogram**: a chart of the 32 permanent teeth,
each shown with a realistic silhouette and colored by its current condition. Tapping a
tooth opens a popup that lets the doctor (a) set the tooth's condition from an editable
catalog, (b) **+ Log treatment** — open the existing follow-up *Add Entry* form with the
tooth pre-filled, so money/ledger/invoice flow through unchanged, and (c) **+ Add to
plan** — attach the tooth to a treatment plan. Teeth that already have a plan or an unpaid
balance show a badge, **computed at read time** from the existing follow-up + plan data
(never stored).

Built on **backend + both UIs**: the Flask web portal (`templates.py`) and the Flutter
app (`clinic_mobile_app/`), at full parity.

### Locked decisions

1. **Numbering** — FDI/ISO two-digit, permanent dentition only (`11`–`48`). Primary
   teeth (`51`–`85`) are out of scope.
2. **Granularity** — *whole-tooth* status (one condition per tooth), **not** per-surface.
   Realistic SVG silhouettes (molars with cusps, pointed canines, blade incisors).
3. **Conditions** — an **editable catalog** seeded with a Core 8, modelled on the existing
   `treatment_procedures` catalog, with color swatch + Arabic label + icon + sort order.
4. **Links** — tap tooth → popup: set condition · **+ Log treatment** (existing follow-up
   Add-Entry, tooth pre-filled) · **+ Add to plan**. Plan/unpaid badges render back on the
   chart.
5. **Treatment plans** — a plan can span **multiple teeth** via a `treatment_plan_teeth`
   link table (revises the earlier "one `tooth_no` column on the plan header" idea).
6. **Legacy data** — auto-adopt existing `patient_followups.tooth_no` values that are
   valid FDI onto the chart at read time; ignore junk/free-text (left on the follow-up
   row, never charted). No migration of historical data.
7. **Badges are computed, never stored** — consistent with the codebase's
   "recompute, don't store" style (e.g. the running follow-up balance).

## Existing mechanics (build on, do not break)

- **`SYNC_TABLES`** (`dental_clinic.py:361`) lists every table that syncs. The trigger
  loop at `dental_clinic.py:926` calls `ensure_updated_at_trigger` for **each** entry, so
  any table added to `SYNC_TABLES` automatically gets its `updated_at` auto-stamp trigger
  (`ensure_updated_at_trigger`, `dental_clinic.py:395`). Sync is last-write-wins by
  `updated_at` via `_apply_sync_import` (`~1412`); deletes call `record_tombstone`
  (`dental_clinic.py:1345`) and propagate as tombstones. **Adding a synced table is
  therefore three lines: the `CREATE TABLE`, the `SYNC_TABLES` entry, and `record_tombstone`
  on delete — no bespoke sync code.**
- **Catalog pattern** — `treatment_procedures` (`CREATE` at `dental_clinic.py:609`; routes
  `GET/POST /api/treatment-procedures`, `PUT /api/treatment-procedures/<id>`; seeded from
  `default_procedures` at `dental_clinic.py:929` via `INSERT OR IGNORE`; soft-deleted via
  an `active` flag). `tooth_conditions` mirrors this verbatim.
- **Migrations** — additive columns go through `ensure_table_column`
  (`dental_clinic.py:377`); the block at `dental_clinic.py:860‑869` is where each table's
  `updated_at` is back-filled. New `CREATE TABLE` blocks sit beside the existing ones
  (`~593‑640`).
- **Follow-up Add-Entry already carries a tooth** — `patient_followups` has `tooth_no TEXT`
  (`CREATE` at `dental_clinic.py:621`); the desktop follow-up form and the Flutter sheet
  (`patient_detail_screen.dart` ~1345‑1558) both write it. "+ Log treatment" just opens that
  same form with `tooth_no` pre-set — **no new money path**.
- **Treatment plans** — `treatment_plans` (`CREATE` at `dental_clinic.py:593`) and routes
  `/api/treatment-plans` (`dental_clinic.py:2420`), `/api/treatment-plans/<id>` (`2464`).
  Note: the GET serializer (`2432‑2445`) reads columns **positionally** (`row[10]` =
  `patient_name`), which is already fragile because `updated_at` was appended by
  `ensure_table_column`. This design reworks that GET to `sqlite3.Row`/dict access while
  adding the `teeth` array (below), fixing the fragility in passing.

## Why a chart row is "marked", not "every tooth"

`patient_tooth_chart` stores **one row per tooth the doctor has actually marked**. An
unmarked tooth is implicitly *healthy* and is not stored — so a new patient has zero chart
rows, and the chart renders all 32 as healthy by default. This keeps the table small,
keeps sync deltas tiny, and means "reset a tooth to healthy" is a delete (+ tombstone),
not a sentinel row.

## Data model (`dental_clinic.py`)

### `tooth_conditions` — editable catalog (mirrors `treatment_procedures`)

```sql
CREATE TABLE IF NOT EXISTS tooth_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    name_ar TEXT,
    color TEXT DEFAULT '#9ca3af',   -- hex swatch painted on the tooth
    icon TEXT,                      -- short glyph/key for the legend (optional)
    sort_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP   -- required: the SYNC_TABLES trigger writes it
)
```

Seeded beside `default_procedures` (`~929`) with `INSERT OR IGNORE` — **Core 8**:

| name | name_ar | color | sort |
|------|---------|-------|------|
| Healthy | سليم | `#22c55e` | 0 |
| Decay | تسوّس | `#ef4444` | 1 |
| Filled | حشوة | `#3b82f6` | 2 |
| Crown | تاج | `#a855f7` | 3 |
| Root canal | علاج عصب | `#f59e0b` | 4 |
| Missing | مفقود | `#6b7280` | 5 |
| Implant | زرعة | `#06b6d4` | 6 |
| Needs extraction | يحتاج خلع | `#dc2626` | 7 |

(*Healthy* exists in the catalog for the legend/picker; selecting it on a tooth deletes the
chart row, since healthy = unmarked.)

### `patient_tooth_chart` — one row per marked tooth

```sql
CREATE TABLE IF NOT EXISTS patient_tooth_chart (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    tooth_no TEXT NOT NULL,         -- FDI two-digit, '11'..'48'
    condition_id INTEGER,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   -- required: the SYNC_TABLES trigger writes it
    FOREIGN KEY (patient_id) REFERENCES patients (id),
    FOREIGN KEY (condition_id) REFERENCES tooth_conditions (id)
)
```

- Index: `idx_patient_tooth_chart_patient_id ON patient_tooth_chart(patient_id)`.
- **No hard `UNIQUE(patient_id, tooth_no)` constraint** — sync merges by primary-key `id`
  (last-write-wins), and two devices marking the same tooth offline would create two ids;
  a UNIQUE constraint would make the second import fail. Instead: the upsert handler keeps
  **one row per (patient_id, tooth_no) on a given device** (SELECT-then-UPDATE-or-INSERT),
  and the read endpoint collapses any cross-device duplicate to the row with the newest
  `updated_at`. This matches how the app already tolerates id-based merge everywhere else.

### `treatment_plan_teeth` — plan ↔ tooth link (multi-tooth plans)

```sql
CREATE TABLE IF NOT EXISTS treatment_plan_teeth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    tooth_no TEXT NOT NULL,         -- FDI two-digit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   -- required: the SYNC_TABLES trigger writes it
    FOREIGN KEY (plan_id) REFERENCES treatment_plans (id)
)
```

- Index: `idx_treatment_plan_teeth_plan_id ON treatment_plan_teeth(plan_id)`.
- `treatment_plans` itself is **unchanged** (no new column) — the teeth live in the link
  table.

### Sync wiring

Add all three to `SYNC_TABLES` (`dental_clinic.py:361`):
`'tooth_conditions'`, `'patient_tooth_chart'`, `'treatment_plan_teeth'`. The trigger loop
(`926`) then gives each an `updated_at` auto-stamp trigger. **Each new table must therefore
carry the `updated_at` column itself** (included in the `CREATE`s above) — the trigger does
`SET updated_at = …`, so a missing column would make every UPDATE on the table fail at
fire time. Deletes in the handlers below call `record_tombstone`. No other sync code
changes.

### FDI validation (shared helper)

`_is_valid_fdi(s)` → `True` iff `s` matches `^[1-4][1-8]$` (quadrant 1‑4, tooth 1‑8). Used
by the chart upsert, plan-teeth, and the legacy auto-adopt filter. Arch display order
(left→right as the clinician faces the patient):

```
upper:  18 17 16 15 14 13 12 11 | 21 22 23 24 25 26 27 28
lower:  48 47 46 45 44 43 42 41 | 31 32 33 34 35 36 37 38
```

## API (`dental_clinic.py`, new routes near `~2420`)

### Tooth-condition catalog (mirror of `/api/treatment-procedures`)

| Method | Endpoint | Behaviour |
|--------|----------|-----------|
| GET | `/api/tooth-conditions` | List (default active-only; `?all=1` includes inactive), ordered by `sort_order, name` |
| POST | `/api/tooth-conditions` | Create `{name, name_ar?, color?, icon?, sort_order?}` |
| PUT | `/api/tooth-conditions/<id>` | Update fields |
| DELETE | `/api/tooth-conditions/<id>` | Soft-delete (`active = 0`) + `record_tombstone`; chart rows referencing it keep the id and render as "unknown/grey" until re-set |

### Patient chart

| Method | Endpoint | Behaviour |
|--------|----------|-----------|
| GET | `/api/patients/<id>/tooth-chart` | The whole chart for the patient (see shape below) |
| POST | `/api/patients/<id>/tooth-chart` | Upsert one tooth `{tooth_no, condition_id, note?}`. `condition_id` of the *Healthy* row (or `null`) deletes the row + tombstone. Rejects invalid FDI with `400`. |
| DELETE | `/api/patients/<id>/tooth-chart/<tooth_no>` | Clear the tooth back to healthy (delete + tombstone) |

**GET response** — marked teeth merged with legacy follow-up teeth and computed badges:

```jsonc
{
  "conditions": [ /* active catalog, for the legend + picker */ ],
  "teeth": {
    "16": {
      "condition_id": 2, "condition_name": "Decay", "color": "#ef4444",
      "note": "distal",
      "source": "chart",          // "chart" = explicit row; "legacy" = adopted from follow-ups
      "has_plan": true,           // computed: any treatment_plan_teeth row for this patient+tooth
      "unpaid_balance": 150.0     // computed: Σ(price − discount − payment) over follow-ups with this tooth_no, ≥0
    },
    "26": { "source": "legacy", "condition_id": null, "has_plan": false, "unpaid_balance": 0 }
  }
}
```

**Computed badges (read-time, not stored):**
- `has_plan` — `EXISTS` join `treatment_plans → treatment_plan_teeth` for `patient_id` +
  `tooth_no`.
- `unpaid_balance` — reuse the follow-up ledger math (`price − discount − payment`) summed
  over that patient's follow-ups whose `tooth_no` equals this tooth, clamped at ≥0.

**Legacy auto-adopt (decision #6):** the GET folds in distinct `patient_followups.tooth_no`
values that pass `_is_valid_fdi` and have no explicit `patient_tooth_chart` row, marking
them `source:"legacy"` with `condition_id:null` (rendered in a neutral "treated" tint) so
historically-treated teeth still light up. Junk/free-text tooth values are ignored.

### Treatment plans — add teeth

- **GET `/api/treatment-plans`** (`2420`): rework the positional serializer to dict access
  and add `"teeth": ["16","26"]` (subquery/`GROUP_CONCAT` on `treatment_plan_teeth`).
- **POST `/api/treatment-plans`** (`2453`): accept optional `teeth: [...]`; after inserting
  the plan, insert one validated `treatment_plan_teeth` row per FDI tooth.
- **PUT `/api/treatment-plans/<id>`** (`2479`): accept `teeth: [...]`; diff against existing
  link rows — insert new, delete removed (with `record_tombstone` per removed row).
- **DELETE `/api/treatment-plans/<id>`** (`2468`): also delete + tombstone its
  `treatment_plan_teeth` rows.
- **full-profile** (`dental_clinic.py:1858`, the `treatment_plans` block): include `teeth`
  so the patient profile can show plan chips.

## Desktop UI (`templates.py`)

- **Odontogram card** on the patient profile: an inline `<svg>` arch of 32 tooth shapes in
  the FDI order above (upper row + lower row, quadrant gap in the middle), each `<path>`
  realistic for its class (molar cusps / canine point / incisor blade) and filled with its
  condition color (healthy = outline only). FDI number under each tooth. A small **legend**
  lists the active catalog with swatches. Plan/unpaid **badges** are small dots/glyphs in
  the tooth corner.
- **Tap a tooth → popup** (decision #4):
  - **Condition** `<select>` from `GET /api/tooth-conditions` → `POST .../tooth-chart` on
    change (optimistic repaint, reload on success).
  - **+ Log treatment** → opens the existing follow-up *Add Entry* modal with
    `#followup-tooth` pre-filled (and procedure focus). Reuses the entire money/discount/
    ledger/invoice path with zero new logic.
  - **+ Add to plan** → choose/create a plan and add this tooth (`PUT/POST
    /api/treatment-plans` with `teeth`).
  - **Note** field → saved on the chart row.
- **Tooth-conditions admin** sheet under **Settings**, mirroring the Procedure-catalog
  admin (add / edit color+labels+icon / reorder / activate-inactivate).
- **i18n** — every new label gets EN + AR keys in the `translations` object; the chart
  honours RTL (mirror the arch horizontally in Arabic so quadrant 1 stays on the patient's
  right).

## Flutter UI (`clinic_mobile_app/`, full parity)

- **Models**: `tooth_condition.dart`, `tooth_chart_entry.dart`; extend the treatment-plan
  model with `List<String> teeth`.
- **Service**: `tooth_chart_service.dart` (catalog CRUD + chart GET/upsert/clear,
  Dio, mirrors `catalog_service.dart`); plan service gains teeth read/write.
- **Local DB**: bump the `sqflite` schema version in `database_service.dart` and add an
  `onUpgrade` step that `CREATE TABLE IF NOT EXISTS` the two new tables + link table — so
  existing installs migrate without data loss.
- **Screen**: an **Odontogram** tab on `patient_detail_screen.dart` (or
  `odontogram_screen.dart`), painting the same arch via `CustomPaint`/`flutter_svg`. Tap →
  bottom sheet with the same three actions; **+ Log treatment** reuses the existing
  follow-up Add-Entry sheet (~1345‑1558) with the tooth pre-filled.
- **Conditions admin** sheet under Settings, mirroring `catalog_screen.dart`.
- Currency stays `₪`; no `$` (parity invariant #4).

## Edge cases

| Case | Behaviour |
|------|-----------|
| New patient | zero chart rows → all 32 render healthy |
| Set a tooth to *Healthy* | delete the chart row + tombstone (healthy = unmarked) |
| Invalid FDI on upsert (`99`, `5a`, primary `51`) | `400`, not stored |
| Legacy follow-up `tooth_no = "upper left"` (junk) | ignored by the chart; stays on the follow-up row |
| Legacy follow-up `tooth_no = "16"`, no chart row | shown as `source:"legacy"`, neutral tint, still gets badges |
| Two devices mark tooth 16 offline | both rows sync; read-time collapse shows the newest `updated_at` |
| Condition soft-deleted while teeth reference it | teeth keep the id, render neutral/"unknown" until re-set |
| Delete a plan covering 16,26,36 | plan + its 3 link rows deleted & tombstoned; `has_plan` clears on all three |
| Tooth with unpaid follow-ups but no chart mark | `unpaid_balance` badge still computed (legacy adopt) |

## Testing

New pytest suites under `tests/` (AAA style, following the repo's existing structure):

- **`test_tooth_conditions.py`** — catalog CRUD, soft-delete (`active=0` + tombstone),
  seed presence of the Core 8, `?all=1` filter.
- **`test_tooth_chart_api.py`** — upsert one tooth; set→Healthy deletes the row; FDI
  validation (`99`/`5a`/`51` → 400); per-patient scoping; clear endpoint tombstones.
- **`test_tooth_chart_badges.py`** — `has_plan` true only when a plan-tooth link exists;
  `unpaid_balance` equals the follow-up ledger sum (clamped ≥0); **legacy auto-adopt**
  surfaces valid `tooth_no` and ignores junk.
- **`test_treatment_plan_teeth.py`** — POST/PUT teeth diff (add/remove + tombstones), GET
  returns the `teeth` array, plan delete cascades the link rows.
- **`test_tooth_chart_sync.py`** — all three tables export/import; tombstone propagation;
  cross-device duplicate collapses to newest at read time.
- Extend **`test_api_fuzz.py`** to hit the new endpoints (no 5xx on malformed input).

Flutter (`clinic_mobile_app/test/`): `tooth_chart_service_test.dart` (model round-trip +
chart parse incl. computed fields), a widget/golden for the arch, and a DB `onUpgrade`
migration test.

Manual parity check (reported honestly, like the existing inline-JS features): tap a tooth
on both desktop and mobile → set condition, log a treatment (money lands on the ledger),
add to a multi-tooth plan, and confirm badges + colors match across the two clients after a
sync.

## Files

| File | Change |
|------|--------|
| `dental_clinic.py` | 3 `CREATE TABLE` blocks + Core-8 seed; `SYNC_TABLES` += 3; `ensure_table_column`/index lines; `_is_valid_fdi` helper; `/api/tooth-conditions` (+`/<id>`) routes; `/api/patients/<id>/tooth-chart` (GET/POST + `/<tooth_no>` DELETE) with computed badges + legacy adopt; treatment-plans GET/POST/PUT/DELETE teeth handling (and dict-access serializer fix); full-profile teeth |
| `templates.py` | Odontogram SVG card + legend + tap popup (condition / +Log treatment / +Add to plan / note); tooth-conditions admin sheet; EN/AR i18n keys; RTL arch mirroring |
| `clinic_mobile_app/lib/models/` | `tooth_condition.dart`, `tooth_chart_entry.dart`; plan model += `teeth` |
| `clinic_mobile_app/lib/services/` | `tooth_chart_service.dart`; plan service teeth read/write; `database_service.dart` version bump + `onUpgrade` |
| `clinic_mobile_app/lib/screens/` | Odontogram tab/screen + tap sheet (reuses follow-up Add-Entry); conditions admin sheet |
| `tests/` | `test_tooth_conditions.py`, `test_tooth_chart_api.py`, `test_tooth_chart_badges.py`, `test_treatment_plan_teeth.py`, `test_tooth_chart_sync.py`; extend `test_api_fuzz.py` |
| `clinic_mobile_app/test/` | `tooth_chart_service_test.dart` + arch widget/golden + migration test |
| `README.md` | Document the odontogram (Features + REST API + tables + test counts) |

## Implementation note

Per the working preference, implementation will be farmed out to **parallel agents** on
independent tracks — **backend** (schema + API + sync), **desktop** (`templates.py`),
**mobile** (Flutter), **tests** — coordinated from a `writing-plans` plan. The
brainstorming/design dialogue stays inline (this doc). The single shared dependency the
tracks must agree on first is the **GET `/api/patients/<id>/tooth-chart` JSON shape** and
the **FDI arch order** above; both are frozen here so the tracks can proceed without
blocking each other.
