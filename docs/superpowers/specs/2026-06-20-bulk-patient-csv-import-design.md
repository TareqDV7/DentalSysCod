# Bulk Patient Import (CSV / Excel) — Design

**Date:** 2026-06-20
**Status:** Approved (brainstorm complete)
**Scope:** Desktop Settings → Data Tools. Import a clinic's existing patient list
from a CSV or Excel file into DentaCare.

---

## 1. Why

Migration-in is the make-or-break for a switching clinic: a solo dentist will not
re-key hundreds of patients by hand. A one-shot bulk import of their existing
patient list removes the single biggest reason to say no. This is a Phase 1
launch-readiness item (`docs/LAUNCH_READINESS.md` → "Bulk patient import").

This feature imports **patient demographics only**. Appointments, treatments, and
billing history are explicitly out of scope (see §8).

---

## 2. Decisions (locked during brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| File format | **CSV + Excel (`.xlsx`)** | Adds `openpyxl`. Non-technical staff often have `.xlsx`. |
| Column mapping | **Auto-detect + manual override** | Reads their header row, best-guesses each field, user confirms/corrects. |
| Bad rows | **Preview → import valid + report skipped** | Clinic gets most data in now; problem rows reported, not blocking. |
| Duplicates | **Flag, skip by default, allow override** | Reuses existing name+phone matcher; keeps the DB clean. |
| Data scope | **Demographics only** | Predictable; the rest is a far larger, separate project. |
| Date parsing | **User picks the file's date format** | Eliminates silent DOB corruption from ambiguous dates. |
| State model | **Two-call stateless (re-send file)** | No server temp state; fits the pure-helper pattern; trivial cost at this scale. |
| Skipped-rows report | **Inline in the UI only** | No `exports/` file in v1 (YAGNI). |

---

## 3. Architecture

### 3.1 New pure module: `patient_import.py`

No Flask. Takes bytes / rows, returns plain data. Same grain as `db_import.py`
and `patient_dedupe.py`. The caller (the Flask endpoint) owns the DB transaction.

```
read_table(filename: str, data: bytes) -> ParsedTable
    Detect CSV vs .xlsx by extension + magic bytes.
    CSV  : stdlib csv; sniff delimiter; strip UTF-8 BOM; decode utf-8 (fallback latin-1).
    .xlsx: openpyxl read_only mode; first worksheet; first row = headers.
    Returns: headers: list[str], rows: list[dict[str, str]] (raw string cells).
    Raises ValueError on unreadable / empty / unsupported files.

guess_mapping(headers: list[str]) -> dict[field, header | None]
    Fuzzy-match each target FIELD to a source header via a bilingual EN/AR synonym
    table. Normalization: lowercase, strip, collapse whitespace/punctuation.
    Unmatched fields map to None.

validate_rows(rows, mapping, date_format) -> (clean: list[dict], problems: list[dict])
    Apply mapping → build a normalized patient dict per row.
    Enforce required fields (first_name, last_name).
    Parse date_of_birth strictly per date_format; unparseable -> problem.
    problems entries: {row_number: int, reason: str}.
    row_number is 1-based over data rows (header excluded), matching what a user
    sees in a spreadsheet minus the header.

flag_duplicates(clean, existing_index) -> list[dict]
    Mark each clean row as duplicate when its (normalized name, phone) matches an
    existing patient OR an earlier row in the same file.
    Reuses patient_dedupe.normalize_name. Phone normalized to digits only.
    existing_index is built by the caller from the patients table.
```

### 3.2 Endpoints (in `dental_clinic.py`)

Both are **desktop-only** (return 404 when `CLOUD_MODE`), auth-gated like the
other `/api/data/*` tools, and CSRF-covered (same-origin SPA `fetch`; the existing
fetch interceptor attaches `X-CSRFToken`).

