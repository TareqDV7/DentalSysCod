# Bulk Patient Import (CSV / Excel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a clinic bulk-import its existing patient list (CSV or Excel) into DentaCare from the desktop Settings → Data Tools surface.

**Architecture:** A new pure-Python module `patient_import.py` (parse / auto-map / validate / dedupe — no Flask, caller owns the transaction, same grain as `db_import.py` and `patient_dedupe.py`) behind two desktop-only Flask endpoints (`preview` + `commit`) using a two-call stateless flow (the file is re-sent on commit). A Data Tools UI card drives mapping confirmation, a dry-run preview, and the import.

**Tech Stack:** Python 3 / Flask, stdlib `csv`, `openpyxl` (new dep) for `.xlsx`, SQLite, inline HTML/JS in `templates.py`, pytest.

## Global Constraints

- **Desktop-only:** both endpoints return `404` when `dental_clinic.CLOUD_MODE` is true. (verbatim: `{'error': 'Not available on the cloud node'}`)
- **Auth-gated:** the login gate (`_AUTH_REQUIRED_EXACT`) is **exact-match** — every new route path MUST be added to that set or it is publicly reachable.
- **Bilingual EN/AR:** all user-facing strings have English + Arabic. Static markup uses `data-en`/`data-ar`; dynamic JS uses `currentLanguage === 'ar' ? '…' : '…'` or `t('key','English')`.
- **Canonical stored date format is `YYYY-MM-DD`** (what `parse_date_input` writes); imported DOBs must be stored in that format.
- **Importable fields (demographics only):** `first_name` (required), `last_name` (required), `date_of_birth`, `phone`, `email`, `address`, `gender`, `medical_history`. No appointments/billing/history.
- **Safety:** commit does backup-first (`run_database_backup()`), one transaction, full rollback on unexpected error, writes an audit-log row.
- **Caps:** reject files larger than **10 MB** or with more than **20,000** data rows (HTTP 400).
- **Duplicate key:** `(patient_dedupe.normalize_name(first,last), digits_only(phone))`; both parts must match; two same-name rows with both phones blank share key `(name,"")` and ARE duplicates.
- **Test command:** `python -m pytest tests/<file> -v` (pytest summary may be suppressed; rely on exit code / `-v`).

---

### Task 1: Add `openpyxl` dependency + bundle it in the build

**Files:**
- Modify: `requirements.txt`
- Modify: `DentaCare.spec:14-51` (the `COMMON_HIDDEN` list)

**Interfaces:**
- Produces: `openpyxl` importable at runtime in both source and the PyInstaller binaries.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add a line after the existing entries:

```
openpyxl>=3.1
```

- [ ] **Step 2: Install it**

Run: `pip install "openpyxl>=3.1"`
Expected: installs openpyxl (and its `et-xmlfile` dep).

- [ ] **Step 3: Verify it imports**

Run: `python -c "import openpyxl; print(openpyxl.__version__)"`
Expected: prints a version `>= 3.1`.

- [ ] **Step 4: Add openpyxl to the PyInstaller hidden imports**

In `DentaCare.spec`, inside the `COMMON_HIDDEN` list (ends at line 51), add these entries before the closing `]`:

```python
    # Bulk patient import (.xlsx parsing). 'openpyxl.cell._writer' is a known
    # PyInstaller miss that openpyxl imports lazily.
    'openpyxl',
    'openpyxl.cell._writer',
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt DentaCare.spec
git commit -m "build: add openpyxl dependency + bundle for .xlsx patient import"
```

---

### Task 2: `read_table` — parse CSV and `.xlsx` into headers + rows

**Files:**
- Create: `patient_import.py`
- Test: `tests/test_patient_import.py`

**Interfaces:**
- Produces:
  - `IMPORT_FIELDS: list[dict]` — `[{'key': str, 'required': bool}, ...]` in display order.
  - `DATE_FORMATS: dict[str,str]` — label → `strptime` pattern.
  - `read_table(filename: str, data: bytes) -> tuple[list[str], list[dict[str,str]]]` — returns `(headers, rows)`; each row is `{header: cell_string}`. Raises `ValueError` on empty/unreadable/unsupported files.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_patient_import.py`:

```python
import io

import openpyxl
import pytest

import patient_import as pi


def _csv_bytes(text):
    return text.encode('utf-8')


def test_read_csv_basic():
    headers, rows = pi.read_table('p.csv', _csv_bytes(
        'First Name,Last Name,Mobile\nAli,Hassan,0501\nMona,Saleh,0502\n'))
    assert headers == ['First Name', 'Last Name', 'Mobile']
    assert rows[0] == {'First Name': 'Ali', 'Last Name': 'Hassan', 'Mobile': '0501'}
    assert len(rows) == 2


def test_read_csv_strips_bom_and_blank_trailing_rows():
    headers, rows = pi.read_table('p.csv', '﻿Name,Phone\nAli,1\n\n'.encode('utf-8'))
    assert headers == ['Name', 'Phone']
    assert len(rows) == 1


def test_read_csv_quoted_field_with_comma():
    _, rows = pi.read_table('p.csv', _csv_bytes('Name,Address\nAli,"Cairo, Egypt"\n'))
    assert rows[0]['Address'] == 'Cairo, Egypt'


def test_read_xlsx_coerces_numeric_and_dates_to_strings():
    import datetime
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Name', 'Phone', 'DOB'])
    ws.append(['Ali', 501, datetime.datetime(2020, 3, 4)])
    buf = io.BytesIO()
    wb.save(buf)
    headers, rows = pi.read_table('p.xlsx', buf.getvalue())
    assert headers == ['Name', 'Phone', 'DOB']
    assert rows[0]['Phone'] == '501'          # not '501.0'
    assert rows[0]['DOB'] == '2020-03-04'     # datetime rendered ISO


