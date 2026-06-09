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
