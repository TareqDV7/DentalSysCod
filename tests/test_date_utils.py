import pytest

from dental_clinic import (
    normalize_date_input,
    parse_date_input,
    format_date_display,
    normalize_datetime_input,
    is_friday_datetime,
)


def test_parse_date_input_basic_formats():
    assert parse_date_input('2026-05-06') == '2026-05-06'
    assert parse_date_input('06/05/2026') == '2026-05-06'
    assert parse_date_input('06-05-2026') == '2026-05-06'
    assert parse_date_input('') is None
    assert parse_date_input(None) is None


def test_format_date_display():
    assert format_date_display('2026-05-06') == '06/05/2026'
    assert format_date_display('') == ''
    assert format_date_display(None) == ''


def test_normalize_date_input_iso_and_date():
    assert normalize_date_input('2026-05-06') == '2026-05-06'
    assert normalize_date_input('2026-05-06T12:34:56') == '2026-05-06'


def test_normalize_datetime_input_and_errors():
    assert normalize_datetime_input('2026-05-06T12:34:56') == '2026-05-06 12:34:56'
    with pytest.raises(ValueError):
        normalize_datetime_input('')


def test_is_friday_datetime():
    # 2026-05-08 is a Friday
    assert is_friday_datetime('2026-05-08T09:00:00') is True
    assert is_friday_datetime('') is False
    assert is_friday_datetime('not-a-date') is False
