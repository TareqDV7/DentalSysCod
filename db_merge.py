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


def _unique_dest_name(dst_uploads: str, file_name: str) -> str:
    stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base = os.path.basename(file_name or 'image')
    candidate = os.path.join(dst_uploads, f'merged_{stamp}_{base}')
    n = 0
    while os.path.exists(candidate):
        n += 1
        candidate = os.path.join(dst_uploads, f'merged_{stamp}_{n}_{base}')
    return candidate


def _copy_medical_images(dst_cur, src_cur, remaps: dict, src_uploads, dst_uploads,
                         report: MergeReport) -> None:
    patient_map = remaps.get('patients', {})
    cols = [c for c in _dst_columns(dst_cur, 'medical_images') if c != 'id']
    src_cur.execute('SELECT * FROM medical_images ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    if not rows:
        return
    if not src_uploads or not dst_uploads:
        report.images_skipped += len(rows)
        report.warnings.append(
            f'{len(rows)} medical image(s) skipped — image files were not included '
            f'(import a .zip bundle to carry X-rays).')
        return
    os.makedirs(dst_uploads, exist_ok=True)
    for row in rows:
        new_pid = _remap_value(row.get('patient_id'), patient_map)
        if new_pid is None:
            report.images_skipped += 1
            continue
        # Resolve the source file: stored absolute path, else by file_name in src uploads.
        candidates = []
        if row.get('file_path'):
            candidates.append(row['file_path'])
            candidates.append(os.path.join(src_uploads, os.path.basename(row['file_path'])))
        if row.get('file_name'):
            candidates.append(os.path.join(src_uploads, os.path.basename(row['file_name'])))
        source_file = next((p for p in candidates if p and os.path.exists(p)), None)
        if not source_file:
            report.images_skipped += 1
            report.warnings.append(f"medical image missing on disk: {row.get('file_name')}")
            continue
        dest_file = _unique_dest_name(dst_uploads, row.get('file_name') or os.path.basename(source_file))
        try:
            shutil.copy2(source_file, dest_file)
        except OSError as exc:
            report.images_skipped += 1
            report.warnings.append(f"could not copy image {row.get('file_name')}: {exc}")
            continue
        out = dict(row)
        out['patient_id'] = new_pid
        out['file_path'] = dest_file
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO medical_images ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(out.get(c) for c in cols),
            )
        except sqlite3.Error as exc:
            report.images_skipped += 1
            report.warnings.append(f'medical_images: skipped a row ({exc})')
            continue
        report.images_copied += 1


def _copy_expenses(dst_cur, src_cur, remaps: dict, report: MergeReport) -> dict:
    """Copy expenses, rewriting patient_id and treatment_id via their maps, and
    reference_id via the follow-up map ONLY when source_type == 'followup'
    (otherwise reference_id is unrelated bookkeeping and is preserved)."""
    cols = [c for c in _dst_columns(dst_cur, 'expenses') if c != 'id']
    src_cur.execute('SELECT * FROM expenses ORDER BY id ASC')
    rows = [dict(r) for r in src_cur.fetchall()]
    patient_map = remaps.get('patients', {})
    treatment_map = remaps.get('treatments', {})
    followup_map = remaps.get('patient_followups', {})
    id_map = {}
    added = skipped = 0
    for row in rows:
        old_id = row.get('id')
        out = dict(row)
        if 'patient_id' in cols:
            out['patient_id'] = _remap_value(row.get('patient_id'), patient_map)
        if 'treatment_id' in cols:
            out['treatment_id'] = _remap_value(row.get('treatment_id'), treatment_map)
        if 'reference_id' in cols and str(row.get('source_type') or '') == 'followup':
            out['reference_id'] = _remap_value(row.get('reference_id'), followup_map)
        placeholders = ', '.join('?' for _ in cols)
        try:
            dst_cur.execute(
                f"INSERT INTO expenses ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(out.get(c) for c in cols),
            )
        except sqlite3.Error as exc:
            skipped += 1
            report.warnings.append(f'expenses: skipped a row ({exc})')
            continue
        if old_id is not None:
            id_map[old_id] = dst_cur.lastrowid
        added += 1
    report.add('expenses', added, skipped)
    return id_map


# (table, {fk_column: remap_key}) in foreign-key dependency order.
_GENERIC_ORDER = [
    ('appointments',         {'patient_id': 'patients'}),
    ('visits',               {'patient_id': 'patients', 'appointment_id': 'appointments'}),
    ('treatments',           {'patient_id': 'patients', 'appointment_id': 'appointments'}),
    ('treatment_plans',      {'patient_id': 'patients'}),
    ('treatment_plan_teeth', {'plan_id': 'treatment_plans'}),
    ('patient_followups',    {'patient_id': 'patients', 'procedure_id': 'treatment_procedures'}),
    ('billing',              {'patient_id': 'patients', 'treatment_id': 'treatments'}),
]


def merge_database(dst_conn, src_db_path, *, src_uploads=None, dst_uploads=None,
                   include_images=True, include_credit=True) -> MergeReport:
    """Additively merge the SQLite DB at src_db_path into dst_conn. Caller commits."""
    report = MergeReport()
    src_conn = sqlite3.connect(f'file:{src_db_path}?mode=ro', uri=True)
    src_conn.row_factory = sqlite3.Row
    try:
        dst_cur = dst_conn.cursor()
        src_cur = src_conn.cursor()
        remaps = {}
        # Catalogs first (deduped by name) so followups/tooth-chart can remap to them.
        remaps['treatment_procedures'] = _dedupe_catalog(dst_cur, src_cur, 'treatment_procedures', report)
        remaps['tooth_conditions'] = _dedupe_catalog(dst_cur, src_cur, 'tooth_conditions', report)
        # Patients next, then everything that hangs off them.
        remaps['patients'] = _copy_table(dst_cur, src_cur, 'patients', {}, remaps, report)
        for table, fk_cols in _GENERIC_ORDER:
            remaps[table] = _copy_table(dst_cur, src_cur, table, fk_cols, remaps, report)
        _copy_expenses(dst_cur, src_cur, remaps, report)
        remaps['patient_tooth_chart'] = _copy_table(
            dst_cur, src_cur, 'patient_tooth_chart',
            {'patient_id': 'patients', 'condition_id': 'tooth_conditions'}, remaps, report)
        if include_images:
            _copy_medical_images(dst_cur, src_cur, remaps, src_uploads, dst_uploads, report)
        if include_credit:
            _copy_table(dst_cur, src_cur, 'patient_credit_transactions',
                        {'patient_id': 'patients', 'invoice_id': 'billing'}, remaps, report)
        # Recompute running balances for every imported patient.
        for new_pid in remaps['patients'].values():
            try:
                _recompute_balances(dst_cur, new_pid)
            except sqlite3.Error:
                pass
    finally:
        src_conn.close()
    return report


def _recompute_balances(dst_cur, patient_id):
    """Defer to dental_clinic's ledger recompute. Imported here lazily to keep
    db_merge import-light and avoid a circular import at module load."""
    import dental_clinic
    dental_clinic._recompute_followup_balances(dst_cur, patient_id)


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
