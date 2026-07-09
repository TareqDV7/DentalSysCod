"""Staff permission keys and cursor-level permission storage helpers.

Enforcement (which route needs which key, the before_request gate) lives in
dental_clinic.py alongside the other before_request gates — this module only
defines the permission vocabulary and the storage helpers, mirroring
inventory.py / patient_dedupe.py: pure functions taking a cursor, no
connection management of their own.
"""

PERMISSION_KEYS = (
    'patients.view', 'patients.edit',
    'followups.view', 'followups.edit',   # combined clinical + billing fields
                                            # on the follow-up sheet — see plan
                                            # Global Constraints for why this
                                            # isn't split further.
    'appointments.view', 'appointments.edit',
    'billing.view', 'billing.edit',
    'expenses.view', 'expenses.edit',
    'depo.view', 'depo.edit',
    'reports.view',
    'post_studio.use',
    'data_tools.use',
    'settings.manage',
    'staff.manage',
)

_PERMISSION_KEY_SET = frozenset(PERMISSION_KEYS)


def grant_all(cursor, user_id):
    """Grant every known permission key to user_id. Idempotent."""
    for key in PERMISSION_KEYS:
        cursor.execute(
            'INSERT OR REPLACE INTO user_permissions (user_id, permission_key, granted) '
            'VALUES (?, ?, 1)', (user_id, key))


def get_permissions(cursor, user_id):
    """Return the set of permission keys currently granted to user_id."""
    rows = cursor.execute(
        'SELECT permission_key FROM user_permissions WHERE user_id = ? AND granted = 1',
        (user_id,)
    ).fetchall()
    return {row[0] for row in rows}


def set_permission(cursor, user_id, permission_key, granted):
    """Grant or revoke a single permission key for user_id."""
    if permission_key not in _PERMISSION_KEY_SET:
        raise ValueError(f'Unknown permission key: {permission_key}')
    cursor.execute(
        'INSERT OR REPLACE INTO user_permissions (user_id, permission_key, granted) '
        'VALUES (?, ?, ?)', (user_id, permission_key, 1 if granted else 0))


def migrate_default_grants(cursor):
    """One-time-per-user migration: any user with zero permission rows at all
    (i.e. they existed before RBAC, or were inserted directly without going
    through the Manage Staff UI) gets every permission granted. Safe to call
    on every app start — a user who already has at least one permission row
    (even a revoked one) is left alone, so an Owner's deliberate revocation
    is never silently re-granted on the next restart."""
    user_ids = [r[0] for r in cursor.execute('SELECT id FROM users').fetchall()]
    for uid in user_ids:
        has_any = cursor.execute(
            'SELECT 1 FROM user_permissions WHERE user_id = ? LIMIT 1', (uid,)
        ).fetchone()
        if not has_any:
            grant_all(cursor, uid)
