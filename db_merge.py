"""Additive cross-clinic database merge engine.

Pure (no Flask). Opens a source SQLite DB read-only and inserts its records into
a destination connection in foreign-key dependency order, assigning fresh ids
and rewriting every foreign key. Catalog tables dedupe by name. The destination's
existing rows are never updated or deleted — the merge is purely additive.

The caller owns the transaction: run inside one and commit on success / roll back
on exception so a partial merge never lands.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MergeReport:
    tables: dict = field(default_factory=dict)   # table -> {'added': int, 'skipped': int}
    images_copied: int = 0
    images_skipped: int = 0
    warnings: list = field(default_factory=list)

    def add(self, table: str, added: int, skipped: int = 0) -> None:
        entry = self.tables.setdefault(table, {'added': 0, 'skipped': 0})
        entry['added'] += added
        entry['skipped'] += skipped

    def total_added(self) -> int:
        return sum(t['added'] for t in self.tables.values())

    def as_dict(self) -> dict:
        return {
            'tables': self.tables,
            'images_copied': self.images_copied,
            'images_skipped': self.images_skipped,
            'warnings': self.warnings,
            'total_added': self.total_added(),
        }


def _dst_columns(dst_cur, table: str) -> list:
    dst_cur.execute(f'PRAGMA table_info({table})')
    return [r[1] for r in dst_cur.fetchall()]


def _remap_value(old_value, id_map: dict):
    """Translate one foreign-key value through an id map.

    None/0/'' stay null (no link). A value with no entry in the map (orphan)
    becomes None so we never point at a non-existent row."""
    if old_value in (None, 0, ''):
        return None
    return id_map.get(old_value)


def _copy_table(dst_cur, src_cur, table: str, fk_cols: dict, remaps: dict, report: MergeReport) -> dict:
    """Additively copy every row of `table` from source to destination.

    fk_cols maps a column name -> the remap key (an earlier table's id map) to
    rewrite it through. Returns this table's own old_id -> new_id map. Rows that
    raise a per-row SQLite error are counted as skipped without aborting.
    """
    cols = [c for c in _dst_columns(dst_cur, table) if c != 'id']
    src_cur.execute(f'SELECT * FROM {table} ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    id_map = {}
    added = skipped = 0
    for row in rows:
        old_id = row.get('id')
        values = []
        for col in cols:
            val = row.get(col)
            if col in fk_cols:
                val = _remap_value(val, remaps.get(fk_cols[col], {}))
            values.append(val)
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(values),
            )
        except sqlite3.Error as exc:
            skipped += 1
            report.warnings.append(f'{table}: skipped a row ({exc})')
            continue
        if old_id is not None:
            id_map[old_id] = dst_cur.lastrowid
        added += 1
    report.add(table, added, skipped)
    return id_map


def _dedupe_catalog(dst_cur, src_cur, table: str, report: MergeReport, name_col: str = 'name') -> dict:
    """Merge a name-unique catalog. Reuse the destination row when the name
    already exists (keeping the destination's values); otherwise insert as new.
    Returns old_id -> resolved_id."""
    dst_cur.execute(f'SELECT id, {name_col} FROM {table}')
    existing = {str(r[1]).strip().lower(): r[0] for r in dst_cur.fetchall()}
    cols = [c for c in _dst_columns(dst_cur, table) if c != 'id']
    src_cur.execute(f'SELECT * FROM {table} ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    id_map = {}
    added = skipped = 0
    for row in rows:
        old_id = row.get('id')
        key = str(row.get(name_col) or '').strip().lower()
        if not key:
            skipped += 1
            continue
        if key in existing:
            id_map[old_id] = existing[key]
            skipped += 1
            continue
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(row.get(c) for c in cols),
            )
        except sqlite3.Error as exc:
            skipped += 1
            report.warnings.append(f'{table}: skipped a row ({exc})')
            continue
        new_id = dst_cur.lastrowid
        id_map[old_id] = new_id
        existing[key] = new_id
        added += 1
    report.add(table, added, skipped)
    return id_map
