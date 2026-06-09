# tests/test_db_import.py
"""Bundle / file-validation helpers for the data-tools import surface."""
import sqlite3
import zipfile

import pytest

import db_import


def test_is_sqlite_file_true_for_real_db(tmp_path):
    db = tmp_path / 'real.db'
    sqlite3.connect(str(db)).close()
    assert db_import.is_sqlite_file(str(db)) is True


def test_is_sqlite_file_false_for_junk(tmp_path):
    junk = tmp_path / 'junk.bin'
    junk.write_bytes(b'PK\x03\x04 not a db')
    assert db_import.is_sqlite_file(str(junk)) is False


def test_build_then_extract_bundle_roundtrip(tmp_path):
    db = tmp_path / 'dental_clinic.db'
    sqlite3.connect(str(db)).close()
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    (uploads / 'x.png').write_bytes(b'img')
    bundle = tmp_path / 'bundle.zip'

    db_import.build_bundle(str(bundle), str(db), str(uploads))
    out = tmp_path / 'out'
    db_path, uploads_dir = db_import.extract_bundle(str(bundle), str(out))

    assert db_import.is_sqlite_file(db_path)
    assert (uploads_dir is not None) and (out / 'uploads' / 'x.png').exists()


def test_extract_bundle_rejects_zip_slip(tmp_path):
    evil = tmp_path / 'evil.zip'
    with zipfile.ZipFile(str(evil), 'w') as z:
        z.writestr('../escape.txt', 'pwned')
    with pytest.raises(ValueError):
        db_import.extract_bundle(str(evil), str(tmp_path / 'out'))
