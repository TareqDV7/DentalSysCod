# Email Auth + Per-Dentist Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Email-based sign-in + transactional emails (reset/verify/invite/alerts) via a stateless cloud relay, Windows-style login tiles, and server-enforced per-dentist data scoping with an admin/dentist/staff role model.

**Architecture:** The local Flask appliance (dental_clinic.py) gains auth codes, roles, and scoping; the SAME file running with `CLINIC_CLOUD_MODE=1` gains one stateless `/api/relay/email` endpoint that sends via Resend. All email-carried secrets are 6-digit OTP codes typed into the app (LAN-only appliance — links can't reach it). Spec: `docs/superpowers/specs/2026-07-14-email-auth-dentist-accounts-design.md`.

**Tech Stack:** Flask, SQLite, Werkzeug password hashing, stdlib urllib (no new deps), pytest.

## Global Constraints

- Password/code hashing: ALWAYS `hash_password()` (dental_clinic.py:89) which uses `PASSWORD_HASH_METHOD = 'pbkdf2:sha256'`. NEVER Werkzeug default (scrypt breaks frozen exe).
- Outbound HTTP: stdlib urllib only, matching `_cloud_http_request` (dental_clinic.py:9041) and reminder_channels.py. No requests/httpx/resend SDK.
- New pure-logic modules follow permissions.py pattern: cursor-level functions, no connection management.
- All new user-facing strings bilingual EN/AR (SPA uses existing i18n dict in templates.py; emails rendered per `lang` param).
- templates.py JS trap: HTML_TEMPLATE etc. are plain Python strings — JS `'\n'` must be written `'\\n'`. Verify edited JS with `node --check` where practical.
- Tests: run `python -m pytest tests/ -q` (NOT `rtk pytest`); check `$LASTEXITCODE`. Route tests set `session['uid']` via `client.session_transaction()`. conftest.py auto-attaches CSRF.
- CSRF: new JSON POSTs are covered by the global `_csrf_protect` gate automatically; no per-route work unless the route is a no-JS form.
- Anti-enumeration: forgot-password responses are byte-identical whether or not the account/email exists (plan supersedes spec's "masked address" display — masking leaks existence).
- No regressions: username+password login and all existing tests keep passing after every task.
- Frequent commits, conventional format (`feat:`/`fix:`/`test:`/`docs:`), no attribution lines (disabled via settings).

## File Map

| File | Change |
|---|---|
| `dental_clinic.py` | schema migration, login/lockout, forgot/reset/verify/invite/alert/recovery routes, relay endpoint (cloud), relay client, `dentist_scope` + route scoping, `/api/auth/me` role |
| `auth_codes.py` (new) | OTP issue/verify, recovery-code helpers |
| `email_templates.py` (new) | EN/AR subject+body rendering for 4 templates |
| `templates.py` | LOGIN_TEMPLATE tiles rewrite, SPA: staff email/role UI, profile verify, recovery code, hide dentist filter |
| `tests/test_*.py` (new, per task) | see tasks |
| `README.md`, `CHANGELOG.md`, `DEPLOY_CLOUD.md`, `cloud/docker-compose.yml` | docs + relay env |

---

### Task 1: Schema — roles, email columns, auth tables

**Files:**
- Modify: `dental_clinic.py` — `init_database()` around the `ensure_table_column` block at :1349-1360, plus new `migrate_user_roles(cursor)` called from `init_database()` right after `permissions.migrate_default_grants(cursor)` (grep for that call).
- Test: `tests/test_auth_schema.py`

**Interfaces:**
- Produces: users columns `email`, `email_verified`, `role`, `failed_login_count`, `locked_until`; tables `auth_codes`, `admin_recovery`; unique index `idx_users_email`; function `migrate_user_roles(cursor)`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth_schema.py
"""Schema for email auth + role model (spec 2026-07-14)."""
import sqlite3

import dental_clinic


def _fresh_db(tmp_path, monkeypatch):
    db = tmp_path / 'clinic.db'
    monkeypatch.setattr(dental_clinic, 'DATABASE', str(db), raising=False)
    dental_clinic.init_database()
    return sqlite3.connect(str(db))


def test_users_new_columns(tmp_path, monkeypatch):
    conn = _fresh_db(tmp_path, monkeypatch)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert {'email', 'email_verified', 'role', 'failed_login_count', 'locked_until'} <= cols


def test_auth_tables_exist(tmp_path, monkeypatch):
    conn = _fresh_db(tmp_path, monkeypatch)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'auth_codes' in names and 'admin_recovery' in names


def test_email_unique_index(tmp_path, monkeypatch):
    conn = _fresh_db(tmp_path, monkeypatch)
    idx = {r[1] for r in conn.execute("PRAGMA index_list(users)")}
    assert 'idx_users_email' in idx


def test_role_migration(tmp_path, monkeypatch):
    conn = _fresh_db(tmp_path, monkeypatch)
    cur = conn.cursor()
    cur.execute("INSERT INTO users (username, password_hash, is_dentist) VALUES ('d1', 'x', 1)")
    d1 = cur.lastrowid
    cur.execute("INSERT INTO users (username, password_hash, is_dentist) VALUES ('mgr', 'x', 1)")
    mgr = cur.lastrowid
    cur.execute("INSERT INTO user_permissions (user_id, permission_key, granted) VALUES (?, 'staff.manage', 1)", (mgr,))
    cur.execute("INSERT INTO users (username, password_hash) VALUES ('desk', 'x')")
    desk = cur.lastrowid
    cur.execute("UPDATE users SET role = NULL")
    dental_clinic.migrate_user_roles(cur)
    conn.commit()
    roles = dict(cur.execute("SELECT id, role FROM users WHERE id IN (?,?,?)", (d1, mgr, desk)))
    assert roles[d1] == 'dentist'
    assert roles[mgr] == 'admin'      # staff.manage beats is_dentist
    assert roles[desk] == 'staff'
    # idempotent: second run changes nothing
    dental_clinic.migrate_user_roles(cur)
    assert roles == dict(cur.execute("SELECT id, role FROM users WHERE id IN (?,?,?)", (d1, mgr, desk)))
```

NOTE: check how existing schema tests (tests/test_multi_dentist_schema.py) build a fresh DB and mirror THAT mechanism exactly instead of the `_fresh_db` sketch above if it differs — init/database path handling must match the suite's convention.

- [ ] **Step 2: Run, verify FAIL** — `python -m pytest tests/test_auth_schema.py -q` → fails (missing columns/tables/function).

- [ ] **Step 3: Implement**

In `init_database()` next to the other `ensure_table_column` calls (:1349-1360):

```python
    ensure_table_column(cursor, 'users', 'email', 'TEXT')
    ensure_table_column(cursor, 'users', 'email_verified', 'INTEGER DEFAULT 0')
    ensure_table_column(cursor, 'users', 'role', 'TEXT')
    ensure_table_column(cursor, 'users', 'failed_login_count', 'INTEGER DEFAULT 0')
    ensure_table_column(cursor, 'users', 'locked_until', 'TEXT')
    # SQLite can't add UNIQUE via ALTER; partial unique index instead.
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
                      ON users (email) WHERE email IS NOT NULL AND email != ' '||'' ''')
```

(Use `WHERE email IS NOT NULL AND email != ''` — write it plainly, the doubled quotes above are markdown-escaping noise.)

New tables next to the users CREATE TABLE block (:1168):

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            consumed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_recovery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_at TEXT
        )
    ''')
```

Module-level function (place near `permissions.migrate_default_grants` caller):

```python
def migrate_user_roles(cursor):
    """Derive role for users whose role is NULL/empty. admin (holds
    staff.manage) > dentist (is_dentist=1) > staff. Idempotent: rows with a
    role already set are never touched, so later manual demotions stick."""
    rows = cursor.execute(
        "SELECT id, is_dentist FROM users WHERE role IS NULL OR role = ''"
    ).fetchall()
    for row in rows:
        uid, is_dentist = row[0], row[1]
        has_manage = cursor.execute(
            'SELECT 1 FROM user_permissions WHERE user_id = ? AND '
            "permission_key = 'staff.manage' AND granted = 1", (uid,)).fetchone()
        role = 'admin' if has_manage else ('dentist' if is_dentist else 'staff')
        cursor.execute('UPDATE users SET role = ? WHERE id = ?', (role, uid))
```

Call `migrate_user_roles(cursor)` in `init_database()` immediately after `permissions.migrate_default_grants(cursor)`. Also: seeded first admin (INSERT at :1533) gets `role='admin'` explicitly via the migration on the same startup — no INSERT change needed.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_auth_schema.py tests/test_multi_dentist_schema.py -q` → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(auth): role column, email columns, auth_codes + admin_recovery tables"`

---

### Task 2: auth_codes.py — OTP + recovery-code logic

**Files:**
- Create: `auth_codes.py`
- Test: `tests/test_auth_codes.py`

**Interfaces:**
- Consumes: `auth_codes` / `admin_recovery` tables (Task 1); `hash_password`-equivalent hashing done internally with `generate_password_hash(code, method='pbkdf2:sha256')`.
- Produces:
  - `CODE_TTL_MINUTES = 10`, `MAX_ATTEMPTS = 5`
  - `issue_code(cursor, user_id, purpose) -> str` (6-digit, voids prior active codes for user+purpose)
  - `verify_code(cursor, user_id, purpose, code) -> str` — one of `'ok' | 'expired' | 'invalid' | 'locked'`; `'ok'` consumes.
  - `issue_recovery_code(cursor) -> str` (format `XXXX-XXXX-XXXX-XXXX`, voids prior unused rows)
  - `redeem_recovery_code(cursor, code) -> bool` (marks used)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth_codes.py
import sqlite3

import pytest

import auth_codes


@pytest.fixture
def cur():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE auth_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0, consumed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE admin_recovery (id INTEGER PRIMARY KEY AUTOINCREMENT, code_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, used_at TEXT);
    ''')
    yield conn.cursor()
    conn.close()


def test_issue_returns_six_digits_and_hashes(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    assert len(code) == 6 and code.isdigit()
    row = cur.execute('SELECT code_hash FROM auth_codes').fetchone()
    assert code not in row[0]                      # stored hashed, never plaintext
    assert row[0].startswith('pbkdf2:sha256')      # frozen-exe-safe method


def test_verify_ok_consumes(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'ok'
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'invalid'  # single use


def test_new_code_voids_old(cur):
    old = auth_codes.issue_code(cur, 1, 'password_reset')
    new = auth_codes.issue_code(cur, 1, 'password_reset')
    assert auth_codes.verify_code(cur, 1, 'password_reset', old) == 'invalid'
    assert auth_codes.verify_code(cur, 1, 'password_reset', new) == 'ok'


def test_purposes_isolated(cur):
    code = auth_codes.issue_code(cur, 1, 'email_verify')
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'invalid'


def test_expired(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    cur.execute("UPDATE auth_codes SET expires_at = '2000-01-01T00:00:00'")
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'expired'


def test_attempt_lockout(cur):
    code = auth_codes.issue_code(cur, 1, 'password_reset')
    for _ in range(auth_codes.MAX_ATTEMPTS):
        assert auth_codes.verify_code(cur, 1, 'password_reset', '000000') in ('invalid', 'locked')
    assert auth_codes.verify_code(cur, 1, 'password_reset', code) == 'locked'


def test_recovery_roundtrip(cur):
    code = auth_codes.issue_recovery_code(cur)
    assert len(code) == 19 and code.count('-') == 3
    assert auth_codes.redeem_recovery_code(cur, code) is True
    assert auth_codes.redeem_recovery_code(cur, code) is False  # single use


def test_recovery_regenerate_voids_old(cur):
    old = auth_codes.issue_recovery_code(cur)
    auth_codes.issue_recovery_code(cur)
    assert auth_codes.redeem_recovery_code(cur, old) is False
```

- [ ] **Step 2: Run, verify FAIL** — module missing.

- [ ] **Step 3: Implement**

```python
# auth_codes.py
"""OTP auth codes + one-time admin recovery codes. Cursor-level pure
functions, mirroring permissions.py: no connection management here.
Hashing is pbkdf2:sha256 explicitly (frozen-exe rule — see
dental_clinic.PASSWORD_HASH_METHOD)."""
import secrets
import string
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
_HASH_METHOD = 'pbkdf2:sha256'
_RECOVERY_ALPHABET = string.ascii_uppercase + string.digits


def _now():
    return datetime.utcnow()


def issue_code(cursor, user_id, purpose):
    """Create a fresh 6-digit code for (user, purpose); voids any prior
    active codes so only the newest one works. Returns plaintext code —
    caller emails it and must never store it."""
    cursor.execute(
        'UPDATE auth_codes SET consumed = 1 WHERE user_id = ? AND purpose = ? AND consumed = 0',
        (user_id, purpose))
    code = f'{secrets.randbelow(1000000):06d}'
    expires = (_now() + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(timespec='seconds')
    cursor.execute(
        'INSERT INTO auth_codes (user_id, purpose, code_hash, expires_at) VALUES (?, ?, ?, ?)',
        (user_id, purpose, generate_password_hash(code, method=_HASH_METHOD), expires))
    return code


def verify_code(cursor, user_id, purpose, code):
    """Returns 'ok' (and consumes) | 'expired' | 'invalid' | 'locked'."""
    row = cursor.execute(
        'SELECT id, code_hash, expires_at, attempts FROM auth_codes '
        'WHERE user_id = ? AND purpose = ? AND consumed = 0 '
        'ORDER BY id DESC LIMIT 1', (user_id, purpose)).fetchone()
    if not row:
        return 'invalid'
    code_id, code_hash, expires_at, attempts = row[0], row[1], row[2], row[3]
    if attempts >= MAX_ATTEMPTS:
        return 'locked'
    if _now().isoformat(timespec='seconds') > expires_at:
        return 'expired'
    if not check_password_hash(code_hash, str(code or '')):
        cursor.execute('UPDATE auth_codes SET attempts = attempts + 1 WHERE id = ?', (code_id,))
        return 'locked' if attempts + 1 >= MAX_ATTEMPTS else 'invalid'
    cursor.execute('UPDATE auth_codes SET consumed = 1 WHERE id = ?', (code_id,))
    return 'ok'


def issue_recovery_code(cursor):
    """One-time clinic recovery code XXXX-XXXX-XXXX-XXXX. Voids prior unused
    codes. Returns plaintext exactly once — show/print, never store."""
    cursor.execute("UPDATE admin_recovery SET used_at = 'voided' WHERE used_at IS NULL")
    groups = [''.join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(4)]
    code = '-'.join(groups)
    cursor.execute('INSERT INTO admin_recovery (code_hash) VALUES (?)',
                   (generate_password_hash(code, method=_HASH_METHOD),))
    return code


def redeem_recovery_code(cursor, code):
    row = cursor.execute(
        'SELECT id, code_hash FROM admin_recovery WHERE used_at IS NULL '
        'ORDER BY id DESC LIMIT 1').fetchone()
    normalized = (code or '').strip().upper()
    if not row or not check_password_hash(row[1], normalized):
        return False
    cursor.execute("UPDATE admin_recovery SET used_at = datetime('now') WHERE id = ?", (row[0],))
    return True
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_auth_codes.py -q` → PASS.
- [ ] **Step 5: Commit** — `feat(auth): auth_codes module — OTP issue/verify + recovery codes`

---

### Task 3: email_templates.py — EN/AR rendering

**Files:**
- Create: `email_templates.py`
- Test: `tests/test_email_templates.py`

**Interfaces:**
- Produces: `render(template: str, lang: str, params: dict) -> tuple[str, str]` (subject, body). Templates: `password_reset`, `email_verify`, `staff_invite`, `security_alert`. `lang` in `('en', 'ar')`, unknown → `'en'`. Unknown template → `ValueError`. Params: `clinic_name`, `code` (reset/verify/invite), `username` (invite), `event` + `detail` (alert).

- [ ] **Step 1: Failing tests**

```python
# tests/test_email_templates.py
import pytest

import email_templates


def test_reset_en_contains_code():
    subject, body = email_templates.render('password_reset', 'en',
                                           {'clinic_name': 'Smile Co', 'code': '123456'})
    assert '123456' in body and 'Smile Co' in body and subject


def test_reset_ar_is_arabic():
    subject, body = email_templates.render('password_reset', 'ar',
                                           {'clinic_name': 'X', 'code': '123456'})
    assert '123456' in body
    assert any('؀' <= ch <= 'ۿ' for ch in body)  # Arabic script present


def test_all_templates_both_langs():
    params = {'clinic_name': 'C', 'code': '000000', 'username': 'u',
              'event': 'password_changed', 'detail': 'x'}
    for t in ('password_reset', 'email_verify', 'staff_invite', 'security_alert'):
        for lang in ('en', 'ar'):
            subject, body = email_templates.render(t, lang, params)
            assert subject and body


def test_unknown_template_raises():
    with pytest.raises(ValueError):
        email_templates.render('nope', 'en', {})


def test_unknown_lang_falls_back_to_en():
    s_en, _ = email_templates.render('email_verify', 'en', {'clinic_name': 'C', 'code': '1'})
    s_xx, _ = email_templates.render('email_verify', 'fr', {'clinic_name': 'C', 'code': '1'})
    assert s_en == s_xx
```

- [ ] **Step 2: FAIL** (module missing).

- [ ] **Step 3: Implement** — plain-text bodies (no HTML), `str.format(**params)` with `params` defaulted via `{'clinic_name': '', 'code': '', 'username': '', 'event': '', 'detail': '', **(params or {})}`. Structure:

```python
# email_templates.py
"""Plain-text EN/AR bodies for system emails sent through the cloud relay.
Rendered cloud-side so sender branding stays consistent. Keep plain text —
OTP codes need no HTML, and plain text dodges RTL-HTML rendering bugs."""

_TEMPLATES = {
    'password_reset': {
        'en': ('Your {clinic_name} password reset code',
               'Your password reset code is: {code}\n\n'
               'It expires in 10 minutes. If you did not request this, ignore this email.\n\n'
               '— DentaCare'),
        'ar': ('رمز إعادة تعيين كلمة المرور - {clinic_name}',
               'رمز إعادة تعيين كلمة المرور: {code}\n\n'
               'صالح لمدة 10 دقائق. إذا لم تطلب ذلك، تجاهل هذه الرسالة.\n\n'
               '— DentaCare'),
    },
    # ... email_verify, staff_invite, security_alert same shape.
    # staff_invite EN body: 'You have been invited to {clinic_name}.\nUsername: {username}\n'
    #   'Temporary sign-in code (use as your password once): {code}\n'
    #   'You will choose your own password on first sign-in.'
    # security_alert EN body: 'Security event at {clinic_name}: {event}\n{detail}\n'
    #   'If this was not you or your staff, reset the affected password now.'
    # AR bodies: write real Arabic translations (implementer: proper phrasing,
    #   NOT machine transliteration; mirror the EN content faithfully).
}


def render(template, lang, params):
    entry = _TEMPLATES.get(template)
    if entry is None:
        raise ValueError(f'unknown email template: {template!r}')
    subject, body = entry.get(lang) or entry['en']
    safe = {'clinic_name': '', 'code': '', 'username': '', 'event': '', 'detail': '',
            **(params or {})}
    return subject.format(**safe), body.format(**safe)
```

Write the remaining three templates fully in both languages (real Arabic sentences — same register as the SPA's existing AR strings in templates.py).

- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat(auth): bilingual email templates for system emails`

---

### Task 4: Cloud relay endpoint `/api/relay/email`

**Files:**
- Modify: `dental_clinic.py` — new route near the other CLOUD_MODE-only routes (grep `def api_clinics_register` / the :6496 clinics area); rate-limit dict near `_validate_attempts` (:444-452); Resend sender helper.
- Modify: `cloud/docker-compose.yml` — add `RESEND_API_KEY`, `CLINIC_EMAIL_FROM` env passthrough.
- Test: `tests/test_email_relay_cloud.py`

**Interfaces:**
- Consumes: `email_templates.render` (Task 3), `_resolve_clinic_token()` (:455), clinics table, `_check_attempts` rate-limit pattern (:444).
- Produces: `POST /api/relay/email` (CLOUD_MODE only, else 404). Request: `{to, template, params, lang}` + `X-Clinic-Token` header. Responses: 200 `{'sent': True}`; 401 bad/inactive token; 400 `{'error': ...}` bad template/address; 429 rate limited; 502 provider failure. Module-level `_send_via_resend(to, subject, body)` (monkeypatch point for local-client tests in Task 5).

- [ ] **Step 1: Failing tests**

```python
# tests/test_email_relay_cloud.py
"""Relay endpoint: auth, rate limit, provider call. Follow the CLOUD_MODE
test-setup conventions in tests/test_cloud_mode.py (env flag + fresh master
DB + registered clinic w/ clinic_token) — reuse its fixture approach."""
import dental_clinic


def _register_clinic(...):  # mirror test_cloud_mode.py's helper for a clinic row + token
    ...


def test_relay_requires_cloud_mode(local_client):
    # CLINIC_CLOUD_MODE off → route 404s
    r = local_client.post('/api/relay/email', json={})
    assert r.status_code == 404


def test_relay_rejects_bad_token(cloud_client):
    r = cloud_client.post('/api/relay/email', json={'to': 'a@b.c', 'template': 'password_reset',
                                                    'params': {}, 'lang': 'en'},
                          headers={'X-Clinic-Token': 'nope'})
    assert r.status_code == 401


def test_relay_sends(cloud_client, monkeypatch, clinic_token):
    calls = []
    monkeypatch.setattr(dental_clinic, '_send_via_resend',
                        lambda to, subject, body: calls.append((to, subject, body)))
    r = cloud_client.post('/api/relay/email',
                          json={'to': 'a@b.c', 'template': 'password_reset',
                                'params': {'clinic_name': 'X', 'code': '123456'}, 'lang': 'en'},
                          headers={'X-Clinic-Token': clinic_token})
    assert r.status_code == 200 and r.get_json()['sent'] is True
    assert calls and '123456' in calls[0][2]


def test_relay_unknown_template_400(cloud_client, clinic_token): ...
def test_relay_rate_limit_429(cloud_client, monkeypatch, clinic_token):
    # monkeypatch dental_clinic._RELAY_HOURLY_LIMIT to 2, send 3, expect 429
    ...
def test_relay_provider_failure_502(cloud_client, monkeypatch, clinic_token):
    # _send_via_resend raises → 502, body {'error': ...}
    ...
```

(Ellipses above are the test-fixture plumbing to copy from test_cloud_mode.py — the assertions shown are the contract; write them all out.)

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Implement**

```python
# --- system email relay (cloud node only) -----------------------------------
_RELAY_HOURLY_LIMIT = _env_int('CLINIC_RELAY_HOURLY_LIMIT', 10)
_RELAY_DAILY_LIMIT = _env_int('CLINIC_RELAY_DAILY_LIMIT', 30)
_relay_attempts_hour = {}
_relay_attempts_day = {}


def _send_via_resend(to, subject, body):
    """POST to Resend HTTP API. Raises on any failure (caller maps to 502).
    stdlib urllib per the codebase convention."""
    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    sender = os.environ.get('CLINIC_EMAIL_FROM', 'DentaCare <no-reply@dentacare.tech>').strip()
    if not api_key:
        raise RuntimeError('RESEND_API_KEY not configured')
    payload = json.dumps({'from': sender, 'to': [to], 'subject': subject,
                          'text': body}).encode('utf-8')
    req = urllib.request.Request(
        'https://api.resend.com/emails', data=payload, method='POST',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 300:
            raise RuntimeError(f'Resend status {resp.status}')


@app.route('/api/relay/email', methods=['POST'])
def api_relay_email():
    if not CLOUD_MODE:
        return jsonify({'error': 'Not found'}), 404
    token = _resolve_clinic_token()
    # validate against clinics table exactly like the existing sync auth (:511-518)
    conn = get_master_db_connection()   # ← use whatever helper :511 actually uses
    row = conn.execute('SELECT id, active FROM clinics WHERE clinic_token = ?', (token,)).fetchone()
    conn.close()
    if not token or not row or not row[1]:
        return jsonify({'error': 'Unauthorized'}), 401
    clinic_id = row[0]
    # per-clinic sliding-window limits, reusing the _check_attempts machinery
    err = _check_attempts(_relay_attempts_hour.setdefault(clinic_id, []),
                          _RELAY_HOURLY_LIMIT, 3600, 'relay emails')
    if err is None:
        err = _check_attempts(_relay_attempts_day.setdefault(clinic_id, []),
                              _RELAY_DAILY_LIMIT, 86400, 'relay emails')
    if err is not None:
        return err   # match _check_attempts's actual return contract (inspect :420-452)
    data = request.json or {}
    to = str(data.get('to') or '').strip()
    if '@' not in to or len(to) > 254:
        return jsonify({'error': 'Invalid recipient address'}), 400
    try:
        subject, body = email_templates.render(
            str(data.get('template') or ''), str(data.get('lang') or 'en'),
            data.get('params') or {})
    except ValueError:
        return jsonify({'error': 'Unknown template'}), 400
    try:
        _send_via_resend(to, subject, body)
    except Exception as exc:  # noqa: BLE001 — provider/network failure maps to 502
        logging.getLogger(__name__).warning('relay email send failed: %s', exc)
        return jsonify({'error': 'Email provider failure'}), 502
    return jsonify({'sent': True})
```

IMPORTANT adaptations for the implementer: read `_check_attempts` (:420-452) and the clinic-token validation block (:511-518) first and match their real signatures/return values — the sketch above shows intent, the file is the truth. `import email_templates` at top with the other local imports. Log counts only, never `to`/`body`.

docker-compose env additions (cloud service `environment:` block):

```yaml
      - RESEND_API_KEY=${RESEND_API_KEY:-}
      - CLINIC_EMAIL_FROM=${CLINIC_EMAIL_FROM:-DentaCare <no-reply@dentacare.tech>}
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_email_relay_cloud.py tests/test_cloud_mode.py -q` → PASS.
- [ ] **Step 5: Commit** — `feat(cloud): stateless /api/relay/email endpoint (Resend, per-clinic rate limits)`

---

### Task 5: Local relay client `send_system_email`

**Files:**
- Modify: `dental_clinic.py` — near `_run_cloud_sync_once` / `_cloud_sync_config` (:9061-9084).
- Test: `tests/test_system_email_client.py`

**Interfaces:**
- Consumes: `_cloud_http_request(method, url, headers, body, timeout)` (:9041), `_cloud_sync_config()` (:9061).
- Produces:
  - `send_system_email(to, template, params, lang='en') -> tuple[bool, str]` — `(True, '')` or `(False, reason)` where reason ∈ `'not_paired' | 'unreachable' | 'rate_limited' | 'rejected' | 'provider'`.
  - `send_system_email_async(to, template, params, lang='en')` — daemon thread, swallows+logs all failures (for alerts).

- [ ] **Step 1: Failing tests** — monkeypatch `dental_clinic._cloud_http_request` with a fake returning `(status, json_body)` per its real contract (inspect :9041 first); cases: 200→(True,''), no cloud config→(False,'not_paired'), exception→(False,'unreachable'), 429→(False,'rate_limited'), 400→(False,'rejected'), 502→(False,'provider'). Async: assert a monkeypatched `send_system_email` gets called from `send_system_email_async` (join the thread) and that exceptions inside don't propagate.

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Implement**

```python
def send_system_email(to, template, params, lang='en'):
    """Send one system email through the cloud relay. Returns (ok, reason)."""
    cloud_url, clinic_token, _ = _cloud_sync_config()
    if not (cloud_url and clinic_token):
        return False, 'not_paired'
    try:
        status, resp = _cloud_http_request(
            'POST', cloud_url.rstrip('/') + '/api/relay/email',
            headers={'X-Clinic-Token': clinic_token, 'Content-Type': 'application/json'},
            body={'to': to, 'template': template, 'params': params, 'lang': lang},
            timeout=10)
    except Exception:  # noqa: BLE001 — network failure is an expected offline state
        return False, 'unreachable'
    if status == 200:
        return True, ''
    if status == 429:
        return False, 'rate_limited'
    if status in (400, 401):
        return False, 'rejected'
    return False, 'provider'


def send_system_email_async(to, template, params, lang='en'):
    """Fire-and-forget for security alerts: never blocks, never raises."""
    def _run():
        try:
            ok, reason = send_system_email(to, template, params, lang)
            if not ok:
                logging.getLogger(__name__).info('alert email skipped: %s', reason)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception('alert email crashed')
    threading.Thread(target=_run, daemon=True).start()
```

(Match `_cloud_http_request`'s real body/return conventions — it may take pre-encoded bytes.)

- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat(auth): local send_system_email relay client + async alert wrapper`

---

### Task 6: Login — email-or-username + lockout

**Files:**
- Modify: `dental_clinic.py` `login_page()` (:2563-2594).
- Test: `tests/test_login_email_lockout.py`

**Interfaces:**
- Consumes: users columns from Task 1.
- Produces: login accepts email OR username in the same form field (still named `username`); 5 consecutive failures → `locked_until = now+15min` (per user), lockout alert via `send_system_email_async` (wired fully in Task 9 — call it here already); success resets counter. Locked account → same 401 page with lockout message. Constant `LOCKOUT_THRESHOLD = 5`, `LOCKOUT_MINUTES = 15`.

- [ ] **Step 1: Failing tests** — seed a user with email `doc@x.com` (use existing helper patterns from tests/test_force_password_change.py for user seeding): login with email works; login with username still works; 5 bad passwords → 6th attempt with CORRECT password still rejected while locked; `locked_until` in past → login succeeds and resets `failed_login_count`; inactive user with email can't log in.

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Implement** — replace the user lookup in `login_page()`:

```python
        identifier = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        conn = get_db_connection(with_row_factory=True)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM users WHERE (username = ? OR (email IS NOT NULL AND '
            "email != '' AND lower(email) = lower(?))) AND is_active = 1",
            (identifier, identifier))
        user = cursor.fetchone()
        now_iso = datetime.utcnow().isoformat(timespec='seconds')
        if user and user['locked_until'] and user['locked_until'] > now_iso:
            conn.close()
            return render_template_string(LOGIN_TEMPLATE,
                error='Too many failed attempts — try again in a few minutes.',
                next_url=next_url, csrf_token=_get_or_create_csrf_token()), 401
        if user and check_password_hash(user['password_hash'], password):
            cursor.execute('UPDATE users SET last_login_at = CURRENT_TIMESTAMP, '
                           'failed_login_count = 0, locked_until = NULL WHERE id = ?',
                           (user['id'],))
            # ... existing success path unchanged (session.clear() etc.)
        # failure path:
        if user:
            failed = (user['failed_login_count'] or 0) + 1
            locked_until = None
            if failed >= LOCKOUT_THRESHOLD:
                locked_until = (datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                                ).isoformat(timespec='seconds')
                _alert_admins('account_locked', f"user '{user['username']}' locked after "
                              f'{failed} failed sign-ins')   # Task 9 defines; stub no-op now
            cursor.execute('UPDATE users SET failed_login_count = ?, locked_until = ? WHERE id = ?',
                           (failed, locked_until, user['id']))
            conn.commit()
        conn.close()
        # keep the existing generic 'Invalid username or password.' response
```

Add module-level `LOCKOUT_THRESHOLD = 5`, `LOCKOUT_MINUTES = 15`, and a temporary `def _alert_admins(event, detail): pass` stub (Task 9 fills it). Keep the error string generic for wrong-password vs no-user (anti-enumeration).

- [ ] **Step 4: Run** — plus regression: `python -m pytest tests/test_login_email_lockout.py tests/test_force_password_change.py tests/test_csrf.py -q` → PASS.
- [ ] **Step 5: Commit** — `feat(auth): email-or-username login + failed-attempt lockout`

---

### Task 7: Forgot / reset password routes

**Files:**
- Modify: `dental_clinic.py` — two new routes next to `login_page`; add both paths to the pre-auth public allowlist (grep the before_request gate that redirects anonymous users to /login — find where `/login` is exempted and mirror).
- Test: `tests/test_password_reset_flow.py`

**Interfaces:**
- Consumes: `auth_codes.issue_code/verify_code`, `send_system_email`, users email columns.
- Produces:
  - `POST /api/login/forgot` `{identifier}` → ALWAYS 200 `{'sent': True}` (byte-identical regardless of account existence/verified email/relay failure — log the real outcome server-side only).
  - `POST /api/login/reset` `{identifier, code, new_password}` → 200 on success (password set, lockout cleared, codes consumed, alert fired); 400 `{'error': 'Invalid or expired code'}` on any failure (same message for all failure kinds); min password length 4 (match change_password_page).

- [ ] **Step 1: Failing tests** — with `send_system_email` monkeypatched to capture: happy path end-to-end (forgot → captured code → reset → login with new password works); response for unknown identifier identical to known (compare full JSON + status); unverified email → no send but same response; wrong code → 400; expired (UPDATE auth_codes SET expires_at past) → 400; code single-use; reset clears `locked_until`.

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Implement**

```python
@app.route('/api/login/forgot', methods=['POST'])
def api_login_forgot():
    data = request.json or {}
    identifier = str(data.get('identifier') or '').strip()
    generic = jsonify({'sent': True})
    if not identifier:
        return generic
    conn = get_db_connection(with_row_factory=True)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM users WHERE (username = ? OR (email IS NOT NULL AND '
        "email != '' AND lower(email) = lower(?))) AND is_active = 1",
        (identifier, identifier))
    user = cursor.fetchone()
    if user and user['email'] and user['email_verified']:
        code = auth_codes.issue_code(cursor, user['id'], 'password_reset')
        conn.commit()
        clinic_name = read_app_setting(cursor, 'clinic_name', 'DentaCare')
        lang = read_app_setting(cursor, 'ui_language', 'en')   # ← verify actual setting key; grep templates/app_settings
        ok, reason = send_system_email(user['email'], 'password_reset',
                                       {'clinic_name': clinic_name, 'code': code}, lang)
        if not ok:
            logging.getLogger(__name__).info('reset email not sent: %s', reason)
    conn.close()
    return generic


@app.route('/api/login/reset', methods=['POST'])
def api_login_reset():
    data = request.json or {}
    identifier = str(data.get('identifier') or '').strip()
    code = str(data.get('code') or '').strip()
    new_password = str(data.get('new_password') or '')
    fail = (jsonify({'error': 'Invalid or expired code'}), 400)
    if len(new_password) < 4:
        return jsonify({'error': 'New password must be at least 4 characters.'}), 400
    conn = get_db_connection(with_row_factory=True)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM users WHERE (username = ? OR (email IS NOT NULL AND '
        "email != '' AND lower(email) = lower(?))) AND is_active = 1",
        (identifier, identifier))
    user = cursor.fetchone()
    if not user or auth_codes.verify_code(cursor, user['id'], 'password_reset', code) != 'ok':
        conn.commit()  # persist attempt counter
        conn.close()
        return fail
    cursor.execute('UPDATE users SET password_hash = ?, failed_login_count = 0, '
                   'locked_until = NULL, must_change_password = 0 WHERE id = ?',
                   (hash_password(new_password), user['id']))
    append_audit_log(cursor, 'update', 'password_reset', user['id'], {'via': 'email_code'})
    conn.commit()
    conn.close()
    _alert_admins('password_changed', f"password reset via email for '{user['username']}'")
    return jsonify({'success': True})
```

Add `import auth_codes` top-level. Register both paths in the anonymous-allowed set of the login gate (find it: grep `login_page` redirect logic in a before_request).

- [ ] **Step 4: Run** — plus `tests/test_csrf.py`, `tests/test_permissions.py` regressions → PASS.
- [ ] **Step 5: Commit** — `feat(auth): forgot/reset password via emailed OTP, anti-enumeration`

---

### Task 8: Email set + verification

**Files:**
- Modify: `dental_clinic.py` — `/api/profile/email` + `/api/profile/email/verify` (new, authed); `/api/staff` GET/POST + PUT gain `email`/`role` fields (:2644-2710).
- Test: `tests/test_email_verification.py`

**Interfaces:**
- Produces:
  - `POST /api/profile/email` `{email}` (self, any logged-in user) → stores lowercased email, `email_verified=0`, issues `email_verify` code, sends it; 400 on malformed/duplicate email (`'That email is already in use'`).
  - `POST /api/profile/email/verify` `{code}` → `email_verified=1` on 'ok', 400 otherwise.
  - `/api/staff` GET now returns `email`, `email_verified`, `role`; PUT accepts `email` (admin-set, resets `email_verified=0`, re-issues verify code + send) and `role` (`admin|dentist|staff`, syncs `is_dentist = 1 if role=='dentist' else is_dentist-stays-for-admin?` — rule: `is_dentist = 1` iff role == 'dentist'; refuse demoting the last active admin, mirroring the staff.manage guard at :2686-2694).
  - `GET /api/auth/me` adds `'role'` and `'email'`, `'email_verified'` fields.

- [ ] **Step 1: Failing tests** — set email → row updated + code captured; verify wrong/right code; duplicate email 400; admin PUT email resets verified; role change syncs is_dentist; demote-last-admin 400; auth/me contains role.

- [ ] **Step 2: FAIL.**  

- [ ] **Step 3: Implement** — follow the exact route/handler style of `/api/staff` (:2644). Email validation: `'@' in email and 3 <= len(email) <= 254` (no regex worship). Duplicate check: `SELECT id FROM users WHERE lower(email) = lower(?) AND id != ?`. auth_me (:2603) adds role/email/email_verified from a single SELECT.

- [ ] **Step 4: Run** — plus `tests/test_multi_dentist_staff_ui.py` regression → PASS.
- [ ] **Step 5: Commit** — `feat(auth): email set + OTP verification, staff email/role management`

---

### Task 9: Staff invite + security alerts

**Files:**
- Modify: `dental_clinic.py` — `/api/staff` POST (:2656-2677) invite branch; real `_alert_admins`; hook alert calls into `change_password_page` success (:2554-2560), `/api/staff` POST success, lockout (Task 6 already calls).
- Test: `tests/test_invite_and_alerts.py`

**Interfaces:**
- Consumes: `auth_codes.issue_code`, `send_system_email`, `send_system_email_async`.
- Produces:
  - `/api/staff` POST: when `email` present and `password` empty → temp code becomes the password (`hash_password(code)`), `must_change_password=1`, `email_verified=1` (invite delivery itself proves ownership), staff_invite email sent; response includes `'invited': True`. Password-ful creation unchanged.
  - `def _alert_admins(event, detail)`: SELECT active users `role='admin' AND email != '' AND email_verified=1`; for each, `send_system_email_async(email, 'security_alert', {'clinic_name': ..., 'event': event, 'detail': detail}, lang)`. Never raises.

- [ ] **Step 1: Failing tests** — invite: POST staff with email, no password → user created with must_change_password=1, invite email captured containing 6-digit code, login with that code as password works then forces change (reuse test_force_password_change.py patterns); alerts: monkeypatch `send_system_email_async`, trigger password change / staff create / lockout → assert called with verified-admin recipients only; alert failure (raise inside) doesn't break the parent action.

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement** — replace Task 6's `_alert_admins` stub with the real one; invite branch inside existing POST handler, keep `username` required.
- [ ] **Step 4: Run** — plus `tests/test_force_password_change.py` → PASS.
- [ ] **Step 5: Commit** — `feat(auth): email staff invites + admin security alert emails`

---

### Task 10: Admin recovery code

**Files:**
- Modify: `dental_clinic.py` — `POST /api/settings/recovery-code` (gated `settings.manage` via the permission table at :2353 — add `(None, r'^/api/settings/recovery-code$', 'staff.manage')`), `POST /api/login/recover` (public allowlist like Task 7).
- Test: `tests/test_recovery_code.py`

**Interfaces:**
- Consumes: `auth_codes.issue_recovery_code/redeem_recovery_code`.
- Produces:
  - `POST /api/settings/recovery-code` → `{'code': 'XXXX-XXXX-XXXX-XXXX'}` (plaintext once; voids old).
  - `POST /api/login/recover` `{code, new_password}` → redeems; resets password of the OLDEST active `role='admin'` user; clears their lockout; auto-issues a replacement recovery code and returns `{'success': True, 'username': <admin username>, 'new_recovery_code': <fresh code>}`; 400 `{'error': 'Invalid recovery code'}` otherwise; fires `_alert_admins('recovery_used', ...)`.

- [ ] **Step 1: Failing tests** — generate → redeem resets oldest admin's password (login works), response carries fresh code, old code dead; wrong code 400; regenerate voids prior; endpoint permission-gated (non-staff.manage user → 403 per existing gate behavior in test_permissions.py).
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement** — straightforward; oldest admin: `SELECT id, username FROM users WHERE role='admin' AND is_active=1 ORDER BY id LIMIT 1`; if none → treat as invalid code (400).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat(auth): one-time admin recovery code (offline lockout escape)`

---

### Task 11: `dentist_scope` helper + appointments scoping

**Files:**
- Modify: `dental_clinic.py` — helper near the permission gates (~:2350); apply in appointments routes: list/create (:3359-3420 area), availability/conflict + update (:3866-3933 area), the update/delete route around :6041-6099. Read each route fully first.
- Test: `tests/test_role_scoping_appointments.py`

**Interfaces:**
- Produces:
  - `def _session_role(cursor) -> str` — role of `session['uid']` (`''` if anonymous).
  - `def dentist_scope(cursor, alias='') -> tuple[str, list]` — for role `dentist`: `(' AND {p}dentist_id = ?', [uid])` where `{p}` is `alias + '.'` if alias else `''`; else `('', [])`.
  - Rule (all scoped routes): role `dentist` ⇒ reads filtered to own rows; any client-supplied `dentist_id` (query param or body) IGNORED and forced to `session['uid']` on create; update/delete of a row whose `dentist_id` differs → 403 `{'error': 'Not your record'}`; rows with `dentist_id IS NULL` are VISIBLE to dentists (legacy/front-desk-unassigned bookings must not vanish) but NOT editable by them unless being claimed — keep it simple: NULL rows visible read-only to dentists.

- [ ] **Step 1: Failing tests** — seed admin + dentist A + dentist B + appointments for each + one NULL-dentist row (copy seeding style from tests/test_multi_dentist_appointments.py); as dentist A: list shows A's + NULL rows only; create with forged `dentist_id=B` lands as A; PUT/DELETE B's row → 403; PUT NULL row → 403; as admin: sees all, existing filter param still works.
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement** — helper + per-route WHERE additions. In each SELECT add the scope fragment; in POST, after the existing dentist_id validation block (:3359-3376), add `if _session_role(cursor) == 'dentist': dentist_id = session['uid']`. Update/delete: fetch row's dentist_id first, 403 mismatch.
- [ ] **Step 4: Run** — plus `tests/test_multi_dentist_appointments.py tests/test_appointment_api.py tests/test_dentist_scoped_conflicts.py` → PASS (admin/staff behavior unchanged).
- [ ] **Step 5: Commit** — `feat(rbac): dentist_scope helper + server-enforced appointment scoping`

---

### Task 12: Scoping — billing + followups

**Files:**
- Modify: `dental_clinic.py` — billing list/create/update routes and followup routes (grep `FROM billing`, `FROM patient_followups`; the dentist_id columns exist per :1349-1351).
- Test: `tests/test_role_scoping_billing_followups.py`

**Interfaces:** same rule as Task 11 verbatim (reads scoped + NULL visible read-only; writes forced to self; cross-dentist 403).

- [ ] **Step 1: Failing tests** — mirror Task 11's matrix for billing and followups (copy seeding from tests/test_multi_dentist_billing.py / test_multi_dentist_followups.py).
- [ ] **Step 2: FAIL.** 
- [ ] **Step 3: Implement** with `dentist_scope`.
- [ ] **Step 4: Run** — plus `tests/test_multi_dentist_billing.py tests/test_multi_dentist_followups.py tests/test_followup_balance.py tests/test_payment_history.py` → PASS.
- [ ] **Step 5: Commit** — `feat(rbac): dentist scoping for billing + followups`

---

### Task 13: Scoping — reports + dashboard

**Files:**
- Modify: `dental_clinic.py` — report endpoints with per-dentist breakdowns (:4412-4448, :4548-4581) and dashboard aggregates (grep the dashboard route).
- Test: `tests/test_role_scoping_reports.py`

**Interfaces:**
- Rule: role `dentist` ⇒ every aggregate filtered `dentist_id = uid` (their numbers only — NULL-dentist rows EXCLUDED from a dentist's financial totals: money not attributed to them isn't theirs); `dentist_breakdown` arrays collapse to just their own entry; any client dentist-filter param ignored. Admin/staff: untouched.

- [ ] **Step 1: Failing tests** — seed mixed billing/followups across dentists incl. NULL; as dentist A: totals == A-only sums, breakdown length 1; forged filter param ignored; as admin: unchanged totals (regression vs tests/test_per_dentist_reporting.py expectations).
- [ ] **Step 2: FAIL.** 
- [ ] **Step 3: Implement.** 
- [ ] **Step 4: Run** — plus `tests/test_per_dentist_reporting.py tests/test_reports_gross_profit.py` → PASS.
- [ ] **Step 5: Commit** — `feat(rbac): dentist-scoped reports + dashboard`

---

### Task 14: Login page — tiles + forgot/recovery UI

**Files:**
- Modify: `templates.py` LOGIN_TEMPLATE (:10515) — full rewrite; `dental_clinic.py` `login_page()` GET passes `tiles` context.
- Test: `tests/test_login_tiles_ui.py`

**Interfaces:**
- `login_page()` GET: query `SELECT id, username, display_name, role FROM users WHERE is_active = 1 ORDER BY display_name` — pass as `tiles` list ONLY when count ≤ 12, else `tiles=[]`.
- LOGIN_TEMPLATE renders: tile grid (initial-letter avatar from display_name, name, role badge Admin/Dentist/Staff — EN labels with AR handled the same way LOGIN_TEMPLATE handles language today; if it's EN-only today, keep EN-only, SPA i18n is out of template scope), click → fills hidden `username` field with that username + focuses password; "Sign in another way" link toggles classic identifier+password form; "Forgot password?" section (identifier → JS fetch `/api/login/forgot` → code+new-password fields → `/api/login/reset`); "Use recovery code" link → code+new-password → `/api/login/recover`, on success shows returned `new_recovery_code` with a copy-me warning. All fetches send `X-CSRFToken` from the embedded csrf_token. Jinja-escape everything; JS strings follow the `'\\n'` double-escape rule.

- [ ] **Step 1: Failing tests** — string-assertion style like tests/test_login_tiles_ui.py neighbors (test_calendar_dentist_filter_ui.py is 622B — same idea): GET /login contains tile markup + usernames for a ≤12-user DB; contains forgot-password + recovery markers; with 13 users, no tile markup.
- [ ] **Step 2: FAIL.** 
- [ ] **Step 3: Implement** — after editing, `node --check` the extracted inline JS if feasible, or at minimum run the UI tests + a manual GET.
- [ ] **Step 4: Run** — plus `tests/test_csrf.py tests/test_force_password_change.py` → PASS.
- [ ] **Step 5: Commit** — `feat(auth): Windows-style login tiles + forgot-password + recovery UI`

---

### Task 15: SPA — role-aware UI (staff mgmt, profile, filters)

**Files:**
- Modify: `templates.py` HTML_TEMPLATE — Manage Staff (email field + verify badge + role selector + "Reset password" button); `dental_clinic.py` `/api/staff/<id>` PUT gains a `new_password` field (admin local reset: sets `hash_password(new_password)`, `must_change_password=1` — this is the zero-internet staff reset from the spec); Settings → recovery-code generate button + one-time display modal; profile menu → my email + verify-code entry; dentist filter dropdowns (calendar + reports) hidden when `auth/me.role == 'dentist'`.
- Test: `tests/test_role_ui.py` (+ extend `tests/test_multi_dentist_staff_ui.py` if it asserts staff-form markup)

**Interfaces:**
- Consumes: `/api/auth/me` role field (Task 8), all routes from Tasks 7-10.
- All new strings added to BOTH `en` and `ar` i18n dicts in templates.py (find the existing translation object; follow its key style).

- [ ] **Step 1: Failing tests** — UI string assertions: HTML_TEMPLATE contains staff email input marker, role selector options, reset-password button id, recovery-code button id, verify-email modal id; JS gating references `role === 'dentist'` for the filter hide. Backend: PUT with `new_password` forces change flag.
- [ ] **Step 2: FAIL.** 
- [ ] **Step 3: Implement** — smallest-diff edits inside HTML_TEMPLATE; keep the `'\\n'` rule; update BOTH language dicts.
- [ ] **Step 4: Run** — full suite now: `python -m pytest tests/ -q` → PASS. Then visual smoke per `reference_web_visual_smoke` memory (fresh temp DB → login → check Manage Staff + Settings + login tiles, light + dark).
- [ ] **Step 5: Commit** — `feat(ui): role-aware staff management, email verify, recovery code, dentist filter lock`

---

### Task 16: Docs + deploy

**Files:**
- Modify: `README.md` (features section — memory `feedback_workflow`: README updated per task batch), `CHANGELOG.md`, `DEPLOY_CLOUD.md` (new "Email relay" section: Resend account, domain DNS records for dentacare.tech (SPF/DKIM via Resend dashboard), `RESEND_API_KEY` + `CLINIC_EMAIL_FROM` in `cloud/.env`, rate-limit env knobs, redeploy command).

- [ ] **Step 1: Write docs** — cover: user emails + verification, tile login, forgot-password codes, invites, alerts, recovery code (print + store safely!), dentist data scoping semantics (shared patients, own clinical/financial, NULL-row visibility rule), offline fallbacks.
- [ ] **Step 2: Full suite** — `python -m pytest tests/ -q` → PASS; `$LASTEXITCODE` 0.
- [ ] **Step 3: Commit** — `docs: email auth + per-dentist accounts (user guide, changelog, cloud deploy)`

---

## Post-plan notes for the executor

- Order is dependency-true: 1→2→3→4→5(needs 4 for lockout alert stub only — stub keeps it decoupled)→6→7(needs 2,5)→8→9→10→11→12→13→14(needs 7,10)→15(needs 8-13)→16.
- Manual pre-ship smoke (NOT CI): set real `RESEND_API_KEY` on cloud, trigger one real reset email, verify inbox + SPF/DKIM pass.
- The two spec deviations decided here: (1) no masked-email display on forgot (enumeration leak) — generic message instead; (2) invite marks email pre-verified (delivery proves ownership). Both noted for the spec owner.
- Rebuild exe/installer after merge per `reference_exe_build_inno` (rebuild.bat + ISCC) — separate step, ask user first.
