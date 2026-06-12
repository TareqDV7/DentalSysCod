"""Startup data-location helpers.

Which DB/serial a process is actually using, and detection of a second,
separately-activated install — the root cause behind the "serial drifts across
restarts" confusion, where the frozen service (%PROGRAMDATA%\\DentaCare) and a
source run (the repo folder) resolve different data dirs and each carry their
own activation.
"""
import sqlite3

import dental_clinic


def _make_db(path, serial=None):
    """A minimal DB with an app_settings table, optionally activated."""
    conn = sqlite3.connect(str(path))
    conn.execute('CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)')
    if serial is not None:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('active_serial_number', ?)",
            (serial,))
    conn.commit()
    conn.close()
    return str(path)


def test_read_active_serial_returns_stored_value(tmp_path):
    db = _make_db(tmp_path / 'a.db', 'DENTAL-AAA-0001')
    assert dental_clinic._read_active_serial(db) == 'DENTAL-AAA-0001'


def test_read_active_serial_blank_when_unset(tmp_path):
    db = _make_db(tmp_path / 'a.db', None)
    assert dental_clinic._read_active_serial(db) == ''


def test_read_active_serial_blank_on_missing_file(tmp_path):
    assert dental_clinic._read_active_serial(str(tmp_path / 'nope.db')) == ''


def test_other_activated_dbs_flags_a_different_serial(tmp_path):
    current = _make_db(tmp_path / 'current.db', 'DENTAL-SMD-0001')
    other = _make_db(tmp_path / 'other.db', 'DENTAL-AWDA-9999')
    conflicts = dental_clinic._other_activated_dbs(current, candidates=[other])
    assert conflicts == [(other, 'DENTAL-AWDA-9999')]


def test_other_activated_dbs_ignores_same_serial(tmp_path):
    current = _make_db(tmp_path / 'current.db', 'DENTAL-SMD-0001')
    other = _make_db(tmp_path / 'other.db', 'DENTAL-SMD-0001')
    assert dental_clinic._other_activated_dbs(current, candidates=[other]) == []


def test_other_activated_dbs_excludes_the_current_path(tmp_path):
    current = _make_db(tmp_path / 'current.db', 'DENTAL-SMD-0001')
    # current listed among the candidates must never report itself
    assert dental_clinic._other_activated_dbs(current, candidates=[current]) == []


def test_other_activated_dbs_ignores_unactivated_candidate(tmp_path):
    current = _make_db(tmp_path / 'current.db', 'DENTAL-SMD-0001')
    other = _make_db(tmp_path / 'other.db', None)
    assert dental_clinic._other_activated_dbs(current, candidates=[other]) == []


def test_other_activated_dbs_skips_missing_candidate(tmp_path):
    current = _make_db(tmp_path / 'current.db', 'DENTAL-SMD-0001')
    missing = str(tmp_path / 'nope.db')
    assert dental_clinic._other_activated_dbs(current, candidates=[missing]) == []
