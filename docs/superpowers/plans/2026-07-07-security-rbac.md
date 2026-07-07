# Security PR 2: Staff RBAC (Custom Permission Matrix) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single shared `admin` login with real staff accounts, each with an individually configurable set of permissions, enforced on the desktop portal only (mobile keeps its device-pairing model unchanged).

**Architecture:** The `users` table already exists and already supports multiple accounts (`username`/`password_hash`/`display_name`/`is_active`) — it was just never given a UI to add a second user. This PR adds a `user_permissions` table, a pure-logic `permissions.py` module (mirrors `inventory.py`/`patient_dedupe.py` — cursor-level functions, no connection management), a `before_request` permission gate that mirrors the existing `_AUTH_REQUIRED_EXACT`/`_AUTH_REQUIRED_PREFIXES` pattern (so it only restricts session-authenticated desktop requests — mobile's device/clinic-token requests never touch this new gate), a Settings → "Manage Staff" UI, and an actor field on `audit_logs`.

**Tech Stack:** Flask, SQLite, no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-07-security-hardening-rbac-design.md`, Decisions 3-4 + Architecture › RBAC.
- **Refinement over the spec's permission-key list**, decided during planning (session Q&A 2026-07-07): the follow-up sheet mixes clinical and billing fields in one endpoint, so it gets **one combined permission** (`followups.view`/`followups.edit`) rather than being split across `clinical.*`/`billing.*` — no field-level redaction in this PR. The full key list below supersedes the shorter illustrative list in the spec.
- **RBAC only restricts session-authenticated (desktop) requests.** Any request carrying `X-Device-Token` or `X-Clinic-Token` (the mobile app's existing auth) bypasses the permission gate entirely — this is not a regression, it's the existing, intentional posture for the offline-first mobile app (see `_require_login_for_portal`'s own carve-outs for the same headers).
- Routes already open today with no login requirement at all (license/cloud/sync/pairing/BT/onboarding endpoints, per the comment above `_AUTH_REQUIRED_EXACT`) are **not** touched by this PR — adding permission checks to them is out of scope; they stay exactly as open as they are today.
- New user creation reuses the existing `hash_password()` (`dental_clinic.py:89`) — do not add a second password-hashing path.
- Full existing test suite (742+ tests as of 2026-07-07) must stay green throughout.

---

### Task 1: `user_permissions` table + `permissions.py` module + migration

**Files:**
- Create: `permissions.py`
- Modify: `dental_clinic.py` — add `CREATE TABLE` inside `init_database()` (alongside the other `CREATE TABLE IF NOT EXISTS` statements, right after the `users` table at line 1086), plus a migration call at the end of `init_database()`.
- Test: `tests/test_permissions.py` (new)

**Interfaces:**
- Produces: `permissions.PERMISSION_KEYS` (tuple of strings), `permissions.grant_all(cursor, user_id)`, `permissions.get_permissions(cursor, user_id) -> set[str]`, `permissions.set_permission(cursor, user_id, key, granted)`, `permissions.migrate_default_grants(cursor)`.
- Consumed by: Task 2 (audit log), Task 3 (enforcement gate), Task 4 (staff endpoints), Task 5/6 (frontend, via the endpoints from Task 4).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_permissions.py`:

```python
"""Staff permission storage and the auto-grant-all migration for pre-existing
users (the single 'admin' account that predates RBAC)."""
import sqlite3

import pytest

import dental_clinic
import permissions


@pytest.fixture()
def db(tmp_path, monkeypatch):
    test_db = tmp_path / 'perm_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    return str(test_db)


def test_existing_admin_auto_granted_all_permissions(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    granted = permissions.get_permissions(cur, uid)
    conn.close()
    assert granted == set(permissions.PERMISSION_KEYS)


def test_set_permission_revokes_and_grants(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    permissions.set_permission(cur, uid, 'billing.edit', False)
    conn.commit()
    granted = permissions.get_permissions(cur, uid)
    assert 'billing.edit' not in granted
    permissions.set_permission(cur, uid, 'billing.edit', True)
    conn.commit()
    granted = permissions.get_permissions(cur, uid)
    assert 'billing.edit' in granted
    conn.close()


def test_set_permission_rejects_unknown_key(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    with pytest.raises(ValueError):
        permissions.set_permission(cur, uid, 'not.a.real.key', True)
    conn.close()


def test_migration_does_not_regrant_after_explicit_revoke(db):
    # Re-running the migration (as happens on every init_database() call, e.g.
    # every app start) must not silently re-grant a permission an Owner
    # deliberately revoked from themselves or another account.
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    uid = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    permissions.set_permission(cur, uid, 'data_tools.use', False)
    conn.commit()
    conn.close()

    dental_clinic.init_database()  # re-run migration

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    granted = permissions.get_permissions(cur, uid)
    conn.close()
    assert 'data_tools.use' not in granted


def test_new_user_with_no_permission_rows_gets_none_by_default(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
        ('frontdesk', dental_clinic.hash_password('x'), 'Front Desk'))
    new_uid = cur.lastrowid
    conn.commit()
    # A brand-new user (created after the app already exists) must NOT be
    # auto-granted anything — only the pre-existing migrated admin gets
    # grant-all. New accounts start with zero permissions until an Owner
    # explicitly grants some via the Manage Staff UI (Task 4/5).
    granted = permissions.get_permissions(cur, new_uid)
    conn.close()
    assert granted == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'permissions'`.

- [ ] **Step 3: Create `permissions.py`**

```python
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
```

- [ ] **Step 4: Add the `user_permissions` table and migration call in `dental_clinic.py`**

In `dental_clinic.py`, immediately after the `users` table's `CREATE TABLE IF NOT EXISTS` block (ends at line 1086), add:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id INTEGER NOT NULL,
            permission_key TEXT NOT NULL,
            granted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, permission_key),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
