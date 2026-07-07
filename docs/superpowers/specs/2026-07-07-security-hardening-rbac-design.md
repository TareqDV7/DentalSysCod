# Security Hardening: CSP + Staff RBAC + Encryption-at-Rest (Design Spec)

**Date:** 2026-07-07
**Status:** Approved design — ready for implementation plan.
**Sequencing:** first of 5 planned sub-projects (security → CI testing → recall system → unified clinic gross profit → multi-dentist support). This spec covers **security only**.

## Context

Two items were flagged open after the prior "Security hardening round" (memory:
`project_security_hardening_round`) and never done: encryption-at-rest and CSP.
Separately, the app has a single shared `admin`/`admin` portal login — every
staff member who touches the desktop app (dentist, front desk, anyone else)
uses the same account, so there is no way to know who did what, or to limit
what a front-desk user can see (e.g. clinical notes) versus what a dentist
can see. RBAC was raised as a natural third piece to build now rather than
later, because the upcoming multi-dentist sub-project will also need a
multi-staff-account concept — building it once here avoids reworking auth
twice.

The desktop app runs in two execution contexts that constrain the design:
an interactive WebView window (`dentacare_window.py`) and an installed
background Windows service (`%PROGRAMDATA%\DentaCare`, per
`window/service_port.py` and the free-port handshake). Any design that needs
a human to type something at startup (e.g. a decryption passphrase) breaks
the unattended service path.

The frontend (`templates.py`, ~10k lines) is built entirely on inline
`onclick="..."` handlers — hundreds of them. This directly constrains how
strict a CSP can be without a large separate refactor.

## Goal

Ship three independent, sequentially-ordered improvements:
1. CSP response header (trivial, ships first).
2. Staff accounts with a custom per-account permission matrix, replacing the
   single shared admin login (desktop portal only).
3. Whole-database encryption-at-rest via SQLCipher, with a key that never
   requires a human to type a passphrase (ships last — highest risk).

## Decisions (all user-approved 2026-07-07)

1. **Three separate PRs, not one branch.** CSP → RBAC → Encryption, in that
   order. Risk escalates in that order; each is independently revertable.
   Shipping the smallest, safest change first banks a win before the riskiest
   change (the encryption connection-layer swap) is attempted.

2. **CSP: pragmatic, not strict-nonce.** Keep `'unsafe-inline'` for
   `script-src`/`style-src` so every existing `onclick="..."` handler and
   inline `<style>` keeps working unmodified — migrating hundreds of
   `onclick=` attributes to `addEventListener` wiring is a separate, large,
   mechanical effort with its own risk profile and is explicitly deferred
   (see Non-goals). Everything else gets locked down: no external
   script/style/font sources, `frame-ancestors 'none'` (clickjacking),
   `object-src 'none'`, `base-uri 'self'`, `connect-src`/`img-src` scoped to
   `'self'` + the known cloud host. This still blocks external script
   injection, iframe embedding, and exfiltration to unknown hosts — it just
   doesn't add protection against an XSS that injects *inline* script, which
   the app already guards against by HTML-escaping DB-derived strings
   (confirmed in the invoice-rendering code this session).

3. **RBAC: fully custom permission matrix**, not fixed roles. Every staff
   account gets an individually configurable set of permission grants (not a
   fixed Owner/Dentist/Front-Desk label). This is the most flexible option
   and the most UI/backend surface, chosen deliberately over the simpler
   fixed-role options because a small clinic's actual staff mix doesn't
   always map cleanly onto 3-4 predefined roles.

4. **RBAC scope: desktop portal only.** The mobile app keeps its existing
   device-pairing model (one paired device = full access, unchanged). Mobile
   RBAC is explicitly out of scope for this spec — a future sub-project once
   desktop RBAC has proven out in the field.