```
POST /api/data/import-patients/preview      (multipart: file [, mapping, date_format])
    -> read_table -> guess_mapping (or use supplied mapping) -> validate_rows
       -> flag_duplicates
    Response:
    {
      "headers":   ["...", ...],
      "fields":    [{key, label_en, label_ar, required}],   # the importable fields
      "suggested_mapping": {field: header | null},
      "date_format": "DD/MM/YYYY",
      "rows_total": N,
      "counts":    {valid, problems, duplicates},
      "preview":   [{row_number, values:{field:val}, status:"valid|problem|duplicate", reason?}]
    }

POST /api/data/import-patients/commit        (multipart: file, mapping, date_format, import_duplicates)
    Re-parse + re-validate the file with the finalized mapping/date_format.
    Backup-first (run_database_backup()).
    Insert valid, non-skipped rows in ONE transaction.
    Response:
    {
      "success": true,
      "imported": int,
      "skipped":  int,
      "skipped_report": [{row_number, reason}],     # problems + skipped duplicates
      "backup_path": "..."
    }
```

`import_duplicates` (bool): when false (default), rows flagged as duplicates are
skipped and listed in `skipped_report` with reason "duplicate". When true, they
are imported.

---

## 4. Data flow

1. **Upload → preview.** Client POSTs the file. Server parses, guesses the mapping,
   validates with the guess + default `DD/MM/YYYY`, flags duplicates, returns the
   preview payload.
2. **Adjust.** User edits the mapping dropdowns, picks the real date format, and
   optionally ticks "import duplicates anyway." Any change re-calls preview
   (re-sending the file) so counts and badges refresh.
3. **Commit.** Client re-sends file + finalized mapping + date_format +
   import_duplicates. Server re-parses, re-validates, backs up, inserts valid rows
   in one transaction, returns the summary + skipped report.

The file is parsed twice (preview + commit). This is intentional and negligible:
a solo clinic's patient list is hundreds to low-thousands of rows, a sub-megabyte
file. Keeping the server stateless is worth the re-parse.

---

## 5. Fields, mapping & validation

### 5.1 Importable fields (demographics only)

| field | required | target column | notes |
|---|---|---|---|
| `first_name` | yes | `patients.first_name` | blank → problem |
| `last_name` | yes | `patients.last_name` | blank → problem |
| `date_of_birth` | no | `patients.date_of_birth` | parsed per chosen format; blank ok |
| `phone` | no | `patients.phone` | trimmed; used for dup match |
| `email` | no | `patients.email` | trimmed; no hard validation |
| `address` | no | `patients.address` | trimmed |
| `gender` | no | `patients.gender` | trimmed (free text, as today) |
| `medical_history` | no | `patients.medical_history` | a "notes"/"medical history" column maps here |

Legacy columns `birth_date` and `notes` are left untouched — `date_of_birth` is the
field the create-patient path writes, so the import targets it for consistency.

Insert reuses the existing create-patient INSERT shape. Each insert fires the
`updated_at` trigger, so imported patients sync to cloud/mobile automatically. No
tombstones (inserts only).

### 5.2 Validation rules

- **Required:** blank first or last name → `problem` (skipped), reason names the field.
- **Date:** strict parse per the selected format (`DD/MM/YYYY` default, `MM/DD/YYYY`,
  `YYYY-MM-DD`). Unparseable non-blank value → `problem`. Blank DOB is allowed.
- **Email / phone / others:** stored as-is after trim. No rejection on format —
  clinics routinely have partial data.

### 5.3 Duplicate detection

- Key: `(normalize_name(first, last), digits_only(phone))`. Blank phone normalizes
  to `""`.
- A row is a `duplicate` when its **full key** matches an existing patient or an
  earlier in-file row — i.e. both name **and** phone must be equal. Matching name
  with a different phone is **not** a duplicate; matching phone with a different
  name is **not** a duplicate.
- Edge case (made explicit): two records with the same name and **both** phones
  blank share the key `(name, "")` and **are** flagged as duplicates — conservative
  by design, since the user sees them in the preview and can opt to import anyway.