```

Then find where `init_database()` seeds the admin user (the `INSERT INTO users` call — `dental_clinic.py:1426`) and locate the end of `init_database()`. Add near the end of the function, after `conn.commit()` is normally called by the caller but before the function returns (check the exact end of `init_database()` — it should commit before returning; add the migration call right before that final commit so it's part of the same transaction):

```python
    import permissions as _permissions
    _permissions.migrate_default_grants(cursor)
```

(Import inside the function, not top-level, to avoid a circular-import risk if `permissions.py` ever needs anything from `dental_clinic` later — matches the lazy-import style already used elsewhere in this file, e.g. `from window.data_dir import resolve_data_dir` is top-level but several feature modules are imported lazily near their point of use.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: PASS, 5/5.

- [ ] **Step 6: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: green, no regressions (the new table/migration only adds rows, never removes or alters existing behavior).

- [ ] **Step 7: Commit**

```bash
git add permissions.py dental_clinic.py tests/test_permissions.py
git commit -m "feat(security): add user_permissions table + permission storage helpers

New permissions.py module (mirrors inventory.py's cursor-level pure-logic
style) plus a migration that auto-grants every permission to any user with
zero permission rows — covers the pre-existing single admin account without
disrupting it. Part 1 of the RBAC sub-project."
```

---

### Task 2: Audit log actor field

**Files:**
- Modify: `dental_clinic.py` — `audit_logs` table (line 1057), `append_audit_log` (line 1440)
- Test: `tests/test_permissions.py` (extend) or a new small block in an existing audit-log test file if one exists — check first with `grep -rl append_audit_log tests/` and extend the most relevant existing test file instead of creating a new one if a natural home exists.

**Interfaces:**
- Consumes: `flask.session` (already imported at module level in `dental_clinic.py`).
- Produces: `audit_logs.actor_user_id`, `audit_logs.actor_username` columns, populated automatically by `append_audit_log` — no call-site changes needed anywhere in the codebase.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_permissions.py`:

```python
def test_audit_log_captures_actor_from_session(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['uid'] = 1
            sess['uname'] = 'admin'
        # Any authenticated write that calls append_audit_log — holidays is
        # the smallest such endpoint (no dependencies on other fixtures).
        client.post('/api/holidays', json={'holiday_date': '2026-12-25', 'name': 'Test'})

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT actor_user_id, actor_username FROM audit_logs WHERE entity_type = 'holiday' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row['actor_user_id'] == 1
    assert row['actor_username'] == 'admin'
```