def test_read_empty_file_raises():
    with pytest.raises(ValueError):
        pi.read_table('p.csv', b'')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_patient_import.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'patient_import'`).

- [ ] **Step 3: Write the implementation**

Create `patient_import.py`:

```python
"""Pure helpers for the bulk patient-import surface: parse CSV/.xlsx, auto-map
columns to patient fields, validate rows, and flag duplicates. No Flask — every
function takes bytes/rows and returns plain data; the caller owns the DB
transaction. Mirrors db_import.py / patient_dedupe.py."""
from __future__ import annotations

import csv
import datetime
import io

import patient_dedupe

# Display order; required fields gate a row.
IMPORT_FIELDS = [
    {'key': 'first_name', 'required': True},
    {'key': 'last_name', 'required': True},
    {'key': 'date_of_birth', 'required': False},
    {'key': 'phone', 'required': False},
    {'key': 'email', 'required': False},
    {'key': 'address', 'required': False},
    {'key': 'gender', 'required': False},
    {'key': 'medical_history', 'required': False},
]

DATE_FORMATS = {
    'DD/MM/YYYY': '%d/%m/%Y',
    'MM/DD/YYYY': '%m/%d/%Y',
    'YYYY-MM-DD': '%Y-%m-%d',
}


def _cell_to_str(value) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime('%Y-%m-%d')
    return str(value).strip()


def _read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = data.decode('utf-8-sig')      # strips BOM if present
    except UnicodeDecodeError:
        text = data.decode('latin-1')
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',\t;')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    all_rows = [r for r in reader if any((c or '').strip() for c in r)]
    if not all_rows:
        raise ValueError('file is empty')
    headers = [(h or '').strip() for h in all_rows[0]]
    rows = []
    for raw in all_rows[1:]:
        row = {}
        for i, header in enumerate(headers):
            row[header] = (raw[i] if i < len(raw) else '').strip()
        rows.append(row)
    return headers, rows


