# Licensing overhaul — A1: Cloud License Authority — design

## Goal

Make the **cloud node the authority** for "is this serial valid, active, and allowed on
this device?" — so the product can be **sold** with real anti-piracy and a **subscription**
lifecycle, without breaking its offline-first operation.

A1 is the foundation layer: a cryptographically-verifiable serial format (Ed25519), a
cloud-side serial + device-slot inventory, and a single `POST /api/license/validate`
endpoint that every client calls once at first run (and periodically thereafter). It does
**not** change client UX or local activation yet — those are A2 and A3.

The owner's hard requirement: **"not anyone can use any random serials to enter."** A1
satisfies this cryptographically — an unsigned/forged serial fails Ed25519 verification and
never reaches the inventory.

## Initiative context

This is one of four sub-projects in the licensing/onboarding overhaul. Each gets its own
spec → plan → build:

- **A. Licensing backbone + online validation** — split into three shippable layers:
  - **A1 (this spec)** — cloud license authority + Ed25519 serial format. Pure backend.
  - **A2** — local-server activation hardening (verify the vendor signature in
    `/api/license/activate`, server-derived device fingerprint, server-side `max_devices`,
    enforce device membership on `/login` & `/status`, fix the grace-date bypass). Local
    `licenses`/`license_devices` become a **cache** of cloud truth.
  - **A3** — first-run online gate UX, subscription renewal, and **advisory** revocation
    (view-only degrade), with license validation **decoupled** from cloud-sync enable.
- **B** — premium first-run onboarding (serial once, no URL typing, baked cloud URL).
- **C** — toggle-only auto cloud sync.
- **D** — responsive admin serial-minting app (the pretty UI around the Ed25519 signer).

Build order: **A1 → A2 → A3 → B → C**, with D slotting in once the Ed25519 signing core
(landed in A1) needs a GUI. The existing `serial_generator.py` CLI covers minting test
serials meanwhile.

### Locked decisions (from brainstorming, 2026-06-03)

1. **Online once, then offline.** First run requires internet to validate + claim the
   serial; afterwards the clinic runs offline indefinitely. It **never locks for being
   offline** — it only goes view-only on **license expiry/revocation**, learned on the next
   online check-in (A3). A1 provides the validate endpoint that makes this possible.
2. **Register-on-first-use + signature.** No pre-uploaded inventory. The first time a
   **validly-signed** serial is presented, the cloud records it and binds the device. A
   random/unsigned string fails signature verification and is rejected — that is the
   "no random serials" guarantee.
3. **Subscription model.** A serial carries `expires_at` + `grace_until`. The cloud tracks
   subscription status; lapsed-past-grace = `expired`. (Renewal UX + view-only degrade are
   A3; A1 stores and reports the state.)
4. **Asymmetric Ed25519 signing.** The vendor **private** seed never leaves the vendor
   machine. The **public** key ships in the cloud node (and later the apps). Public keys
   verify but cannot mint. Replaces the current shared-secret HMAC. The public demo-key
   fallback is **removed**.
5. **Device cap per serial.** One serial = one clinic, with a configurable device cap
   (default `3`: desktop + phones). Enforced atomically cloud-side.
6. **Validation is decoupled from cloud-save** (A3 concern, noted here): A1's
   `/api/license/validate` does licensing only; it never enables cloud sync as a side effect.

## Existing mechanics (build on, do not break)

- **Cloud authority lives in `cloud_master.db`.** The `clinics` table is CREATEd in
  `init_database` (`dental_clinic.py:~886`); columns include `serial_number UNIQUE`,
  `clinic_token`, `active`. `register_clinic` (`dental_clinic.py:~4135`) is the idempotent
  tenant provisioner (creates the clinic row + per-tenant DB). **A1 keeps `register_clinic`
  as the provisioner and adds a *separate* license layer it can call** — it does not bloat
  `register_clinic` with slot/revocation logic (architect R3).
