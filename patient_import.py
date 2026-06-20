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


def read_table(filename: str, data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if not data:
        raise ValueError('file is empty')
    name = (filename or '').lower()
    if name.endswith('.xlsx') or data[:4] == b'PK\x03\x04':
        return _read_xlsx(data)
    return _read_csv(data)


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