- Reuses `patient_dedupe.normalize_name`.
- Default: skipped and reported. With `import_duplicates=true`: imported.
- Any duplicates that slip through are handled by the existing duplicate-finder /
  merge tool.

---

## 6. Error handling & safety

- **Backup-first:** `run_database_backup()` before any insert, as merge/dedupe do.
- **Single transaction:** any unexpected error rolls back the whole import; the
  response carries `backup_path`.
- **Per-row problems never abort** — they are collected and reported.
- **Audit log:** `append_audit_log(cursor, 'import', 'patient', None,
  {imported, skipped, source})`.
- **Guard rails (constants):**
  - Max file size: **10 MB** — larger → 400 with a clear message.
  - Max data rows: **20,000** — larger → 400.
  - `openpyxl` read-only mode bounds memory and mitigates zip-bombs.
- **CSRF:** same-origin SPA `fetch`; existing interceptor attaches the token.
- **Cloud:** both endpoints 404 on `CLOUD_MODE` (import is a local appliance action).

---

## 7. UI (desktop Settings → Data Tools, EN/AR)

An **"Import patients"** card in the existing Data Tools section:

1. File picker (`.csv`, `.xlsx`) + **Preview** button.
2. After preview, a mapping panel:
   - One row per importable field: field label (EN/AR) + a "source column"
     dropdown pre-filled with the guess (or "— not imported —").
   - A **date-format** selector (DD/MM/YYYY · MM/DD/YYYY · YYYY-MM-DD).
   - A scrollable preview list: each row shows mapped values + a badge
     (`valid` / `problem` / `duplicate`) and the reason for non-valid rows.
   - Live counts: "X will import · Y problems · Z duplicates".
   - An **"import duplicates anyway"** checkbox.
   - An **"Import N patients"** confirm button (N = current valid + opted-in count).
3. On commit: a `showToast` summary ("Imported N patients, skipped M") and an
   inline skipped-rows list (row # + reason). No file is written.

All new strings added to both EN and AR string sets, following the existing
bilingual pattern in `templates.py` / `web_assets.py`.

---

## 8. Out of scope (v1)

- Appointment, treatment, and billing/financial history import.
- Opening balances.
- Mobile (Flutter) import UI — desktop Data Tools only.
- Saving the skipped-rows report to a file (inline display only).
- Upsert / updating existing patients from the file.

These are deliberately deferred; none block the migration value v1 delivers.

---

## 9. Build implication

`openpyxl>=3.1` is added to `requirements.txt` **and** to the PyInstaller bundle
(hidden imports / `collect_all` as needed) so the signed `.exe` still imports it.
Verification includes parsing an `.xlsx` from the packaged binary, not just from
source.

---

## 10. Testing

**Unit — `patient_import.py` (target 80%+):**
- CSV parsing: comma + tab delimiters, UTF-8 BOM, quoted fields with commas, blank
  trailing rows.
- `.xlsx` parsing: headers + rows, empty cells, numeric cells coerced to strings.
- `guess_mapping`: EN headers, AR headers, messy headers ("Mobile No", "DOB"),
  unmatched field → None.
- `validate_rows`: missing required → problem; bad date per each format → problem;
  blank DOB allowed; clean row → normalized dict; row_number correctness.
- `flag_duplicates`: vs existing patient; within-file repeat; name match + different
  phone → not a dup; phone match + different name → not a dup; same name + both
  phones blank → dup.

**Integration — endpoints (temp-DB fixture; portal routes need `session['uid']`):**
- preview returns the documented shape and correct counts.
- commit imports valid rows, skips problems + duplicates, honors
  `import_duplicates`, writes an audit-log row, and the imported patients appear in
  `/api/patients`.
- commit rolls back fully on an injected mid-insert failure (DB unchanged,
  `backup_path` present).
- both endpoints return 404 under `CLOUD_MODE`.
- both endpoints require auth.
- file too large / too many rows → 400.
