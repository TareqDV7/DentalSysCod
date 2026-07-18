# Email Auth + Per-Dentist Accounts — Design

Date: 2026-07-14
Status: Approved (brainstorm dialogue)

## Goal

1. Email-based sign-in and transactional emails (password reset, verification, staff invite, security alerts) for the local DentaCare clinic appliance.
2. Windows-users-style login: user tiles on the login page; admins see all clinic data, dentists are server-side locked to their own clinical/financial data.

## Constraints

- Clinic app is a LAN-only Windows appliance. Clickable email reset links cannot reach it. All email-carried secrets are **6-digit codes typed into the app** (OTP style).
- Cloud server (app.dentacare.tech) is live, authenticates clinics by license token, and must stay stateless about clinic auth.
- Frozen-exe rule: password/code hashing uses `pbkdf2:sha256` explicitly (never Werkzeug default scrypt — breaks under PyInstaller).
- Bilingual EN/AR product: all emails and new UI strings ship in both languages; Arabic email templates are RTL.
- No regressions: existing username+password login keeps working throughout.

## Decisions (from dialogue)

| Question | Decision |
|---|---|
| Isolation depth | Shared patients; dentist owns own appointments, followups/treatments, billing, reports — server-enforced |
| Email delivery | Cloud relay through app.dentacare.tech; provider Resend; sender `no-reply@dentacare.tech` |
| Emails in scope | Password reset, email verification, staff invite/welcome, security alerts |
| Login identifier | Email **or** username, both accepted |
| Login UX | Windows-style user tiles + password; classic typed field as fallback |
| Offline fallback | Admin resets staff locally (no email); admin self-recovery via one-time printed recovery code |

## 1. Data model, roles, scoping

### users table — new columns

- `email TEXT UNIQUE` (nullable; existing users add later)
- `email_verified INTEGER DEFAULT 0`
- `role TEXT DEFAULT 'staff'` — one of `admin` | `dentist` | `staff`
- `failed_login_count INTEGER DEFAULT 0`
- `locked_until TEXT` (ISO timestamp, NULL when unlocked)

### Migration

- `is_dentist = 1` → role `dentist`.
- Users granted `staff.manage` permission → role `admin` (takes precedence over dentist flag).
- Everyone else → `staff`.
- `is_dentist` column **stays** (30+ references); kept in sync with role by the user-management routes.
- Idempotent, runs in `init_db` alongside `ensure_table_column` calls.
- Role is orthogonal to the existing `user_permissions` keys: permissions keep gating **feature access** (which tabs/actions a user may touch); role gates **data visibility** (whose rows they see) plus admin-only auth actions (Manage Staff resets, recovery code).

### New tables

```sql
CREATE TABLE auth_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,          -- 'password_reset' | 'email_verify' | 'invite'
    code_hash TEXT NOT NULL,        -- pbkdf2:sha256
    expires_at TEXT NOT NULL,       -- now + 10 min
    attempts INTEGER DEFAULT 0,     -- voided at 5
    consumed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE admin_recovery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT NOT NULL,        -- pbkdf2:sha256 of XXXX-XXXX-XXXX-XXXX
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TEXT                    -- single use
);
```

- One active code per (user, purpose): issuing a new code marks prior ones consumed.
- Recovery code: 16 chars in 4 groups, generated from `secrets`, shown/printable exactly once; regenerating voids the old one.

### Scoping — single server-side helper

```python
def dentist_scope(session) -> tuple[str, list]:
    """role=dentist → ('AND <alias>.dentist_id = ?', [uid]); else ('', [])."""
```

- Applied in every read path for appointments, followups, billing, reports, dashboard aggregates.
- Writes: a dentist-created row gets `dentist_id` forced to their own uid; editing/deleting a row owned by another dentist → 403 (404 where the route already hides existence).
- Any client-sent dentist filter param is ignored for role `dentist`.
- Patients remain clinic-shared under the existing permission keys.
- Admin/staff keep the existing per-dentist filter dropdowns; the dentist role never sees them.

## 2. Cloud relay + auth flows

### Cloud: `POST /relay/email` (stateless)

- Body: `{to, template, params, lang}`; templates rendered cloud-side (EN/AR, RTL for AR).
- Auth: existing per-clinic license token header (same mechanism as sync/claim endpoints); revoked serial → refused.
- Rate limits per clinic serial: 10/hour, 30/day.
- Sends via Resend as `no-reply@dentacare.tech`. Logs counts only — never recipient bodies.
- Templates: `password_reset`, `email_verify`, `staff_invite`, `security_alert`.

### Local flows

**Login page (tiles).** Active users listed as tiles: initial avatar, display name, role badge. Click tile → password prompt. "Sign in another way" reveals classic field accepting email OR username. Tiles suppressed above 12 users. CSRF + existing session mechanics unchanged.

**Forgot password.** Tile → "Forgot?". Only works when user has a verified email. App generates code, stores hash, calls relay, shows masked address (`a***@***.com`). User enters code + new password. Expiry 10 min, 5 attempts, single use. Response is identical whether the account/email exists or not (anti-enumeration).

**Email verification.** User (or admin on their behalf) sets email → code emailed → entered in profile/Settings → `email_verified = 1`. Changing email resets verification. Resets only ever go to verified addresses.

**Staff invite.** Admin creates user with email → invite email contains temp 6-digit code used as first password; `must_change_password = 1` forces set-password on first login (existing gate reused).

**Security alerts.** Fire-and-forget relay calls on: password changed, new user created, lockout triggered. Sent to admin users with verified emails. Failures log locally, never block the action.

**Lockout.** 5 consecutive failures → `locked_until = now + 15 min`, alert email to admins. Counter resets on success.

**Offline fallbacks.**
- Manage Staff → "Reset password": admin sets temp password, `must_change_password = 1`. Zero internet needed.
- Login page → "Use recovery code": admin enters one-time recovery code → forced new password → new recovery code generated and displayed once.

## 3. Security

- Codes from `secrets`, pbkdf2-hashed, constant-time verify, single-use, 10-min TTL, 5 attempts.
- Anti-enumeration on forgot-password and on login error messages.
- Relay auth piggybacks license token; cloud validates against license DB.
- New POST routes join existing synchronizer-token CSRF protection.
- Scoping is a security boundary, not a UI convenience: cross-dentist access attempts and forged `dentist_id` values are tested explicitly.

## 4. Error handling

| Failure | Behavior |
|---|---|
| Relay unreachable / timeout (10 s) | "Couldn't send email — check internet or ask admin to reset locally" |
| Provider rejects address | Relay returns 4xx + reason; app: "email address rejected" |
| Rate limit hit | Message with retry-after time |
| Alert email fails | Silent local log only |

## 5. Testing

- Unit: code generate/verify/expiry/attempt-void, `dentist_scope` per role, migration role derivation, recovery-code lifecycle.
- Route (pytest, existing `session['uid']` harness, relay client mocked): full reset flow, invite flow, verify flow, lockout, enumeration-response equality, dentist cross-access → 403, admin unfiltered, forged dentist_id ignored, tiles endpoint hides inactive users.
- Cloud suite: relay auth (valid/revoked token), rate limiting, template rendering EN/AR.
- No live email in CI; one manual Resend smoke before ship.

## Out of scope

- Multi-clinic accounts, SSO/OAuth, email login on mobile app (mobile keeps device pairing), patient-facing emails beyond existing reminders, per-dentist patient ownership.
