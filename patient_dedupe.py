"""Find and merge duplicate patient records.

Duplicates happen mostly after an additive cross-clinic merge (db_merge.py copies
patients without deduping — correctly, because two real people can share a name).
This module never auto-merges: it only *finds* likely duplicates (same normalized
name) and reports per-patient record counts so a human can pick the survivor and
confirm. ``merge_patients`` then performs the chosen merge.

Pure (no Flask): every function takes a sqlite cursor and the caller owns the
transaction (commit on success / roll back on failure). Sync propagation is
automatic — every reassigned table in SYNC_TABLES has an AFTER UPDATE trigger
that bumps ``updated_at``, and the deleted shell goes out as a ``patients``
tombstone (recorded by the caller).
"""
from __future__ import annotations


def normalize_name(first, last) -> str:
    """Key two patients are considered duplicates by: trim, collapse internal
    whitespace, lowercase. Returns '' when both parts are blank."""
    full = f"{first or ''} {last or ''}"
    return ' '.join(full.split()).lower()


def _patient_id_tables(cursor) -> list[str]:
    """Every table (except patients) that has a patient_id column — the rows that
    must move when patients are merged. Read from the schema so a newly added
    clinical table is handled without editing a hard-coded list. Tables keyed off
    a patient row indirectly (e.g. treatment_plan_teeth via plan_id) follow their
    parent automatically and are intentionally not listed here."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'patients'")
    names = [r[0] for r in cursor.fetchall()]
    out = []
    for t in names:
        cursor.execute(f'PRAGMA table_info("{t}")')
        if any(col[1] == 'patient_id' for col in cursor.fetchall()):
            out.append(t)
    return sorted(out)


def _record_count(cursor, tables, patient_id) -> int:
    """How many rows across all patient-owned tables point at this patient — the
    signal that distinguishes a real record from an empty shell."""
    total = 0
    for t in tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{t}" WHERE patient_id = ?', (patient_id,))
        total += cursor.fetchone()[0]
    return total


def find_duplicate_groups(cursor) -> list[dict]:
    """Groups of patients (2+) that share a normalized name. Each patient carries
    a record_count so the caller can tell the real record from an empty shell.
    Within a group, patients are ordered most-records-first (the suggested
    survivor); groups are ordered alphabetically by name key for stable output."""
    cursor.execute(
        'SELECT id, first_name, last_name, phone, email, date_of_birth FROM patients')
    rows = cursor.fetchall()
    groups: dict[str, list] = {}
    for r in rows:
        key = normalize_name(r[1], r[2])
        if not key:
            continue
        groups.setdefault(key, []).append(r)

    tables = _patient_id_tables(cursor)
    result = []
    for key in sorted(groups):
        members = groups[key]
        if len(members) < 2:
            continue
        patients = []
        for r in members:
            pid = r[0]
            name = f"{(r[1] or '').strip()} {(r[2] or '').strip()}".strip()
            patients.append({
                'id': pid,
                'first_name': r[1],
                'last_name': r[2],
                'name': name,
                'phone': r[3],
                'email': r[4],
                'date_of_birth': r[5],
                'record_count': _record_count(cursor, tables, pid),
            })
        patients.sort(key=lambda p: (-p['record_count'], p['id']))
        result.append({
            'name_key': key,
            'display_name': patients[0]['name'] or key,
            'suggested_survivor_id': patients[0]['id'],
            'patients': patients,
        })
    return result


def merge_patients(cursor, survivor_id, duplicate_ids) -> dict:
    """Fold every duplicate's records into ``survivor_id`` then delete the empty
    duplicate patient rows. Reassigns patient_id across all patient-owned tables;
    rows that reference a patient indirectly follow their parent. The caller owns
    the transaction and is responsible for tombstones, audit log, and balance
    recompute on the survivor.

    Raises ValueError on bad input (no duplicates, survivor listed as its own
    duplicate, or any id missing) so nothing partial lands.

    Returns a summary: survivor_id, merged_ids, per-table moved-row counts, and
    the tables touched.
    """
    survivor_id = int(survivor_id)
    dup_ids = [int(d) for d in duplicate_ids]
    if not dup_ids:
        raise ValueError('no duplicate_ids given')
    if survivor_id in dup_ids:
        raise ValueError('survivor_id cannot also be a duplicate_id')
    if len(set(dup_ids)) != len(dup_ids):
        raise ValueError('duplicate_ids contains repeats')

    for pid in [survivor_id, *dup_ids]:
        cursor.execute('SELECT 1 FROM patients WHERE id = ?', (pid,))
        if cursor.fetchone() is None:
            raise ValueError(f'patient {pid} not found')

    tables = _patient_id_tables(cursor)
    moved: dict[str, int] = {}
    for dup in dup_ids:
        for t in tables:
            cursor.execute(
                f'UPDATE "{t}" SET patient_id = ? WHERE patient_id = ?', (survivor_id, dup))
            if cursor.rowcount and cursor.rowcount > 0:
                moved[t] = moved.get(t, 0) + cursor.rowcount
        cursor.execute('DELETE FROM patients WHERE id = ?', (dup,))

    return {
        'survivor_id': survivor_id,
        'merged_ids': dup_ids,
        'moved': moved,
        'tables': tables,
    }
