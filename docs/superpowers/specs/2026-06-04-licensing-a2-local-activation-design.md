# Licensing overhaul — A2: Local-Server Activation Hardening — design

## Goal

Make the clinic's **desktop server the local license authority** and close the trust holes
in local activation. Today `POST /api/license/activate` believes whatever JSON the caller
sends — serial, `max_devices`, plan, and (via a re-activation quirk) an arbitrarily generous
expiry window. A2 makes the desktop:

1. **Verify the vendor Ed25519 signature** on the serial before trusting any of its fields,
2. take `max_devices` / `expires_at` / `grace_until` / `plan_name` **only from the signed
   token (or the cloud's authoritative answer)** — never from client JSON,
3. **call the A1 cloud authority** (`POST /api/license/validate`) once to claim the device
   slot and learn the real subscription state, then **cache** that into the local
   `licenses` / `license_devices` tables,
4. **fall back to the signed token offline** ("online once, then offline"), and
5. **enforce device membership** on `/login` and `/status` so a stranger who only knows the
   serial string can't mint a working offline token over the LAN.

A2 turns the local `licenses` / `license_devices` tables from *self-asserted truth* into a
**cache of cloud truth**, with the vendor-signed token as the offline fallback authority.

## Initiative context

Second of the five licensing sub-projects (see
`docs/superpowers/specs/2026-06-03-licensing-a1-cloud-authority-design.md` for the full map).
A1 (shipped, PR #3) built the cloud authority + Ed25519 serial format + `/api/license/validate`.
A2 is the **client side of A1**: until A2 lands, nothing calls the cloud authority, so A1's
enforcement is dormant. Build order: **A1 ✅ → A2 (this) → A3 → B → C**, D slots in for the GUI.

### Locked decisions carried into A2

- **Desktop is the authority; mobile derives over LAN.** The clinic's desktop server calls the
  cloud, holds the license state, and consumes the cloud device slot. Phones do **not** each
  call the cloud — they enrol with their local desktop over the LAN, and the desktop vouches
  for them. (Confirmed by the user, 2026-06-03.)
- **Online once, then offline.** First activation needs the internet to claim the slot and
  learn subscription state; afterwards the vendor-signed token is a sufficient offline
  authority. The product never locks for *being offline* — only for *expiry/revocation* learned
  on the next online contact (the UX for that degrade is A3).
- **Asymmetric Ed25519.** The desktop ships the **public** key (baked in) and can only verify,
  never mint. The private seed stays on the vendor machine.
- **A2 fully now, then sequence** the remaining sub-projects. (Confirmed by the user.)

## Existing mechanics (build on, do not break)

- **`POST /api/license/activate`** (`dental_clinic.py:4733`) — local, not cloud-guarded. Reads
  `serial_number`, `clinic_name`, `device_id`, `device_name`, `max_devices`, `plan_name` from
  JSON; computes `expires_at` from `DEFAULT_LICENSE_DAYS`; on re-activation **reuses the stored
  window** (`existing[3] or expires_at`, lines 4773–4774 — the grace-date bypass). Binds the
  device in `license_devices` under the client-supplied `max_devices`. Issues a **local HMAC**
  offline token via `serialize_offline_license`.
- **`POST /api/license/login`** (`:4848`) — looks up the serial, checks
  `evaluate_license_window`, returns a fresh offline token + download links. **No device
  membership check** — any caller who knows the serial gets a token.
- **`GET /api/license/status`** (`:4968`) — reads `active_serial_number`, returns the window +
  `active_devices` count. **No device membership check.**
- **`POST /api/license/offline-verify`** (`:4898`) — verifies the local HMAC offline token;
  optional `device_id` match. Stays HMAC (per-server key) — that is correct and unchanged.
- **A1 verification primitives (reuse verbatim):**
  - `_decode_signed_serial_token(token)` (`:255`) → `(payload|None, reason)`; Ed25519-verifies
    a vendor token. Single source of truth for signature checks.
  - `_serial_public_key()` (`:241`) → `Ed25519PublicKey | None` from `_SERIAL_PUBLIC_KEY_B64`
    (`:234`, env `CLINIC_SERIAL_PUBLIC_KEY`).
  - `_cloud_http_request(method, url, headers, body, timeout)` (`:6010`) — stdlib JSON HTTP;
    returns `(status, body)`, never raises on HTTP errors (only on a real connection failure).
  - `_cloud_sync_config()` (`:6029`) → `(url, token, interval)` — the paired cloud URL.
- **Local schema** (`init_database`, `:960`/`:975`): `licenses(serial_number PK, clinic_name,
  plan_name, status, max_devices, expires_at, grace_until, …)` and
  `license_devices(serial_number, device_id, device_name, is_active, UNIQUE(serial_number,
  device_id))`.
- **Helpers:** `evaluate_license_window` (`:1666`), `fetch_license_record` (`:1687`),
  `get_or_create_license_signing_key`/`serialize_offline_license`/`build_offline_license_payload`
  (`:523`–`:572`), `read_app_setting`/`write_app_setting` (`:507`/`:515`).

## A2 scope

**In:**

1. **Baked-in public key** so the desktop can verify vendor signatures with no env setup.
2. **Reworked `/api/license/activate`** — signature-gated, token-sourced fields, server-derived
   fingerprint, cloud-validate-then-cache, offline token fallback, grace-bypass fix, and a
   backward-compatible **LAN-attach** path for phones.
3. **Device-membership enforcement** on `/login` and `/status`.
4. **Backend test suite** `tests/test_license_activation_a2.py`.

**Out (later layers):**
- First-run online-gate UX, renewal prompts, view-only degrade on expiry/revocation — **A3**.
- Baked **cloud URL** + one-tap onboarding (no URL typing) — **B** (A2 reuses the *paired* URL
  or an env override; it does not invent the zero-config URL story).
- Toggle-only sync — **C**. Admin GUI — **D**.
- Dart-side offline signature verification in the Flutter app — **not needed**: mobile derives
  state from the desktop over the LAN, so the desktop is the only verifier in A2/B.

## Design

### 1. Baked-in public key

`_SERIAL_PUBLIC_KEY_B64` becomes `env CLINIC_SERIAL_PUBLIC_KEY → _BAKED_SERIAL_PUBLIC_KEY`,
where `_BAKED_SERIAL_PUBLIC_KEY` is the **real vendor public key** (base64, 32 bytes) committed
in source. This is safe: the public key verifies but cannot mint. On the cloud the env var is
set explicitly and still wins; on the desktop the baked constant is used. Tests monkeypatch
`_SERIAL_PUBLIC_KEY_B64` exactly as the A1 suite already does, so no test plumbing changes.

### 2. Reworked `POST /api/license/activate`

The endpoint now branches on whether a verifiable `serial_token` is present.

**Request (primary activation — desktop):**
`{ "serial_token": "<v2 token>", "device_name": "<optional>" }`

**Request (LAN attach — phone, no token):**
`{ "serial_number": "...", "device_id": "<phone fp>", "device_name": "<optional>" }`

**Algorithm:**

1. **If `serial_token` present → primary activation.**
   1. `payload, why = _decode_signed_serial_token(serial_token)`. If `payload is None` →
      `403 {error, reason}` (`why` ∈ `missing|no_key|malformed|bad_signature`). **A forged or
      unsigned token never gets past here** — the "no random serials" guarantee, locally.
   2. Pull **only from the verified payload**: `serial`, `clinic_name`, `plan_name`,
      `max_devices`, `expires_at`, `grace_until`. Ignore any same-named client JSON fields.
      Normalise the ISO `…Z` timestamps to the local `YYYY-MM-DD` window format the cache uses.
   3. **Server-derive the device fingerprint** for *this desktop*:
      `fp = _get_or_create_device_fingerprint(cursor)` — a persistent random id stored once in
      `app_settings['device_fingerprint']`. The client cannot override the server's own slot.
   4. **Online validate (best-effort):** if a license cloud URL is resolvable, call
      `_validate_with_cloud(serial_token, fp, device_name)` →
      `POST {cloud}/api/license/validate`. On a network failure this returns `None` (never
      raises). On an HTTP answer:
      - `{valid:false}` → **reject** `403 {error:'License rejected by server', reason}`
        (covers `revoked`/`suspended`/`expired`/`device_cap_reached`). The cloud is authoritative
        when reachable, so a revoked serial cannot be re-activated by replaying an old token.
      - `{valid:true, status, expires_at, grace_until, plan_name?, max_devices?}` → these
        **cloud values win** over the token's (the cloud may have a renewed/shortened window).
   5. **Offline fallback:** if the cloud was unreachable (`None`), trust the **signed token's**
      window (it is vendor-signed and unforgeable). If the token itself is past `grace_until`
      → `403 {error:'License expired', reason:'expired'}`.
   6. **Write the cache** (always overwrite the window — this is the grace-bypass fix):
      `INSERT … ON CONFLICT(serial_number) DO UPDATE SET clinic_name, plan_name, status,
      max_devices, expires_at, grace_until, updated_at` using the authoritative
      (cloud-or-token) values. **Never** reuse `existing.expires_at`/`grace_until` and **never**
      derive the window from `DEFAULT_LICENSE_DAYS` for a signed activation.
   7. Bind the server's `fp` in `license_devices` (idempotent upsert), set
      `active_serial_number`, audit-log, and issue a local HMAC offline token bound to `fp`.

2. **Else (no token) → LAN attach.**
   1. Require an **already-activated** local license for `serial_number`
      (`fetch_license_record`); none → `403 {error:'Activate on the clinic server first'}`. A
      phone cannot bootstrap a license on its own — it joins one the desktop already proved.
   2. Require a non-empty `device_id`; `evaluate_license_window` must be `licensed` (not
      expired/revoked in the cache) else `403`.
   3. Enforce the **cached `max_devices`** (from the signed token, not client JSON): if the
      device isn't already a member and active members ≥ `max_devices` →
      `403 {error:'Max active devices reached (N)'}`.
   4. Upsert the device in `license_devices`, audit-log, issue an HMAC offline token bound to
      that `device_id`.

The legacy `max_devices` / `expires_at` / `plan_name` client JSON fields are **dropped** from
the trusted path. (For one release the LAN-attach branch still accepts a client `device_id`,
because that *is* the phone's identity — but it never sets the window or the cap.)

### 3. Device-membership rule on `/login` and `/status`

> **Rule:** a request that carries a non-empty `device_id` must correspond to an **active member**
> of the active serial. A request with **no** `device_id` is treated as the local authority
> (the desktop's own portal on the host machine) and answered from license state directly.

- **`POST /api/license/login`** — read `device_id` from the body. If present and not an active
  member of `serial_number` → `403 {error:'Device not enrolled', reason:'device_not_recognized'}`.
  Members (and tokenless desktop calls) proceed exactly as today.
- **`GET /api/license/status`** — read `device_id` from the query string. If present and not an
  active member of the active serial → `{licensed:false, reason:'device_not_recognized'}`.
  Tokenless calls (desktop portal) answer from license state unchanged.

This is what makes "mobile derives over LAN" real: a phone is licensed **iff** the desktop
enrolled it; the serial string alone is not a credential.

## New helpers (all in `dental_clinic.py`)

- `_get_or_create_device_fingerprint(cursor)` → `str`. Reads `app_settings['device_fingerprint']`;
  if empty, generates `secrets.token_hex(16)`, persists it, returns it. Stable across restarts,
  server-owned, client-unforgeable.
- `_license_cloud_url()` → `str | None`. Resolves the license-validate base URL:
  `env CLINIC_LICENSE_CLOUD_URL` → `_cloud_sync_config()[0]` (the paired URL) → `None`.
  (Sub-project B adds a baked default; A2 stays explicit.)
- `_validate_with_cloud(serial_token, fingerprint, device_name='')` → `dict | None`. Resolves the
  URL, POSTs to `/api/license/validate` via `_cloud_http_request`, returns the parsed body, or
  `None` if no URL is configured **or** the network call fails (caught — never raises). This is
  the single seam the tests stub to simulate online/offline/revoked cloud answers.
- `_iso_to_window_date(value)` → `str`. Normalises a token `…Z` ISO timestamp to the
  `YYYY-MM-DD` form the local cache stores (so `evaluate_license_window` keeps working).

## Error handling

- Signature / expiry / cap failures are **business outcomes** → `403` (activation) or
  `{licensed:false, reason}` (status), never `500`. Matches the public-API no-500 contract
  (`tests/test_api_fuzz.py`).
- `_validate_with_cloud` swallows `URLError`/timeout/parse errors and returns `None` so a flaky
  network degrades to the offline-token path, not a crash.
- No SQL / path / exception text leaks in responses (consistent with the cloud hardening in
  `c7bfaec`).

## Security notes (set expectations)

- **A2 stops:** locally forged/altered serials (signature gate), client-inflated `max_devices`
  or expiry (token/cloud-sourced now), the grace-date bypass (window always re-written from the
  authority), and strangers minting tokens off a known serial string (membership gate).
- **A2 cannot stop** (offline-first reality, per the A1 security review): an attacker with full
  OS access on the desktop can extract the local HMAC key, patch the binary, or set the clock
  back. A2 + A1 raise the bar to "casual piracy impossible," not "uncrackable." The baked
  **public** key is not a secret — leaking it does nothing; only the vendor **private** seed
  could mint, and it never ships.

## Test plan (A2 — backend `pytest`, new suite `tests/test_license_activation_a2.py`)

Fixtures mirror the A1 suite: generate an Ed25519 keypair, monkeypatch `_SERIAL_PUBLIC_KEY_B64`
to the public key, use a temp DB in **local** (non-cloud) mode, and stub `_validate_with_cloud`
to simulate the cloud.

- **Signature gate:** unsigned/forged/tampered `serial_token` → `403` with the right `reason`;
  a validly-signed token → `200`.
- **Field sourcing:** a token with `max_devices=5` but client JSON `max_devices=99` → the cached
  license has `max_devices=5` (client value ignored).
- **Grace-bypass fix:** activate with a token whose window is `expires=+10d`; re-activate with a
  token whose window is `expires=+400d` → cached window is the **new** one; a re-activation that
  *omits* a fresher window never resurrects a stale generous window.
- **Cloud authoritative when reachable:** stub cloud → `{valid:false, reason:'revoked'}` →
  activation `403`; stub → `{valid:true, status:'active', expires_at:<later>}` → cache reflects
  the cloud window, not the token's.
- **Offline fallback:** stub `_validate_with_cloud` → `None` (network down) → activation succeeds
  off the signed token; a token already past grace → `403 expired` even offline.
- **Device cap (LAN attach):** activate desktop (token, cap 2) → consumes slot 1; attach phone
  `d2` → ok; attach phone `d3` → `403 Max active devices reached`.
- **LAN attach requires prior activation:** attach with a serial that was never activated →
  `403 Activate on the clinic server first`.
- **Membership on `/login`:** enrolled `device_id` → `200` + token; unknown `device_id` →
  `403 device_not_recognized`; no `device_id` (desktop) → `200`.
- **Membership on `/status`:** `?device_id=<enrolled>` → `licensed:true`; `?device_id=<stranger>`
  → `licensed:false, reason:'device_not_recognized'`; no param (desktop) → answers from state.
- **Server-derived fingerprint:** two activations on the same DB reuse one
  `app_settings['device_fingerprint']`; a client-supplied `device_id` never overrides the
  desktop's own slot.
- **No-500 fuzz:** malformed/oversized bodies → `400/403`, never `500`.

## Dependencies

None new — reuses A1's `cryptography` (Ed25519) and stdlib `urllib`. No Dart/Flutter change in
A2 (mobile derives over LAN; the Dart client work is B).

## Deferred / open (resolved later, flagged so they aren't lost)

- **Baked cloud URL / zero-config onboarding** → B. A2 needs a configured (paired or env) URL to
  validate online; with none, it activates straight off the signed token (still secure, just no
  slot claim until the URL is set).
- **Periodic re-validation cadence** (re-checking the cloud after first run to learn
  revocation/expiry) → A3, which owns the online-gate + view-only degrade UX. A2 makes the call
  reusable; A3 schedules it.
- **Multi-desktop clinics** (several servers under one serial) are handled naturally: each
  desktop has its own `device_fingerprint` and consumes one cloud slot under the serial's cap.