def _read_xlsx(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise ValueError('file is empty')
    headers = [_cell_to_str(c) for c in header_row]
    rows = []
    for raw in rows_iter:
        if not any(_cell_to_str(c) for c in raw):
            continue
        row = {}
        for i, header in enumerate(headers):
            row[header] = _cell_to_str(raw[i]) if i < len(raw) else ''
        rows.append(row)
    wb.close()
    return headers, rows


def read_table(filename: str, data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if not data:
        raise ValueError('file is empty')
    name = (filename or '').lower()
    if name.endswith('.xlsx') or data[:4] == b'PK\x03\x04':
        return _read_xlsx(data)
    return _read_csv(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_patient_import.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add patient_import.py tests/test_patient_import.py
git commit -m "feat: patient_import.read_table (CSV + xlsx parsing)"
```

---

### Task 3: `guess_mapping` — bilingual auto-detect of columns

**Files:**
- Modify: `patient_import.py`
- Test: `tests/test_patient_import.py`

**Interfaces:**
- Produces: `guess_mapping(headers: list[str]) -> dict[str, str | None]` — maps each field key in `IMPORT_FIELDS` to a header from `headers` (or `None`). Each header is used at most once.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_patient_import.py`:

```python
def test_guess_mapping_english():
    m = pi.guess_mapping(['First Name', 'Last Name', 'Mobile No', 'DOB', 'E-mail'])
    assert m['first_name'] == 'First Name'
    assert m['last_name'] == 'Last Name'
    assert m['phone'] == 'Mobile No'
    assert m['date_of_birth'] == 'DOB'
    assert m['email'] == 'E-mail'
    assert m['address'] is None


def test_guess_mapping_arabic():
    m = pi.guess_mapping(['الاسم الأول', 'اسم العائلة', 'الجوال', 'العنوان'])
    assert m['first_name'] == 'الاسم الأول'
    assert m['last_name'] == 'اسم العائلة'
    assert m['phone'] == 'الجوال'
    assert m['address'] == 'العنوان'


def test_guess_mapping_no_double_assign():
    # Only one header; it should bind to first_name, not also last_name.
    m = pi.guess_mapping(['Name'])
    bound = [k for k, v in m.items() if v == 'Name']
    assert len(bound) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_patient_import.py -k guess_mapping -v`
Expected: FAIL (`AttributeError: module 'patient_import' has no attribute 'guess_mapping'`).

- [ ] **Step 3: Write the implementation**

Add to `patient_import.py`:

```python
# Header synonyms per field (normalized: lowercased, non-alphanumeric stripped).
# Arabic kept as-is (normalization only lowercases/space-collapses for it).
_SYNONYMS = {
    'first_name': ['first name', 'firstname', 'fname', 'given name', 'first',
                   'name', 'patient name', 'full name',
                   'الاسم الاول', 'الاسم الأول', 'الاسم', 'اسم المريض', 'الاسم الكامل'],
    'last_name': ['last name', 'lastname', 'lname', 'surname', 'family name', 'last',
                  'اسم العائلة', 'العائلة', 'اللقب', 'الكنية'],
    'date_of_birth': ['date of birth', 'dob', 'birth date', 'birthdate', 'birthday',
                      'تاريخ الميلاد', 'الميلاد', 'تاريخ الولادة'],
    'phone': ['phone', 'phone number', 'mobile', 'mobile no', 'mobile number',
              'tel', 'telephone', 'cell', 'contact', 'contact number',
              'الهاتف', 'الجوال', 'الموبايل', 'رقم الهاتف', 'رقم الجوال', 'تليفون'],
    'email': ['email', 'e-mail', 'email address', 'mail',
              'البريد', 'البريد الالكتروني', 'الايميل', 'بريد الكتروني'],
    'address': ['address', 'addr', 'location', 'home address', 'residence',
                'العنوان', 'السكن', 'الموقع'],
    'gender': ['gender', 'sex', 'الجنس', 'النوع'],
    'medical_history': ['medical history', 'history', 'notes', 'medical notes',
                        'remarks', 'comments', 'medical',
                        'التاريخ الطبي', 'ملاحظات', 'الملاحظات', 'تاريخ مرضي', 'ملاحظات طبية'],
}


def _norm_header(h: str) -> str:
    h = (h or '').strip().lower()
    return ''.join(ch for ch in h if ch.isalnum() or ch.isspace() or '؀' <= ch <= 'ۿ')


def guess_mapping(headers: list[str]) -> dict[str, str | None]:
    norm = {h: ' '.join(_norm_header(h).split()) for h in headers}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for field in IMPORT_FIELDS:
        key = field['key']
        chosen = None
        for syn in _SYNONYMS[key]:
            syn_n = ' '.join(_norm_header(syn).split())
            for h in headers:
                if h in used:
                    continue
                if norm[h] == syn_n:
                    chosen = h
                    break
            if chosen:
                break
        if chosen:
            used.add(chosen)
        mapping[key] = chosen
    return mapping
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_patient_import.py -k guess_mapping -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add patient_import.py tests/test_patient_import.py
git commit -m "feat: patient_import.guess_mapping (bilingual EN/AR header auto-detect)"
```

---

### Task 4: `parse_date` + `validate_rows`

**Files:**
- Modify: `patient_import.py`
- Test: `tests/test_patient_import.py`

**Interfaces:**
- Produces:
  - `parse_date(value: str, date_format: str) -> str | None` — returns canonical `YYYY-MM-DD` or `None` if a non-blank value doesn't match the format. Blank → returns `''`.
  - `validate_rows(rows, mapping, date_format) -> tuple[list[dict], list[dict]]` — returns `(clean, problems)`. Each `clean` dict has all 8 field keys (unmapped/blank → `''`) plus `row_number: int` (1-based over data rows). Each `problems` dict is `{'row_number': int, 'reason': str}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_patient_import.py`:

```python
_FIELDS_ALL = {f['key'] for f in pi.IMPORT_FIELDS}


def test_parse_date_formats():
    assert pi.parse_date('04/03/2020', 'DD/MM/YYYY') == '2020-03-04'
    assert pi.parse_date('03/04/2020', 'MM/DD/YYYY') == '2020-03-04'
    assert pi.parse_date('2020-03-04', 'YYYY-MM-DD') == '2020-03-04'
    assert pi.parse_date('', 'DD/MM/YYYY') == ''
    assert pi.parse_date('32/13/2020', 'DD/MM/YYYY') is None


def test_validate_rows_clean():
    rows = [{'F': 'Ali', 'L': 'Hassan', 'D': '04/03/2020', 'P': '0501'}]
    mapping = {'first_name': 'F', 'last_name': 'L', 'date_of_birth': 'D', 'phone': 'P',
               'email': None, 'address': None, 'gender': None, 'medical_history': None}
    clean, problems = pi.validate_rows(rows, mapping, 'DD/MM/YYYY')
    assert problems == []
    assert clean[0]['first_name'] == 'Ali'
    assert clean[0]['date_of_birth'] == '2020-03-04'
    assert clean[0]['email'] == ''
    assert clean[0]['row_number'] == 1
    assert _FIELDS_ALL.issubset(clean[0].keys())


def test_validate_rows_missing_required_becomes_problem():
    rows = [{'F': '', 'L': 'Hassan'}]
    mapping = {'first_name': 'F', 'last_name': 'L', 'date_of_birth': None, 'phone': None,
               'email': None, 'address': None, 'gender': None, 'medical_history': None}
    clean, problems = pi.validate_rows(rows, mapping, 'DD/MM/YYYY')
    assert clean == []
    assert problems[0]['row_number'] == 1
    assert 'first name' in problems[0]['reason'].lower()


def test_validate_rows_bad_date_becomes_problem():
    rows = [{'F': 'Ali', 'L': 'Hassan', 'D': '99/99/9999'}]
    mapping = {'first_name': 'F', 'last_name': 'L', 'date_of_birth': 'D', 'phone': None,
               'email': None, 'address': None, 'gender': None, 'medical_history': None}
    clean, problems = pi.validate_rows(rows, mapping, 'DD/MM/YYYY')
    assert clean == []
    assert 'date' in problems[0]['reason'].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_patient_import.py -k "parse_date or validate_rows" -v`
Expected: FAIL (`AttributeError: ... 'parse_date'`).

- [ ] **Step 3: Write the implementation**

Add to `patient_import.py`:

```python
def parse_date(value: str, date_format: str) -> str | None:
    value = (value or '').strip()
    if not value:
        return ''
    fmt = DATE_FORMATS.get(date_format, DATE_FORMATS['DD/MM/YYYY'])
    try:
        return datetime.datetime.strptime(value[:10], fmt).strftime('%Y-%m-%d')
    except ValueError:
        return None


def validate_rows(rows, mapping, date_format):
    clean, problems = [], []
    for i, raw in enumerate(rows, start=1):
        record = {}
        for field in IMPORT_FIELDS:
            key = field['key']
            header = mapping.get(key)
            record[key] = (raw.get(header) or '').strip() if header else ''
        reason = None
        if not record['first_name']:
            reason = 'missing first name'
        elif not record['last_name']:
            reason = 'missing last name'
        else:
            dob = parse_date(record['date_of_birth'], date_format)
            if dob is None:
                reason = f"unparseable date of birth: {record['date_of_birth']!r}"
            else:
                record['date_of_birth'] = dob
        if reason:
            problems.append({'row_number': i, 'reason': reason})
        else:
            record['row_number'] = i
            clean.append(record)
    return clean, problems
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_patient_import.py -k "parse_date or validate_rows" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add patient_import.py tests/test_patient_import.py
git commit -m "feat: patient_import.parse_date + validate_rows"
```

---

### Task 5: `build_existing_index` + `flag_duplicates`

**Files:**
- Modify: `patient_import.py`
- Test: `tests/test_patient_import.py`

**Interfaces:**
- Produces:
  - `build_existing_index(cursor) -> set[tuple[str,str]]` — `(name_key, phone_digits)` for every existing patient.
  - `flag_duplicates(clean: list[dict], existing_index: set) -> list[dict]` — returns the same rows with an added `is_duplicate: bool`. A row is a duplicate if its key is in `existing_index` or matched an earlier row in `clean`.
  - `_dup_key(first, last, phone) -> tuple[str,str]` — helper (also used by the commit endpoint).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_patient_import.py`:

```python
def _clean(first, last, phone):
    return {'first_name': first, 'last_name': last, 'phone': phone, 'row_number': 1}


def test_flag_duplicates_within_file():
    rows = [_clean('Ali', 'Hassan', '0501'), _clean('ali', 'hassan', '0501')]
    out = pi.flag_duplicates(rows, set())
    assert out[0]['is_duplicate'] is False
    assert out[1]['is_duplicate'] is True


def test_flag_duplicates_vs_existing():
    idx = {pi._dup_key('Ali', 'Hassan', '0501')}
    out = pi.flag_duplicates([_clean('Ali', 'Hassan', '0501')], idx)
    assert out[0]['is_duplicate'] is True


def test_flag_duplicates_name_match_different_phone_is_not_dup():
    idx = {pi._dup_key('Ali', 'Hassan', '0501')}
    out = pi.flag_duplicates([_clean('Ali', 'Hassan', '9999')], idx)
    assert out[0]['is_duplicate'] is False


def test_flag_duplicates_same_name_both_blank_phone_is_dup():
    rows = [_clean('Ali', 'Hassan', ''), _clean('Ali', 'Hassan', '')]
    out = pi.flag_duplicates(rows, set())
    assert out[1]['is_duplicate'] is True


def test_build_existing_index(tmp_path):
    import sqlite3
    db = tmp_path / 'x.db'
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name TEXT, '
                 'last_name TEXT, phone TEXT)')
    conn.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('Ali','Hassan','050-1')")
    conn.commit()
    idx = pi.build_existing_index(conn.cursor())
    assert pi._dup_key('Ali', 'Hassan', '0501') in idx   # phone digits-only
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_patient_import.py -k "duplicates or existing_index" -v`
Expected: FAIL (`AttributeError: ... 'flag_duplicates'`).

- [ ] **Step 3: Write the implementation**

Add to `patient_import.py`:

```python
def _digits(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def _dup_key(first: str, last: str, phone: str) -> tuple[str, str]:
    return (patient_dedupe.normalize_name(first, last), _digits(phone))


def build_existing_index(cursor) -> set[tuple[str, str]]:
    cursor.execute('SELECT first_name, last_name, phone FROM patients')
    return {_dup_key(r[0], r[1], r[2]) for r in cursor.fetchall()}


def flag_duplicates(clean: list[dict], existing_index: set) -> list[dict]:
    seen = set(existing_index)
    out = []
    for row in clean:
        key = _dup_key(row.get('first_name', ''), row.get('last_name', ''), row.get('phone', ''))
        is_dup = key in seen
        marked = dict(row)
        marked['is_duplicate'] = is_dup
        out.append(marked)
        seen.add(key)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_patient_import.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add patient_import.py tests/test_patient_import.py
git commit -m "feat: patient_import.flag_duplicates + build_existing_index"
```

---

### Task 6: Preview endpoint `POST /api/data/import-patients/preview`

**Files:**
- Modify: `dental_clinic.py` (add route near the other `/api/data/*` routes, ~line 4192; add both new paths to `_AUTH_REQUIRED_EXACT` at line 1957)
- Test: `tests/test_import_patients_api.py`

**Interfaces:**
- Consumes: `patient_import.read_table/guess_mapping/validate_rows/build_existing_index/flag_duplicates`, `IMPORT_FIELDS`, `DATE_FORMATS`.
- Produces: JSON `{headers, fields, suggested_mapping, date_format, rows_total, counts:{valid,problems,duplicates}, preview:[{row_number, values, status, reason?}]}`. `status` ∈ `valid|problem|duplicate`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_import_patients_api.py`:

```python
import io

import openpyxl
import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db = data_dir / 'dental_clinic.db'
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def _csv_upload(text, name='patients.csv'):
    return {'file': (io.BytesIO(text.encode('utf-8')), name)}


def test_preview_requires_login(client):
    assert client.post('/api/data/import-patients/preview').status_code == 401


def test_preview_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    r = client.post('/api/data/import-patients/preview',
                    data=_csv_upload('First Name,Last Name\nAli,Hassan\n'),
                    content_type='multipart/form-data')
    assert r.status_code == 404


def test_preview_returns_mapping_and_counts(client):
    _login(client)
    csv_text = ('First Name,Last Name,Mobile,DOB\n'
                'Ali,Hassan,0501,04/03/2020\n'
                ',Saleh,0502,\n')                      # missing first name -> problem
    r = client.post('/api/data/import-patients/preview',
                    data=_csv_upload(csv_text), content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_json()
    assert body['suggested_mapping']['first_name'] == 'First Name'
    assert body['suggested_mapping']['phone'] == 'Mobile'
    assert body['counts']['valid'] == 1
    assert body['counts']['problems'] == 1
    assert body['rows_total'] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_import_patients_api.py -v`
Expected: FAIL — `test_preview_requires_login` fails (route 404s, not 401) because the route doesn't exist / isn't gated yet.

- [ ] **Step 3: Add the import + auth-gate entries**

Near the top imports of `dental_clinic.py` (where `db_import`, `db_merge`, `patient_dedupe` are imported), add:

```python
import patient_import
```

In `_AUTH_REQUIRED_EXACT` (line 1957), add the two new paths inside the set literal:

```python
                        '/api/data/duplicate-patients', '/api/data/merge-patients',
                        '/api/data/import-patients/preview',
                        '/api/data/import-patients/commit'}
```

- [ ] **Step 4: Write the preview route**

Add after `data_merge_patients` (~line 4235) in `dental_clinic.py`:

```python
# Caps that bound import memory/time. See docs/superpowers/specs/2026-06-20-bulk-patient-csv-import-design.md.
_IMPORT_MAX_BYTES = 10 * 1024 * 1024
_IMPORT_MAX_ROWS = 20_000


def _read_import_file():
    """Resolve the uploaded import file to (headers, rows) or (None, None, error_response)."""
    file = request.files.get('file')
    if not file or not file.filename:
        return None, None, (jsonify({'error': 'No file uploaded'}), 400)
    data = file.read()
    if len(data) > _IMPORT_MAX_BYTES:
        return None, None, (jsonify({'error': 'File too large (max 10 MB)'}), 400)
    try:
        headers, rows = patient_import.read_table(file.filename, data)
    except ValueError as exc:
        return None, None, (jsonify({'error': f'Could not read file: {exc}'}), 400)
    if len(rows) > _IMPORT_MAX_ROWS:
        return None, None, (jsonify({'error': 'Too many rows (max 20,000)'}), 400)
    return headers, rows, None


@app.route('/api/data/import-patients/preview', methods=['POST'])
def data_import_patients_preview():
    """Dry-run: parse + auto-map + validate + flag duplicates, no DB writes.
    Desktop-only. The client re-sends the file (with finalized mapping) to commit."""
    if CLOUD_MODE:
        return jsonify({'error': 'Not available on the cloud node'}), 404
    headers, rows, err = _read_import_file()
    if err:
        return err
    date_format = request.form.get('date_format') or 'DD/MM/YYYY'
    supplied = request.form.get('mapping')
    if supplied:
        try:
            mapping = json.loads(supplied)
        except ValueError:
            return jsonify({'error': 'Invalid mapping'}), 400
    else:
        mapping = patient_import.guess_mapping(headers)

    clean, problems = patient_import.validate_rows(rows, mapping, date_format)
    conn = sqlite3.connect(str(DB_NAME))
    try:
        index = patient_import.build_existing_index(conn.cursor())
    finally:
        conn.close()
    flagged = patient_import.flag_duplicates(clean, index)

    preview = []
    for row in flagged:
        status = 'duplicate' if row['is_duplicate'] else 'valid'
        values = {f['key']: row.get(f['key'], '') for f in patient_import.IMPORT_FIELDS}
        preview.append({'row_number': row['row_number'], 'values': values, 'status': status})
    for prob in problems:
        preview.append({'row_number': prob['row_number'], 'values': {},
                        'status': 'problem', 'reason': prob['reason']})
    preview.sort(key=lambda p: p['row_number'])

    dup_count = sum(1 for r in flagged if r['is_duplicate'])
    return jsonify({
        'headers': headers,
        'fields': patient_import.IMPORT_FIELDS,
        'date_formats': list(patient_import.DATE_FORMATS.keys()),
        'suggested_mapping': mapping,
        'date_format': date_format,
        'rows_total': len(rows),
        'counts': {'valid': len(flagged) - dup_count, 'duplicates': dup_count,
                   'problems': len(problems)},
        'preview': preview,
    })
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_import_patients_api.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_import_patients_api.py
git commit -m "feat: /api/data/import-patients/preview (dry-run, auth+cloud gated)"
```

---

### Task 7: Commit endpoint `POST /api/data/import-patients/commit`

**Files:**
- Modify: `dental_clinic.py` (add route after the preview route)
- Test: `tests/test_import_patients_api.py`

**Interfaces:**
- Consumes: `patient_import.*`, `run_database_backup()`, `append_audit_log(cursor, action_type, entity_type, entity_id, details)`.
- Produces: JSON `{success: True, imported: int, skipped: int, skipped_report: [{row_number, reason}], backup_path}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_patients_api.py`:

```python
def _commit(client, csv_text, **form):
    data = {'file': (io.BytesIO(csv_text.encode('utf-8')), 'patients.csv'),
            'date_format': form.get('date_format', 'DD/MM/YYYY')}
    if 'mapping' in form:
        data['mapping'] = form['mapping']
    if 'import_duplicates' in form:
        data['import_duplicates'] = form['import_duplicates']
    return client.post('/api/data/import-patients/commit', data=data,
                       content_type='multipart/form-data')


def test_commit_requires_login(client):
    assert client.post('/api/data/import-patients/commit').status_code == 401


def test_commit_imports_valid_skips_problems(client):
    _login(client)
    csv_text = ('First Name,Last Name,Mobile,DOB\n'
                'Ali,Hassan,0501,04/03/2020\n'
                ',Saleh,0502,\n')
    r = _commit(client, csv_text)
    assert r.status_code == 200
    body = r.get_json()
    assert body['imported'] == 1
    assert body['skipped'] == 1
    # The imported patient is now visible.
    listing = client.get('/api/patients').get_json()
    assert any(p['last_name'] == 'Hassan' for p in listing)
    assert all(p['last_name'] != 'Saleh' for p in listing)


def test_commit_skips_duplicates_by_default_then_imports_when_opted_in(client):
    _login(client)
    csv_text = 'First Name,Last Name,Mobile\nAli,Hassan,0501\nAli,Hassan,0501\n'
    body = _commit(client, csv_text).get_json()
    assert body['imported'] == 1 and body['skipped'] == 1
    # Opt in: the in-file duplicate now imports too (and both collide with the
    # one already stored, so 2 more come in).
    body2 = _commit(client, csv_text, import_duplicates='true').get_json()
    assert body2['imported'] == 2


def test_commit_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert _commit(client, 'First Name,Last Name\nAli,Hassan\n').status_code == 404


def test_commit_writes_audit_log(client):
    _login(client)
    _commit(client, 'First Name,Last Name\nAli,Hassan\n')
    import sqlite3
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    n = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action_type='import'").fetchone()[0]
    conn.close()
    assert n == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_import_patients_api.py -k commit -v`
Expected: FAIL — `test_commit_requires_login` fails (route doesn't exist).

- [ ] **Step 3: Write the commit route**

Add after `data_import_patients_preview` in `dental_clinic.py`:

```python
@app.route('/api/data/import-patients/commit', methods=['POST'])
def data_import_patients_commit():
    """Re-parse + re-validate the file with the finalized mapping, then insert the
    valid (non-skipped) rows in one transaction. Backup-first; full rollback on
    unexpected failure. Desktop-only."""
    if CLOUD_MODE:
        return jsonify({'error': 'Not available on the cloud node'}), 404
    headers, rows, err = _read_import_file()
    if err:
        return err
    date_format = request.form.get('date_format') or 'DD/MM/YYYY'
    import_duplicates = (request.form.get('import_duplicates') or '').lower() in ('1', 'true', 'yes', 'on')
    supplied = request.form.get('mapping')
    if supplied:
        try:
            mapping = json.loads(supplied)
        except ValueError:
            return jsonify({'error': 'Invalid mapping'}), 400
    else:
        mapping = patient_import.guess_mapping(headers)

    clean, problems = patient_import.validate_rows(rows, mapping, date_format)
    skipped_report = list(problems)

    backups = run_database_backup()
    backup_path = backups[0] if backups else None
    conn = sqlite3.connect(str(DB_NAME))
    cursor = conn.cursor()
    try:
        index = patient_import.build_existing_index(cursor)
        flagged = patient_import.flag_duplicates(clean, index)
        imported = 0
        for row in flagged:
            if row['is_duplicate'] and not import_duplicates:
                skipped_report.append({'row_number': row['row_number'], 'reason': 'duplicate'})
                continue
            cursor.execute(
                '''INSERT INTO patients (first_name, last_name, date_of_birth, phone,
                                         email, address, gender, medical_history)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (row['first_name'], row['last_name'], row['date_of_birth'] or None,
                 row['phone'], row['email'], row['address'], row['gender'],
                 row['medical_history']))
            imported += 1
        append_audit_log(cursor, 'import', 'patient', None,
                         {'imported': imported, 'skipped': len(skipped_report)})
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — any failure must roll back the whole import
        conn.rollback()
        app.logger.exception('Patient import failed')
        return jsonify({'error': f'Import failed and was rolled back: {type(exc).__name__}: {exc}',
                        'backup_path': backup_path}), 500
    finally:
        conn.close()
    skipped_report.sort(key=lambda p: p['row_number'])
    return jsonify({'success': True, 'imported': imported, 'skipped': len(skipped_report),
                    'skipped_report': skipped_report, 'backup_path': backup_path})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_import_patients_api.py -v`
Expected: PASS (all preview + commit tests).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `python -m pytest tests/ -q`
Expected: exit code 0 (`echo $LASTEXITCODE` → 0). The CSRF conftest auto-attaches tokens so existing POSTs still pass.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_import_patients_api.py
git commit -m "feat: /api/data/import-patients/commit (backup-first, audit, dup override)"
```

---

### Task 8: Data Tools UI — import card, mapping/preview panel, commit

**Files:**
- Modify: `templates.py` (markup ~line 2966 in `.data-tools-actions`; new panel after `#dup-review-panel` line 2969; JS after `renderDuplicateGroups` ~line 6620)

**Interfaces:**
- Consumes: `POST /api/data/import-patients/preview` and `/commit`; existing JS helpers `showToast`, `escapeHtml`, `t`, `currentLanguage`.
- Produces: a working import flow in Settings → Data Tools.

- [ ] **Step 1: Add the button + hidden file input**

In `templates.py`, inside `.data-tools-actions` (after the "Find duplicate patients" button at line 2966), add:

```html
                    <label class="btn" for="import-patients-file" style="cursor:pointer;" data-en="📥 Import patients" data-ar="📥 استيراد المرضى">📥 Import patients</label>
                    <input type="file" id="import-patients-file" accept=".csv,.xlsx" style="display:none" onchange="startPatientImport(this)">
```

- [ ] **Step 2: Add the review panel container**

After `<div id="dup-review-panel" ...></div>` (line 2969), add:

```html
                  <div id="import-review-panel" class="dup-review" style="display:none;"></div>
```

- [ ] **Step 3: Add the JS (preview → mapping UI → commit)**

In `templates.py`, after the `renderDuplicateGroups` function (~line 6620, before the closing of the duplicate-finder block), add:

```javascript
        // ── Bulk patient import ──────────────────────────────────────────────
        let _importFile = null;

        async function startPatientImport(input) {
          _importFile = input.files && input.files[0];
          input.value = '';
          if (!_importFile) return;
          await refreshImportPreview(null, 'DD/MM/YYYY');
        }

        async function refreshImportPreview(mapping, dateFormat) {
          const panel = document.getElementById('import-review-panel');
          panel.style.display = '';
          panel.innerHTML = `<div class="muted">${t('importing_preview', 'Reading file…')}</div>`;
          const fd = new FormData();
          fd.append('file', _importFile);
          fd.append('date_format', dateFormat);
          if (mapping) fd.append('mapping', JSON.stringify(mapping));
          try {
            const r = await fetch('/api/data/import-patients/preview', { method: 'POST', body: fd });
            const b = await r.json();
            if (!r.ok) throw new Error(b.error || 'failed');
            renderImportPreview(b);
          } catch (e) {
            panel.innerHTML = '';
            showToast((currentLanguage === 'ar' ? 'تعذّر قراءة الملف: ' : 'Could not read file: ') + (e.message || e), 'error');
          }
        }

        function _currentMappingFromUI() {
          const mapping = {};
          document.querySelectorAll('.import-map-select').forEach(sel => {
            mapping[sel.dataset.field] = sel.value || null;
          });
          return mapping;
        }

        function renderImportPreview(b) {
          const panel = document.getElementById('import-review-panel');
          const ar = currentLanguage === 'ar';
          const fieldLabel = (k) => ({
            first_name: ar ? 'الاسم الأول' : 'First name', last_name: ar ? 'اسم العائلة' : 'Last name',
            date_of_birth: ar ? 'تاريخ الميلاد' : 'Date of birth', phone: ar ? 'الهاتف' : 'Phone',
            email: ar ? 'البريد' : 'Email', address: ar ? 'العنوان' : 'Address',
            gender: ar ? 'الجنس' : 'Gender', medical_history: ar ? 'التاريخ الطبي' : 'Medical history'
          }[k] || k);
          const opt = (h, sel) => `<option value="${escapeHtml(h)}" ${h === sel ? 'selected' : ''}>${escapeHtml(h)}</option>`;
          const noneLbl = ar ? '— لا يُستورد —' : '— not imported —';

          const mapRows = b.fields.map(f => {
            const sel = b.suggested_mapping[f.key] || '';
            const opts = `<option value="">${noneLbl}</option>` + b.headers.map(h => opt(h, sel)).join('');
            const req = f.required ? ' *' : '';
            return `<div class="import-map-row"><label>${fieldLabel(f.key)}${req}</label>
              <select class="import-map-select" data-field="${f.key}" onchange="onImportMappingChange()">${opts}</select></div>`;
          }).join('');

          const dfOpts = b.date_formats.map(d => `<option value="${d}" ${d === b.date_format ? 'selected' : ''}>${d}</option>`).join('');
          const c = b.counts;
          const badge = (s) => `<span class="import-badge import-badge--${s}">${s === 'valid' ? (ar ? 'صالح' : 'valid') : s === 'duplicate' ? (ar ? 'مكرر' : 'duplicate') : (ar ? 'مشكلة' : 'problem')}</span>`;
          const previewRows = b.preview.slice(0, 200).map(p => {
            const name = `${escapeHtml(p.values.first_name || '')} ${escapeHtml(p.values.last_name || '')}`.trim();
            const detail = p.status === 'problem' ? escapeHtml(p.reason || '') : escapeHtml(p.values.phone || '');
            return `<tr><td>${p.row_number}</td><td>${name || '—'}</td><td>${detail}</td><td>${badge(p.status)}</td></tr>`;
          }).join('');

          panel.innerHTML = `
            <h4>${ar ? 'مطابقة الأعمدة' : 'Match columns'}</h4>
            <div class="import-map-grid">${mapRows}</div>
            <div class="import-controls">
              <label>${ar ? 'صيغة التاريخ' : 'Date format'}
                <select id="import-date-format" onchange="onImportMappingChange()">${dfOpts}</select></label>
              <label><input type="checkbox" id="import-dups" onchange="onImportMappingChange()">
                ${ar ? 'استيراد المكرر أيضًا' : 'Import duplicates anyway'}</label>
            </div>
            <div class="import-summary">${ar
              ? `${c.valid} للاستيراد · ${c.problems} مشكلة · ${c.duplicates} مكرر`
              : `${c.valid} to import · ${c.problems} problems · ${c.duplicates} duplicates`}</div>
            <div class="table-container" style="max-height:280px;overflow:auto;">
              <table><thead><tr><th>#</th><th>${ar ? 'الاسم' : 'Name'}</th><th>${ar ? 'تفاصيل' : 'Detail'}</th><th></th></tr></thead>
              <tbody>${previewRows}</tbody></table></div>
            <div class="import-actions" style="margin-top:10px;display:flex;gap:8px;">
              <button class="btn btn-primary" onclick="commitPatientImport()">${ar ? `استيراد ${c.valid} مريض` : `Import ${c.valid} patients`}</button>
              <button class="btn" onclick="cancelPatientImport()">${ar ? 'إلغاء' : 'Cancel'}</button>
            </div>`;
          panel.dataset.importDups = '';
        }

        function onImportMappingChange() {
          const dateFormat = document.getElementById('import-date-format').value;
          refreshImportPreview(_currentMappingFromUI(), dateFormat);
        }

        function cancelPatientImport() {
          _importFile = null;
          const panel = document.getElementById('import-review-panel');
          panel.style.display = 'none';
          panel.innerHTML = '';
        }

        async function commitPatientImport() {
          if (!_importFile) return;
          const ar = currentLanguage === 'ar';
          const fd = new FormData();
          fd.append('file', _importFile);
          fd.append('date_format', document.getElementById('import-date-format').value);
          fd.append('mapping', JSON.stringify(_currentMappingFromUI()));
          fd.append('import_duplicates', document.getElementById('import-dups').checked ? 'true' : 'false');
          try {
            const r = await fetch('/api/data/import-patients/commit', { method: 'POST', body: fd });
            const b = await r.json();
            if (!r.ok) throw new Error(b.error || 'failed');
            showToast(ar ? `تم استيراد ${b.imported} مريض، وتخطّي ${b.skipped}` : `Imported ${b.imported} patients, skipped ${b.skipped}`, 'success');
            const panel = document.getElementById('import-review-panel');
            if (b.skipped_report && b.skipped_report.length) {
              panel.innerHTML = `<h4>${ar ? 'صفوف تم تخطّيها' : 'Skipped rows'}</h4>
                <div class="table-container" style="max-height:240px;overflow:auto;">
                <table><thead><tr><th>#</th><th>${ar ? 'السبب' : 'Reason'}</th></tr></thead><tbody>
                ${b.skipped_report.map(s => `<tr><td>${s.row_number}</td><td>${escapeHtml(s.reason)}</td></tr>`).join('')}
                </tbody></table></div>
                <button class="btn" onclick="cancelPatientImport()" style="margin-top:8px;">${ar ? 'إغلاق' : 'Close'}</button>`;
            } else {
              cancelPatientImport();
            }
            _importFile = null;
            if (typeof loadAuditLogs === 'function') loadAuditLogs();
          } catch (e) {
            showToast((ar ? 'فشل الاستيراد: ' : 'Import failed: ') + (e.message || e), 'error');
          }
        }
```

- [ ] **Step 4: Add minimal styles**

Find the `.dup-review` style block in `templates.py` (the CSS for the duplicate panel) and add nearby:

```css
        .import-map-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px 14px; margin:8px 0; }
        .import-map-row { display:flex; flex-direction:column; font-size:0.85em; }
        .import-map-row select { padding:4px; }
        .import-controls { display:flex; gap:16px; align-items:center; flex-wrap:wrap; margin:8px 0; font-size:0.88em; }
        .import-summary { font-weight:600; margin:6px 0; }
        .import-badge { padding:1px 7px; border-radius:10px; font-size:0.75em; }
        .import-badge--valid { background:#dcfce7; color:#166534; }
        .import-badge--duplicate { background:#fef9c3; color:#854d0e; }
        .import-badge--problem { background:#fee2e2; color:#991b1b; }
```

- [ ] **Step 5: Verify the templates still render (no JS-escaping break)**

Run: `python -c "import templates; print(len(templates.HTML_TEMPLATE))"`
Expected: prints an integer, no exception. (Per `reference_templates_js_escaping`: `HTML_TEMPLATE` is a normal Python string — verify it still imports cleanly.)

- [ ] **Step 6: Run the full suite again**

Run: `python -m pytest tests/ -q`
Expected: exit code 0.

- [ ] **Step 7: Commit**

```bash
git add templates.py
git commit -m "feat: Data Tools patient-import UI (mapping, preview, commit; EN/AR)"
```

---

## Self-Review

**1. Spec coverage:**
- §3.1 module (read_table/guess_mapping/validate_rows/flag_duplicates) → Tasks 2–5. ✓
- §3.2 endpoints (preview/commit, cloud+auth gated) → Tasks 6–7. ✓
- §5 fields/validation/date/dups → Tasks 4–5 + commit INSERT (Task 7). ✓
- §6 safety (backup-first, transaction, audit, caps, CSRF) → Task 7 + `_read_import_file` caps (Task 6); CSRF is automatic (same-origin fetch) — no code needed. ✓
- §7 UI → Task 8. ✓
- §9 build (openpyxl dep + bundle) → Task 1. ✓
- §10 tests → Tasks 2–7 carry their tests. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**3. Type consistency:**
- `_dup_key(first,last,phone)` defined in Task 5, reused in tests + `build_existing_index`. ✓
- `validate_rows` returns rows carrying all 8 field keys + `row_number`; `flag_duplicates` adds `is_duplicate`; commit reads exactly those keys for the INSERT. ✓
- Preview/commit both call `_read_import_file()` (defined in Task 6). ✓
- `import_patients/preview` + `/commit` paths added to `_AUTH_REQUIRED_EXACT` (Task 6 step 3) — covers both routes. ✓

**Note for the implementer:** Task 8 (UI) has no automated assertion beyond template-import + full-suite-green; do a manual desktop visual check (or Playwright smoke per `reference_web_visual_smoke`) of the import flow before considering it done.
