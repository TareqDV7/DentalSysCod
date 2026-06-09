"""Engine tests for additive cross-clinic database merge (db_merge.py).

Builds two independent clinic DBs with COLLIDING primary-key ids, merges
source into destination, and asserts the destination keeps its own data while
the source's records arrive under fresh ids with every foreign key rewritten.
"""
import sqlite3

import pytest

import dental_clinic
import db_merge


def _new_db(path):
    """Create a real, fully-migrated clinic DB at `path` and return a Row-factory
    connection. Reuses dental_clinic.init_database by pointing DB_NAME at it."""
    prev = dental_clinic.DB_NAME
    dental_clinic.DB_NAME = str(path)
    try:
        dental_clinic.init_database()
    finally:
        dental_clinic.DB_NAME = prev
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def test_merge_report_starts_empty():
    report = db_merge.MergeReport()
    assert report.total_added() == 0
    assert report.warnings == []
    assert report.images_copied == 0


def test_copy_table_remaps_fk_and_assigns_new_id(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    # Destination already has a patient at id=1 (occupies the colliding id).
    dst.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Dst', 'Existing')")
    dst.commit()
    # Source patient id=1 ('Src One') and an appointment for them.
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'Src', 'One')")
    src.execute("INSERT INTO appointments (id, patient_id, appointment_date) VALUES (5, 1, '2026-01-01')")
    src.commit()

    remaps = {}
    patient_map = db_merge._copy_table(dst.cursor(), src.cursor(), 'patients', {}, remaps, db_merge.MergeReport())
    remaps['patients'] = patient_map
    appt_map = db_merge._copy_table(dst.cursor(), src.cursor(), 'appointments',
                                    {'patient_id': 'patients'}, remaps, db_merge.MergeReport())
    dst.commit()

    # Source patient id=1 must have landed under a NEW id (not 1 — that's taken).
    new_pid = patient_map[1]
    assert new_pid != 1
    row = dst.execute('SELECT first_name, last_name FROM patients WHERE id = ?', (new_pid,)).fetchone()
    assert (row['first_name'], row['last_name']) == ('Src', 'One')
    # The destination's original patient is untouched.
    assert dst.execute("SELECT first_name FROM patients WHERE id = 1").fetchone()['first_name'] == 'Dst'
    # The appointment's patient_id was rewritten to the new patient id.
    new_aid = appt_map[5]
    assert dst.execute('SELECT patient_id FROM appointments WHERE id = ?', (new_aid,)).fetchone()['patient_id'] == new_pid