- **Vendor signature verifier already exists (HMAC).** `_verify_serial_token`
  (`dental_clinic.py:~236`) + `_serial_signing_key` (`~226`, reads `CLINIC_SERIAL_SIGNING_KEY`).
  Wired into the register gate at `~4163` behind `CLINIC_REQUIRE_SIGNED_SERIAL` (`~223`,
  default off). **A1 replaces the HMAC verifier with an Ed25519 verifier** and makes
  verification mandatory at the cloud authority.
- **`serial_generator.py`** is the vendor signer: `generate_license_token` (`~48`) HMAC-signs
  a base64 payload; `load_signing_key` (`~120`) reads `backend_key.json`. **A1 reworks the
  signing to Ed25519** and **removes the public demo-key fallback** (`serial_generator.py:~74`,
  security finding H-5 — a known constant key in source).
- **Cloud-open routes** are listed in `_CLOUD_OPEN_EXACT` (`dental_clinic.py:~192`).
  `/api/license/validate` is added there (callable without a clinic token, like
  `register`/`offline-verify`).
- **HTTP plumbing** for client→cloud is `_cloud_http_request` (`dental_clinic.py:~5796`,
  stdlib `urllib`); the mobile uses `CloudSyncService` over `dio`. A2/B reuse these to call
  `/api/license/validate`; A1 only builds the endpoint.
- **Migrations** go through `ensure_table_column` (`~377`/`~927`) for new columns and
  `CREATE TABLE IF NOT EXISTS` for new tables, inside `init_database`, guarded by `CLOUD_MODE`
  where appropriate.
- **Rate limit** `_check_register_rate_limit` (`~289`) reads `_client_ip` (`~283`), which
  currently trusts `X-Forwarded-For` verbatim (spoofable — security H-3).

## A1 scope

**In:** Ed25519 keypair + token format; `serial_generator.py` Ed25519 signing (+ demo-key
removal); cloud `license_serials` + `license_device_slots` tables; `POST /api/license/validate`
with atomic cap enforcement and register-on-first-use; an admin-gated revoke/status endpoint;
`ProxyFix` hardening; full backend test suite.

**Out (later layers):** any change to local `/api/license/activate` (A2); client first-run
UX, renewal, view-only degrade, cloud-save coupling (A3); the admin GUI (D); baking the
public key into the apps + offline Dart verification (A2/B).

## Key material (Ed25519)

- One vendor keypair, generated once via a small `serial_generator.py --genkey` subcommand
  (or a one-off script). Output:
  - **Private seed** → a new local file (e.g. `backend_ed25519_key.json`, **gitignored**),
    shape `{"alg":"ed25519","private":"<base64 32-byte seed>"}`. Never committed, never
    shipped. This is the new "crown jewel" (replaces `backend_key.json`).
  - **Public key** → printed/exported as base64; configured on the cloud node as
    `CLINIC_SERIAL_PUBLIC_KEY`. (Later baked into the apps for offline signature checks.)
- **Library:** Python `cryptography` (Hazmat `Ed25519PrivateKey`/`Ed25519PublicKey`) — well
  maintained, bundles under PyInstaller (requires adding to `requirements.txt` and a
  `hiddenimports` entry in `DentaCare.spec`; the build-resolver handles bundling). PyNaCl is
  an acceptable lighter alternative if `cryptography`'s OpenSSL footprint is a problem at
  package time; the spec defaults to `cryptography`.
- **Migration from HMAC:** there are no real signed serials in circulation yet (HMAC gate
  defaults off), so this is a clean cutover — no dual-verify path needed. If any HMAC serials
  exist, they are re-issued.

## Serial token v2 (Ed25519)

Format (unchanged envelope, new signature alg): `base64url(payload_json).base64url(ed25519_sig)`.

Payload fields:

```json
{
  "v": 2,
  "serial": "DENTAL-SMD-AB12C-00001",
  "clinic_name": "Smile Dental",
  "plan_name": "standard",
  "max_devices": 3,
  "issued_at":  "2026-06-03T00:00:00Z",
  "expires_at": "2027-06-03T00:00:00Z",
  "grace_until":"2027-06-17T00:00:00Z"
}
```

- The signature covers the exact `payload_json` bytes. Verification: decode payload, verify
  Ed25519 signature with the public key, then enforce field semantics.
