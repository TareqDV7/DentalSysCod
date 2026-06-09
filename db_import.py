# db_import.py
"""Pure helpers for the data-tools import/export surface: SQLite validation and
zip-bundle build/extract (zip-slip-safe). No Flask."""
from __future__ import annotations

import os
import sqlite3
import zipfile

_SQLITE_MAGIC = b'SQLite format 3\x00'
_DB_MEMBER = 'dental_clinic.db'
_UPLOADS_PREFIX = 'uploads/'


def is_sqlite_file(path: str) -> bool:
    try:
        with open(path, 'rb') as fh:
            return fh.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def build_bundle(zip_path: str, db_path: str, uploads_dir: str | None) -> None:
    """Write a .zip containing the DB as `dental_clinic.db` plus the uploads tree."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(db_path, _DB_MEMBER)
        if uploads_dir and os.path.isdir(uploads_dir):
            for root, _dirs, files in os.walk(uploads_dir):
                for name in files:
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, uploads_dir)
                    z.write(full, _UPLOADS_PREFIX + rel.replace(os.sep, '/'))


def _safe_members(z: zipfile.ZipFile, dest_root: str):
    dest_root = os.path.abspath(dest_root)
    for member in z.namelist():
        target = os.path.abspath(os.path.join(dest_root, member))
        if target != dest_root and not target.startswith(dest_root + os.sep):
            raise ValueError(f'unsafe path in archive: {member}')
        yield member


def extract_bundle(zip_path: str, dest_dir: str):
    """Extract a bundle into dest_dir, guarding against zip-slip. Returns
    (db_path, uploads_dir_or_None)."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = list(_safe_members(z, dest_dir))   # validates before extracting
        z.extractall(dest_dir, members=members)
    db_path = os.path.join(dest_dir, _DB_MEMBER)
    if not os.path.exists(db_path):
        # Fall back to the first *.db member.
        dbs = [m for m in members if m.lower().endswith('.db')]
        if not dbs:
            raise ValueError('bundle contains no database file')
        db_path = os.path.join(dest_dir, dbs[0])
    uploads_dir = os.path.join(dest_dir, 'uploads')
    return db_path, (uploads_dir if os.path.isdir(uploads_dir) else None)
