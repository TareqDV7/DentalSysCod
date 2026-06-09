# Merge / Replace Database — Design Spec

**Date:** 2026-06-09
**Branch:** feat/licensing-overhaul
**Status:** Approved design, pending implementation plan

---

## 1. Problem

A clinic operator needs an in-app way to bring data from **another DentaCare database** into the running one. Two distinct goals:

- **Replace** — discard the current data and use an imported database instead (restore an older or other copy).
- **Merge** — combine a **different clinic's** data into the current clinic, keeping both sets.

There is currently no such option in the UI. The README only documents Download Backup (DB only) and a manual file-copy restore. The user confirmed the imported data **could be a genuinely different clinic** (separate ID lineage), so a naive ID-keyed merge would corrupt data — the merge must re-number incoming records and rewrite all links.

## 2. Decisions (locked)

| Decision | Choice |
|----------|--------|
| Data lineage | Could be a **different** clinic → additive re-numbering merge required |
| Duplicate patients (same name+phone) | **Keep separate** — every incoming patient becomes a new record; no auto-dedup of patients |
| Merge scope (beyond core clinical/financial) | Include **medical images** and **patient credit balances**; **exclude holidays** |
| Engine location | New **`db_merge.py`** module (keep `dental_clinic.py` from growing) |
| Import file format | **`.zip` bundle** (db + uploads) to carry X-ray files; bare `.db` accepted (images skipped) |
| Replace mechanism | **Live swap, no restart** (brief maintenance window) |
| Existing data on merge | **Never overwritten or deleted** — additive only |
| Catalog tables | Deduped by name (their `name` columns are `UNIQUE`) |

## 3. Architecture

### 3.1 Modules

- **`db_merge.py`** — pure engine, no Flask/globals. Unit-testable with two temp SQLite files.
  - `merge_database(dst_conn, src_db_path, src_uploads, dst_uploads, *, include_images, include_credit) -> MergeReport`
  - `MergeReport` — per-table counts (added / skipped), images copied, warnings (e.g. "image file missing", "bare .db: images skipped").
- **`dental_clinic.py`** — thin route handlers only: auth gate, upload handling, zip extraction + validation, safety backup, call the engine, return the report JSON. Reuses `run_database_backup()` for the safety snapshot.

### 3.2 Endpoints (local server only; disabled on cloud node)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/data/export-bundle` | Login. Streams a `.zip` of an online-backup DB snapshot + `uploads/`. |
| POST | `/api/data/merge` | Login. Multipart upload (`.zip` or `.db`). Runs additive merge. Returns `MergeReport`. |
| POST | `/api/data/replace` | Login. Multipart upload (`.zip` or `.db`). Backs up current, live-swaps. Returns status + safety-backup path. |

Cloud node (`CLOUD_MODE`) returns `400`/`404` for all three, consistent with other local-only endpoints.

## 4. Merge algorithm (additive, transactional)

Open the source DB as a **second read-only connection**. Insert into the live DB in dependency order, building `old_id -> new_id` remap dicts per table and rewriting foreign keys before each insert. **Entire merge runs inside one transaction** on the live DB — commit on success, roll back on any unexpected error so current data is never left half-merged.

### 4.1 Insert order & remap rules

| # | Table | Strategy |
|---|-------|----------|
| 1 | `treatment_procedures` | Dedupe by `name`: if name exists in dst, map `old_id -> existing_id`; else insert, map to new id |
| 2 | `tooth_conditions` | Dedupe by `name` (same as above) |
| 3 | `patients` | Always insert new (no dedup); map `old_id -> new_id` |
| 4 | `appointments` | Remap `patient_id`; insert; map old→new |
| 5 | `visits` | Remap `patient_id`, `appointment_id` (nullable); insert; map old→new |
| 6 | `treatments` | Remap `patient_id`, `appointment_id` (nullable); insert; map old→new |
| 7 | `treatment_plans` | Remap `patient_id`; insert; map old→new |
| 8 | `treatment_plan_teeth` | Remap `plan_id`; insert |
| 9 | `patient_followups` | Remap `patient_id`, `procedure_id` (nullable); insert; map old→new |
| 10 | `billing` | Remap `patient_id`, `treatment_id` (nullable); insert; map old→new |
| 11 | `expenses` | Remap `patient_id` (nullable), `treatment_id` (nullable), **and `reference_id`→follow-up remap when `source_type='followup'`**; insert |
| 12 | `patient_tooth_chart` | Remap `patient_id`, `condition_id`; insert |
| 13 | `medical_images` | Remap `patient_id`; copy source file into dst `uploads/` under a new unique name; rewrite `file_name` (keep original label) + `file_path` (new absolute path); insert. Skip with warning if file absent or no uploads provided |
| 14 | `patient_credit_transactions` | Remap `patient_id`, `invoice_id`→billing remap (nullable); insert |

