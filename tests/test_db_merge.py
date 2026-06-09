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


def test_dedupe_catalog_by_name(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    # Use names not in the default seed set to get predictable IDs.
    dst.execute("INSERT INTO treatment_procedures (name, default_price) VALUES ('TestProc_A', 100)")
    dst.commit()
    dst_id = dst.execute("SELECT id FROM treatment_procedures WHERE name='TestProc_A'").fetchone()['id']
    src.execute("INSERT INTO treatment_procedures (id, name, default_price) VALUES (999, 'TestProc_A', 250)")
    src.execute("INSERT INTO treatment_procedures (id, name, default_price) VALUES (998, 'TestProc_B', 400)")
    src.commit()

    report = db_merge.MergeReport()
    id_map = db_merge._dedupe_catalog(dst.cursor(), src.cursor(), 'treatment_procedures', report)
    dst.commit()

    # 'TestProc_A' existed in dst -> reused, price NOT overwritten.
    assert id_map[999] == dst_id
    assert dst.execute("SELECT default_price FROM treatment_procedures WHERE id = ?", (dst_id,)).fetchone()[0] == 100
    # 'TestProc_B' was new -> inserted under a fresh id.
    assert id_map[998] != 998
    assert id_map[998] != 999
    names_in_dst = {r[0] for r in dst.execute("SELECT name FROM treatment_procedures").fetchall()}
    assert 'TestProc_A' in names_in_dst
    assert 'TestProc_B' in names_in_dst


def test_copy_expenses_remaps_followup_reference(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'S', 'One')")
    src.execute("INSERT INTO patient_followups (id, patient_id, followup_date) VALUES (9, 1, '2026-01-01')")
    # A followup-sourced expense (auto lab cost) referencing followup id 9 ...
    # (expenses.category is NOT NULL; there is no 'description' column.)
    src.execute("""INSERT INTO expenses (id, category, amount, source_type, reference_id, patient_id)
                   VALUES (4, 'Lab', 50, 'followup', 9, 1)""")
    # ... and a manual expense whose reference_id must be left untouched.
    src.execute("""INSERT INTO expenses (id, category, amount, source_type, reference_id)
                   VALUES (5, 'Rent', 800, 'manual', 999)""")
    src.commit()

    remaps = {
        'patients': {1: 100},
        'treatments': {},
        'patient_followups': {9: 700},
    }
    report = db_merge.MergeReport()
    db_merge._copy_expenses(dst.cursor(), src.cursor(), remaps, report)
    dst.commit()

    lab = dst.execute("SELECT patient_id, reference_id FROM expenses WHERE category = 'Lab'").fetchone()
    assert (lab['patient_id'], lab['reference_id']) == (100, 700)   # both links rewritten
    rent = dst.execute("SELECT reference_id FROM expenses WHERE category = 'Rent'").fetchone()
    assert rent['reference_id'] == 999                              # manual reference_id preserved


def test_copy_medical_images_copies_file_and_repaths(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src_uploads = tmp_path / 'src_uploads'
    dst_uploads = tmp_path / 'dst_uploads'
    src_uploads.mkdir(); dst_uploads.mkdir()
    img = src_uploads / 'xray1.png'
    img.write_bytes(b'\x89PNG fake bytes')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'S', 'One')")
    src.execute("""INSERT INTO medical_images (id, patient_id, file_name, file_path)
                   VALUES (1, 1, 'xray1.png', ?)""", (str(img),))
    src.commit()

    report = db_merge.MergeReport()
    remaps = {'patients': {1: 50}}
    db_merge._copy_medical_images(dst.cursor(), src.cursor(), remaps,
                                  str(src_uploads), str(dst_uploads), report)
    dst.commit()

    row = dst.execute("SELECT patient_id, file_name, file_path FROM medical_images").fetchone()
    assert row['patient_id'] == 50
    assert row['file_name'] == 'xray1.png'
    # File physically copied into the destination uploads dir, path rewritten there.
    import os
    assert os.path.dirname(row['file_path']) == str(dst_uploads)
    assert os.path.exists(row['file_path'])
    assert report.images_copied == 1


def test_copy_medical_images_skips_when_no_uploads(tmp_path):
    dst = _new_db(tmp_path / 'dst.db')
    src = _new_db(tmp_path / 'src.db')
    src.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'S', 'One')")
    src.execute("""INSERT INTO medical_images (id, patient_id, file_name, file_path)
                   VALUES (1, 1, 'x.png', '/nowhere/x.png')""")
    src.commit()
    report = db_merge.MergeReport()
    db_merge._copy_medical_images(dst.cursor(), src.cursor(), {'patients': {1: 50}},
                                  None, None, report)
    dst.commit()
    assert dst.execute("SELECT COUNT(*) FROM medical_images").fetchone()[0] == 0
    assert report.images_skipped == 1
    assert any('image' in w.lower() for w in report.warnings)