5. **Encryption: SQLCipher, whole-database**, not field-level or
   OS-delegated. Protects against the realistic threat for a self-hosted
   single-machine appliance: the `.db` file (or the laptop it's on) is
   physically removed and read on another machine. Field-level encryption
   was rejected as only partial protection (names/phones/billing amounts
   would still be plaintext); relying on BitLocker alone was rejected as
   giving up on the app doing anything at all.

6. **Encryption key: Windows DPAPI, machine scope, not user-entered
   passphrase.** A passphrase-at-launch model was rejected because the
   installed background service cannot prompt a human on every boot, and
   caching the passphrase somewhere for the service to read would recreate
   the exact "key sitting next to the file" problem encryption is meant to
   avoid. DPAPI in **machine scope** (`CRYPTPROTECT_LOCAL_MACHINE`, not user
   scope) is required specifically because the interactive desktop app and
   the installed service may run under different Windows execution
   contexts (logged-in user vs. service account) and both need to decrypt
   the same protected key blob without prompting anyone.

7. **Migration for existing installed clinics: automatic, not opt-in.**
   Clinic staff are non-technical and will not seek out a "Encrypt my
   database" settings toggle — an opt-in button was rejected because it
   realistically means most installs stay unencrypted forever. On first
   launch after the upgrade, the app detects a plaintext DB, backs it up via
   the existing backup mechanism, encrypts in place, verifies, and proceeds
   silently. Failure at any step rolls back to the pre-migration backup —
   the clinic is never left without a working, openable database.

## Architecture

### CSP
Added to the existing security-headers `after_request` hook from the prior
hardening round (not a new hook). One policy string, one header, no new
files.

### RBAC
- New tables: `staff_accounts` (`id`, `username`, `password_hash`,
  `display_name`, `active`, `created_at`) and `staff_permissions`
  (`staff_id`, `permission_key`, `granted`).
- Fixed, enumerated permission key set (not free-form strings), covering the
  app's actual surface: `patients.view`, `patients.edit`, `clinical.view`,
  `clinical.edit` (notes, treatment plans, odontogram), `billing.view`,
  `billing.edit`, `expenses.view`, `expenses.edit`, `depo.view`, `depo.edit`,
  `reports.view`, `post_studio.use`, `data_tools.use` (merge/replace/export —
  destructive, off by default for non-Owner accounts), `settings.manage`,
  `staff.manage` (gates creating/editing other staff accounts and their
  permissions — without this gate a non-privileged account could grant
  itself more access).
- Migration: the existing portal password becomes the first `staff_accounts`
  row (`display_name = 'Owner'`) with every permission key granted. Existing
  installs see no login disruption.
- Backend enforcement: a `@require_permission('key')` decorator wraps
  routes; a request from a staff account lacking the permission gets a 403
  JSON error, not a crash or a silent no-op.
- Frontend enforcement: permissions for the logged-in staff account are
  fetched once at login into a `currentPermissions` set; nav-tabs and
  action buttons the account lacks permission for are hidden (not merely
  disabled, to avoid confusing empty states).
- New UI: Settings → "Manage Staff" (gated on `staff.manage`) — list
  accounts, add/deactivate, and a permission checkbox grid per account.
- `append_audit_log` gains an actor field (which staff account performed the
  action) — the audit log currently records what happened but not
  reliably who did it under a shared login.

### Encryption
- New dependency: a SQLCipher Python binding with a prebuilt Windows wheel.
  **Must be validated against the existing PyInstaller build
  (`DentaCare.spec`) before the rest of this piece is built** — bundling a
  native SQLCipher DLL into a frozen executable is the single largest
  unknown in this spec and needs an early spike, not a late surprise.
- Key lifecycle: on first need, generate 32 random bytes, protect via
  `CryptProtectData` (machine scope), write the protected blob to
  `%PROGRAMDATA%\DentaCare\encryption.key`. Unprotect via
  `CryptUnprotectData` on every app/service start to get the raw key for
  the `PRAGMA key = "x'...'"` handshake.
- A single shared connection helper (e.g. `get_encrypted_connection()`)
  replaces every direct `sqlite3.connect(DB_NAME)` call site — grepped at
  ~50+ occurrences across `dental_clinic.py`. This is the largest mechanical
  change in the whole security sub-project.
- Migration function runs once per install: detect plaintext (a vanilla
  `sqlite3.connect` + trivial read succeeding means plaintext), back up,
  use SQLCipher's export mechanism to produce an encrypted copy, verify row
  counts across all tables match, atomically replace the file, audit-log
  the event.

## Data flow

Login (RBAC): staff submits username/password → server validates against
`staff_accounts` → session cookie set as today, plus the staff's granted
permission keys are attached to the session/loaded on each request → every
route decorated with `@require_permission` checks against that set before
executing.

DB access (encryption): any code path that today does
`sqlite3.connect(DB_NAME)` instead calls `get_encrypted_connection()`, which
reads/unprotects the DPAPI key once (cached in memory for the process
lifetime) and issues `PRAGMA key` immediately after connecting, before any
other statement runs.

## Error handling

- Permission-denied requests return a 403 with a clear JSON error the
  frontend can render as a toast, not a stack trace.
- Encryption migration failure at any step (backup, export, verify,
  replace) aborts and restores the pre-migration backup automatically; the
  app logs a clear error and refuses to silently continue on unverified
  data.
- DPAPI unprotect failure (e.g. key blob corrupted, or moved to a different
  machine where DPAPI can't unprotect it) must fail loudly at startup with
  an actionable message, not silently fall back to an unencrypted or
  broken state.

## Testing (TDD)

- CSP: a single test asserting the header value/policy string is present on
  a representative response.
- RBAC: permission-denied path returns 403 (not 500) for each gated route;
  Owner auto-migration produces a staff account with all permissions
  granted; staff CRUD (create/deactivate/permission-grant) round-trips;
  audit log entries carry the correct actor.
- Encryption: migration happy path (plaintext → encrypted, row counts
  match); forced-failure mid-migration (simulated write error) rolls back
  to the pre-migration backup rather than leaving a half-migrated file;
  `get_encrypted_connection()` round-trips read/write correctly.
- The full existing suite (742+ tests as of this session) must stay green
  throughout — it already exercises nearly every route and is the primary
  regression net for the connection-helper swap touching ~50+ call sites.

## Non-goals (deferred)

- Strict nonce-based CSP (no `unsafe-inline`) — would require migrating
  every `onclick="..."` handler to `addEventListener` first; a separate,
  large, mechanical effort on its own.
- 2FA on portal login — raised as an idea, not included in this spec.
- Mobile RBAC / per-staff mobile login — mobile keeps device-pairing as-is.
- Field-level encryption of specific columns — superseded by whole-DB
  encryption.