- `serial` is the human-readable id (existing `DENTAL-CODE-DEV-NNNNN` format from
  `generate_device_serial_number`, `serial_generator.py:~22`).

## New cloud tables (`cloud_master.db`, guarded to `CLOUD_MODE`)

```sql
CREATE TABLE IF NOT EXISTS license_serials (
  serial        TEXT PRIMARY KEY,
  status        TEXT NOT NULL DEFAULT 'active',  -- active|revoked|suspended|expired
  plan_name     TEXT,
  max_devices   INTEGER NOT NULL DEFAULT 3,
  issued_at     TEXT,
  expires_at    TEXT,                            -- subscription window (ISO)
  grace_until   TEXT,
  clinic_id     INTEGER,                         -- set when the serial registers a clinic
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS license_device_slots (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  serial             TEXT NOT NULL,
  device_fingerprint TEXT NOT NULL,
  device_name        TEXT,
  claimed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_seen_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active          INTEGER NOT NULL DEFAULT 1,
  UNIQUE(serial, device_fingerprint)
);
```

- `license_serials` is the subscription + revocation source of truth. It mirrors the shape of
  the per-clinic local `licenses` table (`dental_clinic.py:~899`) so A2 can treat the local
  row as a cache of this.
- `license_device_slots` is the cloud equivalent of the per-clinic `license_devices`
  (`~914`). The `UNIQUE(serial, fingerprint)` makes re-claims idempotent.

## Endpoint: `POST /api/license/validate` (cloud-only)

Returns `404` outside `CLOUD_MODE` (same guard pattern as `register_clinic`, `~4143`).
Added to `_CLOUD_OPEN_EXACT` (no clinic token required). Rate-limited like `register`.

**Request:** `{ "serial_token": "<v2 token>", "device_fingerprint": "<opaque>", "device_name": "<optional>" }`

**Algorithm** — all inside one `BEGIN IMMEDIATE` transaction on `cloud_master.db` (so the
count-then-insert cap check is atomic; architect R4):

1. **Verify signature.** Decode the token; verify Ed25519 with `CLINIC_SERIAL_PUBLIC_KEY`.
   On failure → `{ "valid": false, "reason": "bad_signature" }` (HTTP 200; the request was
   well-formed). Malformed token / missing fields → HTTP 400.
2. **Register-on-first-use / renewal.** `SELECT` the serial from `license_serials`.
   - If absent → INSERT it using the token's `plan_name`/`max_devices`/`expires_at`/
     `grace_until` (status `active`).
   - If present and the token is validly signed with a **later** `expires_at` → this is a
     **renewal**: update the stored `expires_at`/`grace_until`/`max_devices`/`plan_name` from
     the token and, if it was `expired`, flip `status` back to `active`. (A signed token is
     trusted, so a fresh signed serial is how a subscription renews — the renewal UX is A3.)
   - Never shorten the stored window from an **older** token (ignore stale `expires_at`).
3. **Status gate.** If `status` is `revoked`/`suspended` →
   `{ "valid": false, "reason": "<status>" }`.
4. **Subscription gate.** If `now > grace_until` → set `status='expired'`, return
   `{ "valid": false, "reason": "expired", "expires_at", "grace_until" }`.
5. **Device slot.**
   - If `(serial, device_fingerprint)` already exists → update `last_seen_at`, treat as OK
     (idempotent re-validate — no new slot consumed).
   - Else `SELECT COUNT(*) WHERE serial=? AND is_active=1`; if `< max_devices` → INSERT the
     slot; else → `{ "valid": false, "reason": "device_cap_reached", "max_devices" }`.
6. **Success:** `{ "valid": true, "status": "active", "plan_name", "expires_at",
   "grace_until", "remaining_slots": max_devices - active_slots }`.

**Idempotency:** re-validating the same `(serial, fingerprint)` always returns the current
state and never consumes a second slot.

## Admin: revoke / status

