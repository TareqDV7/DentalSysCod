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
