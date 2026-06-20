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