`POST /api/license/admin/revoke` (cloud-only), gated by a shared admin secret header
(`X-Admin-Token` compared to env `CLINIC_ADMIN_API_TOKEN`; returns 401 without it). Body
`{ "serial": "...", "status": "revoked|suspended|active" }` → updates `license_serials.status`.
This makes revocation end-to-end testable now; the friendly admin UI is sub-project D.
Slot **release** (reactivating a lost device's slot) is also exposed here as
`{ "serial", "device_fingerprint", "release": true }` → `is_active=0` (operator-driven, no
auto-eviction — a phone offline for a month is normal, architect R4).

## Hardening: trusted client IP

Wrap the WSGI app with `werkzeug.middleware.proxy_fix.ProxyFix` (configured for one proxy
hop — Caddy) so `_client_ip` (`~283`) reflects the real client, not a spoofable
`X-Forwarded-For`. This makes the register/validate rate limit meaningful (security H-3).

## Error handling

- Signature/expiry/cap failures are **business outcomes** → HTTP 200 with
  `{valid:false, reason}`, never 500 (the public API must not 500 on bad input — matches the
  existing fuzz-test contract, `tests/test_api_fuzz.py`).
- Malformed JSON / missing required fields → HTTP 400 with a generic message.
- Internal errors are logged server-side and return a generic message — **no paths/SQL/
  exception text leak** (consistent with the recent `register_clinic` hardening, `c7bfaec`).

## Security notes (set expectations)

- **What A1 stops:** random/forged serials (Ed25519), serial reuse beyond the device cap,
  and lets you revoke/expire a serial (effective on next online contact).
- **What no offline-first design can stop** (security review): a determined attacker with
  local OS access can extract a local key, patch the binary, or wind the clock back. A1 +
  A2 raise the bar to "casual piracy impossible," not "uncrackable."
- **Key management:** the Ed25519 **private seed** is the single most sensitive artifact —
  losing it means re-issuing all serials; leaking it lets an attacker mint serials. It stays
  offline on the vendor machine. The cloud only ever holds the **public** key.

## Test plan (A1 — all backend `pytest`)

New suite `tests/test_license_authority.py` (+ extend `tests/test_cloud_mode.py`):

- **Signature:** valid token accepted; tampered payload rejected; random string rejected;
  wrong-key signature rejected.
- **Register-on-first-use:** a fresh valid serial is inserted as `active`; second call is
  idempotent.
- **Status gate:** `revoked`/`suspended` serial → `valid:false` with the right reason.
- **Subscription:** not-yet-expired ok; past `expires_at` but within grace ok; past
  `grace_until` → `expired`.
- **Renewal:** a later-signed token extends `expires_at` and flips `expired`→`active`; an
  older-signed token never shortens the stored window.
- **Device cap:** claim up to `max_devices`; same fingerprint re-claim = no new slot;
  `max_devices+1`th distinct fingerprint → `device_cap_reached`; slot release frees one.
- **Concurrency:** N parallel validates for distinct fingerprints on a cap-2 serial must
  never exceed 2 active slots (the atomic-transaction guarantee).
- **Admin:** revoke flips status and the next validate returns `revoked`; admin endpoint
  401s without `X-Admin-Token`.
- **ProxyFix:** `_client_ip` returns the real client behind a simulated proxy hop; rate limit
  counts per real IP.
- **Cloud-only guard:** `/api/license/validate` returns 404 when not in `CLOUD_MODE`.
- **No-500 fuzz:** malformed/oversized bodies → 400/200, never 500.

A `serial_generator` round-trip test (sign with private seed → verify with public key →
validate endpoint) replaces the existing HMAC round-trip test (`tests/test_cloud_mode.py:~236`).

## Dependencies

- **Python:** `cryptography` (Ed25519). Add to `requirements.txt` + `DentaCare.spec`
  `hiddenimports`. (Dart `package:cryptography` is added later in A2/B for offline client
  verification — out of scope here.)

## Deferred / open (resolved in later specs, flagged so they aren't lost)

- **Who validates at first run — desktop, mobile, or both?** The owner wants the serial
  typed+checked on both. The architecture review cautions mobile should derive license state
  from the desktop over LAN rather than running a divergent cloud check. **Resolved in A3/B.**
  A1 just exposes the endpoint; either client can call it.
- **Admin auth** is a shared-secret header for now; a proper admin auth model arrives with
  sub-project D.
- **Public-key distribution to apps** (for offline signature verification) lands in A2/B.