(If `/api/holidays` doesn't call `append_audit_log` with `entity_type='holiday'`, check the actual entity_type string used at that call site with `grep -n "append_audit_log.*holiday" dental_clinic.py` and adjust the test's `WHERE entity_type = '...'` to match exactly — do not guess.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_permissions.py::test_audit_log_captures_actor_from_session -v`
Expected: FAIL — `sqlite3.OperationalError: no such column: actor_user_id`.

- [ ] **Step 3: Add the columns and update `append_audit_log`**

In `dental_clinic.py`, update the `audit_logs` table (line 1057):

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            actor_user_id INTEGER,
            actor_username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
```

Existing installed clinics already have an `audit_logs` table without these columns — `CREATE TABLE IF NOT EXISTS` won't add them to an existing table. Add an `ALTER TABLE` migration right after this block, guarded so it only runs once:

```python
    cursor.execute("PRAGMA table_info(audit_logs)")
    _audit_cols = {row[1] for row in cursor.fetchall()}
    if 'actor_user_id' not in _audit_cols:
        cursor.execute('ALTER TABLE audit_logs ADD COLUMN actor_user_id INTEGER')
    if 'actor_username' not in _audit_cols:
        cursor.execute('ALTER TABLE audit_logs ADD COLUMN actor_username TEXT')
```

Update `append_audit_log` (line 1440):

```python
def append_audit_log(cursor, action_type, entity_type, entity_id=None, details=None):
    details_text = ''
    if details is not None:
        if isinstance(details, str):
            details_text = details
        else:
            details_text = json.dumps(details, ensure_ascii=False)
    # Best-effort actor capture — reads the current request's session if one
    # exists. Falls back to (None, None) outside a request context (e.g. a
    # background sync/migration call) rather than raising, since audit
    # logging must never be the reason a write fails.
    actor_user_id = None
    actor_username = None
    try:
        actor_user_id = session.get('uid')
        actor_username = session.get('uname')
    except RuntimeError:
        pass  # outside an active Flask request/app context
    cursor.execute('''
        INSERT INTO audit_logs (action_type, entity_type, entity_id, details,
                                 actor_user_id, actor_username)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(action_type or ''), str(entity_type or ''), entity_id, details_text,
          actor_user_id, actor_username))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: green — `ALTER TABLE ADD COLUMN` is additive and `append_audit_log`'s new parameters both have safe defaults, so every existing call site keeps working unchanged.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_permissions.py
git commit -m "feat(security): audit log captures the acting staff member

audit_logs gains actor_user_id/actor_username, populated automatically by
append_audit_log from the current session — no call-site changes needed.
Part 2 of the RBAC sub-project."
```

---

### Task 3: Permission enforcement gate

**Files:**
- Modify: `dental_clinic.py` — add a new `before_request` hook near the existing ones (after `_require_login_for_portal`, `dental_clinic.py:2117-2144`)
- Test: `tests/test_permissions.py` (extend)

**Interfaces:**
- Consumes: `permissions.get_permissions(cursor, user_id)` from Task 1.
- Produces: `_PERMISSION_RULES` (ordered tuple of `(methods_or_None, path_or_prefix, is_prefix, permission_key)`), `_permission_required_for(method, path) -> str | None`, the `_enforce_staff_permission` before_request function. No other task depends on internals beyond the fact that a 403 with `{'error': ..., 'reason': 'permission_denied'}` is returned for a denied request.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_permissions.py`:

```python
def test_session_user_without_permission_gets_403(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
        ('frontdesk', dental_clinic.hash_password('x'), 'Front Desk'))
    uid = cur.lastrowid
    conn.commit()
    conn.close()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['uid'] = uid
            sess['uname'] = 'frontdesk'
        r = client.post('/api/expenses', json={
            'category': 'Test', 'amount': 10, 'expense_date': '01/01/2026',
            'payment_status': 'paid'})
    assert r.status_code == 403
    assert r.get_json()['reason'] == 'permission_denied'


def test_session_user_with_permission_succeeds(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
        ('frontdesk', dental_clinic.hash_password('x'), 'Front Desk'))
    uid = cur.lastrowid
    permissions.set_permission(cur, uid, 'expenses.edit', True)
    conn.commit()
    conn.close()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['uid'] = uid
            sess['uname'] = 'frontdesk'
        r = client.post('/api/expenses', json={
            'category': 'Test', 'amount': 10, 'expense_date': '01/01/2026',
            'payment_status': 'paid'})
    assert r.status_code == 200


def test_device_token_request_bypasses_permission_gate(db):
    # Mobile's device-token path must be completely unaffected by RBAC — it
    # never carries a session, so the gate must not apply to it at all.
    app = dental_clinic.app
    app.config['TESTING'] = True
    with app.test_client() as client:
        r = client.get('/api/patients', headers={'X-Device-Token': 'irrelevant-in-this-test'})
    # No session at all and no permission gate applied — falls through to
    # whatever the route's own logic does (200, or 401 from device-token
    # validation elsewhere — NOT 403 permission_denied).
    assert r.status_code != 403 or r.get_json().get('reason') != 'permission_denied'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_permissions.py -k session_user -v`
Expected: FAIL — the "without permission" test gets 200 (nothing blocks it yet, so it fails the 403 assertion), the "with permission" test also currently 200 so it already passes by coincidence but the first must fail first.

- [ ] **Step 3: Add the permission-rule table and gate in `dental_clinic.py`**

Add near the existing `_AUTH_REQUIRED_EXACT`/`_AUTH_REQUIRED_PREFIXES` definitions (after line 2099), and add `import permissions` to the top-level imports of `dental_clinic.py` (alongside the other local module imports like `import inventory`, `import patient_dedupe` — check `grep -n "^import inventory\|^import patient_dedupe" dental_clinic.py` for the exact existing import block and add `import permissions` there):

```python
# Route -> required-permission mapping for session-authenticated (desktop)
# requests only. Checked in order; first prefix match wins. A route not
# listed here requires no specific permission (only login, if it's already
# in _AUTH_REQUIRED_EXACT/_AUTH_REQUIRED_PREFIXES) — this only ever ADDS
# restriction on top of today's behavior, never removes it. Mobile/device
# and clinic-token requests never reach this gate at all (see
# _enforce_staff_permission below) — RBAC is desktop-portal-only per the
# design spec.
_PERMISSION_RULES = (
    # (methods: frozenset or None-for-any, path_prefix, permission_key)
    (frozenset({'POST'}), '/api/patients', 'patients.edit'),
    (frozenset({'PUT', 'DELETE'}), '/api/patients/', 'patients.edit'),
    (frozenset({'GET'}), '/api/patients', 'patients.view'),

    (frozenset({'GET'}), '/api/patients/', 'followups.view'),  # full-profile, credit, invoice-summary, payment-history, followups GET, tooth-chart GET — narrowed below where a more specific rule is needed
    (frozenset({'POST', 'PUT', 'DELETE'}), '/api/patients/', 'followups.edit'),  # followups/tooth-chart writes nested under /api/patients/<id>/...

    (None, '/api/appointments', None),  # placeholder row overwritten below — see Step 3b
)
```

**Step 3b — this mapping needs to be exact, not approximate.** The `/api/patients/` prefix is shared by several genuinely different sub-resources (`/api/patients/<id>` itself, `/api/patients/<id>/followups`, `/api/patients/<id>/tooth-chart`, `/api/patients/<id>/credit`, `/api/patients/<id>/invoice-summary`, `/api/patients/<id>/payment-history`, `/api/patients/<id>/full-profile`) — a single prefix rule can't distinguish them correctly. Replace the whole block above with a rule table ordered **most-specific-prefix-first**, and a real `_permission_required_for` function that does first-match-wins over exact regex-free substring checks:

```python
_PERMISSION_RULES = (
    # (method_set_or_None, path_regex, permission_key) — order matters, first match wins.
    # Money/financial sub-resources on a patient (checked before the generic
    # patient rules below, since they're more specific paths).
    (None, r'^/api/patients/\d+/(credit|invoice-summary|payment-history)$', 'billing.view'),
    # Follow-up sheet, tooth-chart, medical-images: combined clinical+billing
    # permission (see Global Constraints — no field-level split in this PR).
    (frozenset({'GET'}), r'^/api/patients/\d+/(followups|tooth-chart)(/.*)?$', 'followups.view'),
    (frozenset({'POST', 'PUT', 'DELETE'}), r'^/api/patients/\d+/(followups|tooth-chart)(/.*)?$', 'followups.edit'),
    (frozenset({'GET'}), r'^/api/medical-images(/.*)?$', 'followups.view'),
    (frozenset({'POST'}), r'^/api/medical-images$', 'followups.edit'),
    # Full-profile is a read-only aggregate — gated on the base view permission.
    (frozenset({'GET'}), r'^/api/patients/\d+/full-profile$', 'patients.view'),
    # Generic patient demographics.
    (frozenset({'POST'}), r'^/api/patients$', 'patients.edit'),
    (frozenset({'PUT', 'DELETE'}), r'^/api/patients/\d+$', 'patients.edit'),
    (frozenset({'GET'}), r'^/api/patients(/check-duplicate)?$', 'patients.view'),

    # Treatment plans — clinical, bucketed with follow-ups.
    (frozenset({'GET'}), r'^/api/treatment-plans$', 'followups.view'),
    (frozenset({'POST', 'PUT', 'DELETE'}), r'^/api/treatment-plans(/.*)?$', 'followups.edit'),

    # Appointments / visits / holidays (scheduling).
    (frozenset({'GET'}), r'^/api/(appointments|visits)(/.*)?$', 'appointments.view'),
    (frozenset({'POST', 'PUT', 'DELETE'}), r'^/api/(appointments|visits)(/.*)?$', 'appointments.edit'),
    (frozenset({'GET'}), r'^/api/holidays$', 'appointments.view'),
    (frozenset({'POST', 'DELETE'}), r'^/api/holidays(/.*)?$', 'appointments.edit'),

    # Billing.
    (frozenset({'GET'}), r'^/api/billing(/.*)?$', 'billing.view'),
    (frozenset({'POST', 'DELETE'}), r'^/api/billing(/.*)?$', 'billing.edit'),
    (frozenset({'GET'}), r'^/invoice/\d+$', 'billing.view'),
    (frozenset({'GET'}), r'^/api/reports/receivables$', 'billing.view'),

    # Expenses.
    (frozenset({'GET'}), r'^/api/expenses$', 'expenses.view'),
    (frozenset({'POST', 'PUT', 'DELETE'}), r'^/api/expenses(/.*)?$', 'expenses.edit'),

    # Depo / inventory.
    (frozenset({'GET'}), r'^/api/inventory(/.*)?$', 'depo.view'),
    (frozenset({'POST', 'PUT', 'DELETE'}), r'^/api/inventory/(items|procedures)(/.*)?$', 'depo.edit'),

    # Reports (revenue/weekly summaries — distinct from receivables above).
    (frozenset({'GET'}), r'^/api/reports/(summary|weekly)$', 'reports.view'),

    # Post Studio: creating/deleting posts requires the permission; viewing
    # (GET) stays open, matching the existing mobile-compat carve-out in
    # _require_login_for_portal for the same paths.
    (frozenset({'POST', 'DELETE'}), r'^/api/posts(/.*)?$', 'post_studio.use'),

    # Data tools — dangerous, off by default for anyone but Owner.
    (None, r'^/api/data/(export-bundle|export-bundle-file|merge|replace|clear-catalogs|'
           r'duplicate-patients|merge-patients|import-patients/preview|import-patients/commit)$',
           'data_tools.use'),
    (None, r'^/api/backup(-file)?$', 'data_tools.use'),

    # Catalog editing (procedures/tooth-conditions) and clinic-wide settings.
    (frozenset({'POST', 'PUT', 'DELETE'}), r'^/api/(treatment-procedures|tooth-conditions)(/.*)?$', 'settings.manage'),
    (frozenset({'PUT'}), r'^/api/branding$', 'settings.manage'),
    (frozenset({'POST'}), r'^/api/clinic-settings$', 'settings.manage'),
    (frozenset({'POST'}), r'^/api/bt/configure$', 'settings.manage'),
    (frozenset({'GET'}), r'^/api/audit-logs$', 'settings.manage'),

    # Staff management itself (added in Task 4) — gated on staff.manage.
    (None, r'^/api/staff(/.*)?$', 'staff.manage'),
)

_PERMISSION_RULE_CACHE = tuple((methods, re.compile(pattern), key) for methods, pattern, key in _PERMISSION_RULES)
# (dental_clinic.py already imports `re` at module level — no new import needed.)


def _permission_required_for(method, path):
    for methods, compiled, key in _PERMISSION_RULE_CACHE:
        if methods is not None and method not in methods:
            continue
        if compiled.match(path):
            return key
    return None


@app.before_request
def _enforce_staff_permission():
    if request.method == 'OPTIONS':
        return None
    # Mobile/device requests are never subject to desktop RBAC.
    if request.headers.get('X-Device-Token') or request.headers.get('X-Clinic-Token'):
        return None
    uid = session.get('uid')
    if not uid:
        return None  # not a desktop session at all — unrelated to this gate
    path = request.path or '/'
    required = _permission_required_for(request.method, path)
    if required is None:
        return None
    conn = get_db_connection()
    try:
        granted = permissions.get_permissions(conn.cursor(), uid)
    finally:
        conn.close()
    if required not in granted:
        return jsonify({'error': 'You do not have permission to do that.',
                        'reason': 'permission_denied'}), 403
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: PASS, all tests including the 3 new ones from this task.

- [ ] **Step 5: Run full suite — this is the highest-risk step in the RBAC sub-project**

Run: `python -m pytest tests/ -q`
Expected: green. If anything fails, it almost certainly means an existing test logs in via `session_transaction()` (as `uid=1`, the seeded admin) and then calls a route now covered by `_PERMISSION_RULES` — since the seeded admin has every permission granted (Task 1's migration), this should not happen, but if a test creates its own separate user without going through the normal seed path, check that test's fixture and grant it what it needs via `permissions.grant_all(cur, uid)`, don't weaken the gate to make it pass.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_permissions.py
git commit -m "feat(security): enforce staff permissions on desktop portal requests

New before_request gate checks a route/method -> permission-key mapping for
session-authenticated requests only; mobile's device/clinic-token requests
are untouched. Part 3 of the RBAC sub-project."
```

---

### Task 4: Staff management endpoints

**Files:**
- Modify: `dental_clinic.py` — add new routes near the existing `/api/auth/*` routes (after line 2345, `auth_me`)
- Test: `tests/test_permissions.py` (extend)

**Interfaces:**
- Produces: `GET /api/staff` (list), `POST /api/staff` (create), `PUT /api/staff/<id>` (deactivate/reactivate + display name), `GET /api/staff/<id>/permissions`, `PUT /api/staff/<id>/permissions` (set one or more keys) — all gated by `staff.manage` via Task 3's `_PERMISSION_RULES` (already covers `^/api/staff(/.*)?$`).
- Consumes: `permissions.PERMISSION_KEYS`, `permissions.get_permissions`, `permissions.set_permission`, `hash_password` (already in `dental_clinic.py`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_permissions.py`:

```python
def _owner_client(app, uid=1, uname='admin'):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = uname
    return client


def test_list_staff_returns_seeded_admin(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    r = client.get('/api/staff')
    assert r.status_code == 200
    usernames = [u['username'] for u in r.get_json()]
    assert 'admin' in usernames


def test_create_staff_account_with_selected_permissions(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    r = client.post('/api/staff', json={
        'username': 'frontdesk', 'password': 'x', 'display_name': 'Front Desk',
        'permissions': ['appointments.view', 'appointments.edit', 'patients.view']})
    assert r.status_code == 200, r.get_data(as_text=True)
    new_id = r.get_json()['id']

    r2 = client.get(f'/api/staff/{new_id}/permissions')
    granted = set(r2.get_json()['granted'])
    assert granted == {'appointments.view', 'appointments.edit', 'patients.view'}


def test_create_staff_rejects_duplicate_username(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    client.post('/api/staff', json={'username': 'dup', 'password': 'x', 'permissions': []})
    r = client.post('/api/staff', json={'username': 'dup', 'password': 'x', 'permissions': []})
    assert r.status_code == 400


def test_deactivate_last_staff_manage_account_is_blocked(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    # admin (uid=1) is the ONLY account with staff.manage — deactivating it
    # would lock the clinic out of staff management entirely.
    r = client.put('/api/staff/1', json={'is_active': False})
    assert r.status_code == 400
    assert 'last' in r.get_json()['error'].lower()


def test_deactivate_staff_account_succeeds_when_another_owner_exists(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    r = client.post('/api/staff', json={
        'username': 'owner2', 'password': 'x', 'permissions': list(permissions.PERMISSION_KEYS)})
    second_owner_id = r.get_json()['id']
    r2 = client.put(f'/api/staff/{second_owner_id}', json={'is_active': False})
    assert r2.status_code == 200


def test_revoke_permission_from_self_when_another_owner_exists(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    client.post('/api/staff', json={
        'username': 'owner2', 'password': 'x', 'permissions': list(permissions.PERMISSION_KEYS)})
    r = client.put('/api/staff/1/permissions', json={'permission_key': 'staff.manage', 'granted': False})
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_permissions.py -k staff -v`
Expected: FAIL — `404 Not Found` for every new route (they don't exist yet).

- [ ] **Step 3: Add the routes**

Add to `dental_clinic.py` after `auth_me` (line 2345):

```python
def _count_users_with_permission(cursor, permission_key, exclude_user_id=None):
    rows = cursor.execute(
        'SELECT user_id FROM user_permissions WHERE permission_key = ? AND granted = 1',
        (permission_key,)
    ).fetchall()
    ids = {r[0] for r in rows}
    if exclude_user_id is not None:
        ids.discard(exclude_user_id)
    if not ids:
        return 0
    placeholders = ','.join('?' * len(ids))
    active = cursor.execute(
        f'SELECT COUNT(*) FROM users WHERE id IN ({placeholders}) AND is_active = 1',
        tuple(ids)
    ).fetchone()[0]
    return active


@app.route('/api/staff', methods=['GET', 'POST'])
def staff_accounts():
    conn = get_db_connection(with_row_factory=True)
    cursor = conn.cursor()
    if request.method == 'GET':
        rows = cursor.execute(
            'SELECT id, username, display_name, is_active, created_at, last_login_at FROM users '
            'ORDER BY username'
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        conn.close()
        return jsonify({'error': 'Username and password are required'}), 400
    existing = cursor.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'That username is already in use'}), 400
    cursor.execute(
        'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)',
        (username, hash_password(password), data.get('display_name') or username))
    new_id = cursor.lastrowid
    requested_perms = data.get('permissions') or []
    for key in requested_perms:
        permissions.set_permission(cursor, new_id, key, True)
    append_audit_log(cursor, 'create', 'staff_account', new_id, {'username': username})
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/staff/<int:user_id>', methods=['PUT'])
def staff_account_update(user_id):
    data = request.json or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'is_active' in data and not data['is_active']:
        # Refuse to deactivate the last active account holding staff.manage —
        # that would lock the clinic out of Manage Staff entirely.
        cursor.execute('SELECT 1 FROM user_permissions WHERE user_id = ? AND permission_key = ? AND granted = 1',
                        (user_id, 'staff.manage'))
        if cursor.fetchone():
            remaining = _count_users_with_permission(cursor, 'staff.manage', exclude_user_id=user_id)
            if remaining == 0:
                conn.close()
                return jsonify({'error': 'Cannot deactivate the last account with staff management access'}), 400
    sets, vals = [], []
    if 'is_active' in data:
        sets.append('is_active = ?'); vals.append(1 if data['is_active'] else 0)
    if 'display_name' in data:
        sets.append('display_name = ?'); vals.append(data['display_name'])
    if not sets:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    vals.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
    append_audit_log(cursor, 'update', 'staff_account', user_id, data)
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/staff/<int:user_id>/permissions', methods=['GET', 'PUT'])
def staff_permissions(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'GET':
        granted = sorted(permissions.get_permissions(cursor, user_id))
        conn.close()
        return jsonify({'user_id': user_id, 'granted': granted, 'all_keys': list(permissions.PERMISSION_KEYS)})

    data = request.json or {}
    key = data.get('permission_key')
    granted_flag = bool(data.get('granted'))
    if not granted_flag and key == 'staff.manage':
        remaining = _count_users_with_permission(cursor, 'staff.manage', exclude_user_id=user_id)
        if remaining == 0:
            conn.close()
            return jsonify({'error': 'Cannot revoke the last account with staff management access'}), 400
    try:
        permissions.set_permission(cursor, user_id, key, granted_flag)
    except ValueError as exc:
        conn.close()
        return jsonify({'error': str(exc)}), 400
    append_audit_log(cursor, 'update', 'staff_permission', user_id, {'key': key, 'granted': granted_flag})
    conn.commit()
    conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: PASS, full file green.

- [ ] **Step 5: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_permissions.py
git commit -m "feat(security): staff account CRUD + per-account permission endpoints

GET/POST /api/staff, PUT /api/staff/<id>, GET/PUT /api/staff/<id>/permissions
— all gated on staff.manage. Guards against deactivating or revoking the
last remaining staff.manage-holder, which would lock the clinic out of its
own staff management. Part 4 of the RBAC sub-project."
```

---

### Task 5: "Manage Staff" Settings UI

**Files:**
- Modify: `templates.py` — Settings tab (`#support` tab-content, starts around line 3010) and its EN/AR i18n maps
- Test: this is UI wiring over already-tested endpoints (Task 4); verify with `node --check` on the extracted inline scripts (same technique used earlier this session) rather than new Python tests — there is no existing Playwright coverage that can run in this environment (documented open item), so this task's verification step says so explicitly rather than skipping it silently.

**Interfaces:**
- Consumes: `GET/POST /api/staff`, `PUT /api/staff/<id>`, `GET/PUT /api/staff/<id>/permissions` (Task 4).

- [ ] **Step 1: Locate the exact insertion point**

Run: `python -c "import re; d=open('templates.py',encoding='utf-8').read(); i=d.index('<h3 class=\"settings-group\" data-i18n=\"account\">'); print(d[i-200:i+400])"`

Confirm the `#support` tab's structure (section-card blocks per settings group) before writing the new panel, so the new block matches existing markup exactly (same `<h3 class="settings-group">` / `<div class="section-card">` pattern already used for Account/Sync/Data/Help groups per this session's earlier exploration).

- [ ] **Step 2: Add the "Manage Staff" settings group**

Add a new `<h3 class="settings-group" data-i18n="manage_staff">Manage Staff</h3>` block immediately after the Account group's closing `</div>`, following the exact same `section-card` wrapper pattern as the Account group. Content:
- A table listing staff (`username`, `display_name`, active/inactive badge, last login) fed by `GET /api/staff`.
- An "Add Staff" button opening a small form (username, password, display name, and a permission checkbox grid built from `permissions.PERMISSION_KEYS` — fetch the key list from `GET /api/staff/<any-id>/permissions`'s `all_keys` field, or add a tiny `GET /api/permissions/keys` endpoint if that's cleaner; prefer reusing `all_keys` from the existing endpoint to avoid adding a fourth new route for this).
- Per-row "Edit permissions" opening the same checkbox grid pre-filled from `GET /api/staff/<id>/permissions`, saving via `PUT /api/staff/<id>/permissions` once per changed checkbox (simplest correct approach — no batch-update endpoint needed for a small permission set).
- Per-row deactivate/reactivate toggle calling `PUT /api/staff/<id>` with `{is_active: ...}`.
- Add `data-i18n` keys for every new label to both the EN (`~line 3690` region) and AR (`~line 4190` region) translation maps, following the exact pattern used earlier this session for `expenses_tab`.

- [ ] **Step 3: Syntax-check the extracted inline scripts**

Run the same extraction technique used earlier this session:
```bash
python -c "
import re, sys
sys.path.insert(0, '.')
import templates
html = templates.HTML_TEMPLATE
scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
with open('scratch_ps_check.js', 'w', encoding='utf-8') as f:
    f.write('\n;\n'.join(scripts))
"
node --check scratch_ps_check.js && echo SYNTAX_OK
rm scratch_ps_check.js
```
Expected: `SYNTAX_OK`.

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: green (no Python behavior changed in this task, only `templates.py` markup/JS).

- [ ] **Step 5: Commit**

```bash
git add templates.py
git commit -m "feat(security): Manage Staff settings panel

Add/list/deactivate staff accounts and per-account permission checkboxes,
wired to the Task 4 endpoints. Part 5 of the RBAC sub-project.

Known gap: no automated UI test ran against a live browser in this
environment (Playwright's Chrome install fails here, no admin rights) —
verified via node --check on the extracted inline scripts + manual review
against the existing Settings tab markup pattern. Flagging for a live
click-test before this ships to an installed clinic."
```

---

### Task 6: Permission-aware navigation (hide what the logged-in staff can't use)

**Files:**
- Modify: `templates.py` — the post-login bootstrap JS (wherever `/api/auth/me` or equivalent is called on page load; check `grep -n "auth/me" templates.py` for the exact call site) and the nav-tab markup added/modified across this session (`#main-nav` block).
- Test: same `node --check` verification as Task 5 — no Python changes in this task.

**Interfaces:**
- Consumes: `GET /api/staff/<uid>/permissions` — but the logged-in user doesn't know their own `uid` from the frontend without a lookup; extend `GET /api/auth/me` (`dental_clinic.py:2343-2345`) to also return the caller's granted permission keys, so the frontend gets everything it needs from the one call it already makes on load.

- [ ] **Step 1: Extend `/api/auth/me` to include permissions**

Modify `dental_clinic.py:2343-2345`:

```python
@app.route('/api/auth/me')
def auth_me():
    uid = session.get('uid')
    granted = []
    if uid:
        conn = get_db_connection()
        granted = sorted(permissions.get_permissions(conn.cursor(), uid))
        conn.close()
    return jsonify({'authenticated': bool(uid), 'username': session.get('uname', ''),
                    'permissions': granted})
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_permissions.py`:

```python
def test_auth_me_includes_permissions(db):
    app = dental_clinic.app
    app.config['TESTING'] = True
    client = _owner_client(app)
    r = client.get('/api/auth/me')
    body = r.get_json()
    assert set(body['permissions']) == set(permissions.PERMISSION_KEYS)
```

- [ ] **Step 3: Run test, verify it fails then passes**

Run: `python -m pytest tests/test_permissions.py::test_auth_me_includes_permissions -v`
Expected: FAIL first (KeyError on `'permissions'` — old response shape), then PASS after Step 1's change.

- [ ] **Step 4: Wire frontend nav-hiding in `templates.py`**

Find the JS that currently calls `/api/auth/me` on load (`grep -n "auth/me" templates.py`). Store the returned `permissions` array in a module-level JS `let currentPermissions = new Set();` populated from that response. Add a small helper:

```js
function hasPermission(key) {
    return currentPermissions.has(key);
}
```

For each nav-tab whose backing feature maps to a permission key (Depo → `depo.view`, Billing → `billing.view`, Post Studio → `post_studio.use`, Settings → always visible since `/change-password` self-service has no permission gate, but the new "Manage Staff" group specifically should check `staff.manage`), wrap the existing tab/section visibility toggle: `if (!hasPermission('depo.view')) { navTab.style.display = 'none'; }` run once after the `/api/auth/me` response resolves, mirroring the existing pattern already used for hiding the Post Studio tab based on license state (reuse that existing conditional-hide code path, don't invent a second one — locate it with `grep -n "poststudio.*display\|license.*poststudio" templates.py` first).

- [ ] **Step 5: Syntax-check + full suite**

Run the same `node --check` extraction as Task 5, then:
Run: `python -m pytest tests/ -q`
Expected: `SYNTAX_OK` and full suite green.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py templates.py tests/test_permissions.py
git commit -m "feat(security): hide nav/UI the logged-in staff account can't use

/api/auth/me now returns the caller's granted permission keys; frontend
hides nav-tabs and Manage Staff for accounts lacking the corresponding
permission. Final task of the RBAC sub-project.

Known gap: no live-browser verification (Playwright blocked in this
environment) — same caveat as Task 5."
```

## Self-review notes

- Spec coverage: Decisions 3 (custom matrix) and 4 (desktop-only scope) fully covered; Architecture › RBAC's every listed component (tables, permission keys, migration, backend enforcement, frontend enforcement, Manage Staff UI, audit actor field) has a task. The refined `followups.*` permission (superseding the spec's shorter list) is called out explicitly in Global Constraints so it doesn't read as a silent contradiction of the spec.
- Placeholder scan: every step has complete code; the one explicit "check first, don't guess" instruction (Task 2, Step 1) is a real verification instruction, not a placeholder — the test's exact assertion depends on a string that must be grepped, not invented.
- Type/name consistency verified: `get_permissions`/`set_permission`/`grant_all`/`migrate_default_grants`/`PERMISSION_KEYS` are named identically everywhere they're used across Tasks 1-6. `_PERMISSION_RULES`/`_permission_required_for` introduced in Task 3 and not renamed later. `staff.manage`/`data_tools.use` etc. keys used consistently as literal strings matching `PERMISSION_KEYS` exactly.
- Both Task 5 and Task 6 honestly flag the same environment limitation already hit earlier this session (Playwright Chrome install fails, no admin rights) rather than silently skipping verification.
