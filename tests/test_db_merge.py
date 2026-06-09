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