`holidays` is **not** merged (per decision). `users`, `app_settings`, audit/sync/pairing/license tables are never merged.

### 4.2 Schema-drift tolerance

For every table, read the **destination's** columns via `PRAGMA table_info` and insert only the intersection of (source row keys ∩ dst columns), minus `id`. Effects:
- An **older-version source** missing newer columns merges cleanly (defaults fill the rest).
- Unknown/removed source columns are ignored.
- A per-row SQLite error counts the row as skipped (recorded in the report) without aborting the batch — but a structural failure still rolls the whole transaction back.

### 4.3 Post-merge

Recompute follow-up running balances for the newly inserted patients (reuse `_recompute_followup_balances`). Credit balances derive from the imported `patient_credit_transactions` automatically.

## 5. Replace flow (live swap)

1. Validate the upload (SQLite magic / valid zip).
2. **Safety backup**: online-backup snapshot of the current DB + zip the current `uploads/`; capture the path.
3. Enter a process-wide **maintenance state**: a `before_request` guard returns `503` (JSON `{maintenance: true}`) for the brief window so no handler opens a connection mid-swap. The data/sync endpoints honor it too.
4. `PRAGMA wal_checkpoint(TRUNCATE)`, close any open connection, delete `-wal`/`-shm` sidecars.
5. Overwrite `dental_clinic.db` with the imported DB; replace the `uploads/` folder (from the bundle; left as-is for a bare `.db`).
6. Run `init_database()` to migrate the incoming DB forward to the current schema.
7. Exit maintenance state. The browser refreshes; the pywebview window/service reconnects on its next request.

## 6. Safety & security

- **Login-gated** (staff session) — same gate as `/api/backup`.
- **File validation:** reject uploads whose first 16 bytes are not `SQLite format 3\0`. For zips: reject absolute paths and `..` (zip-slip), extract only `dental_clinic.db` + `uploads/*`, enforce a size cap (`MAX_CONTENT_LENGTH` or manual check).
- **Typed confirmation** in the UI: "type MERGE" / "type REPLACE" before the action fires.
- **Automatic safety backup** before both merge and replace; the path is returned so the operator can always undo.
- **Atomicity:** merge is a single transaction (all-or-nothing); replace keeps the pre-swap snapshot.
- Disabled on the cloud node.

## 7. UI

**Settings → Data Tools** card (bilingual EN/AR via the `translations` object in `templates.py`):

- **Export bundle (.zip)** — downloads db + uploads.
- **Merge another clinic** — file picker + typed confirm → progress → summary report ("Added 142 patients, 318 appointments, 51 invoices, 12 images…") + safety-backup location + any warnings.
- **Replace database** — file picker + typed confirm → maintenance/swap → "Done, refresh" + safety-backup location.

## 8. Testing (TDD, pytest)

- **`tests/test_db_merge.py`** (engine):
  - Two clinics with **colliding IDs** merge correctly: A's data intact; all of B's patients present under new ids; appointments/follow-ups/billing point to the *correct* remapped patient.
  - Catalog **dedupe by name** (shared "Cleaning" → one row; references remapped).
  - `expenses.reference_id` (follow-up) and `patient_credit_transactions.invoice_id` (billing) **soft-links remapped**.
  - **Medical images** copied into dst uploads with rewritten path; warning when file missing / bare `.db`.
  - **Schema-drift** source (older, missing columns) merges without error.
  - Garbage / empty source handled (no crash, sensible report).
  - Existing-data invariant: dst row counts for pre-existing patients unchanged.
- **`tests/test_data_tools_api.py`** (routes): auth gate (401 unauth), non-SQLite rejected, zip-slip rejected, cloud-mode disabled, safety backup created, merge report shape, replace swaps the file + maintenance guard.
- **`tests/test_export_bundle.py`**: bundle contains db + uploads and round-trips through merge.
- Full suite stays green (`python -m pytest tests/`). README "Features" + "REST API Reference" + "Project Structure" updated.

## 9. Out of scope

- Mobile app UI for import/merge (desktop portal only for now).
- Auto-dedup of patients across clinics (explicitly chosen against).
- Same-lineage LWW merge mode (Replace covers the same-clinic restore case).
- Merging `holidays`, `users`, or `app_settings`.

## 10. Risks

- **Cross-clinic true duplicates** (same person at both clinics) become two patient records by design; the operator can merge manually later. Acceptable per decision.
- **Live swap on Windows** must fully release file handles (incl. WAL sidecars) before overwrite; the maintenance guard + checkpoint + connection close mitigate this. Fallback if a handle lingers: surface a clear error and leave current DB untouched (safety backup already taken).
- **Bare `.db` imports** silently lack images — surfaced as an explicit report warning, not a hard failure.
