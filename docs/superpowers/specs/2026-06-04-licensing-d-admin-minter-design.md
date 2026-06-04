# Licensing overhaul — D: Admin Serial-Minting GUI — design

## Goal

Give the vendor a **responsive, friendly GUI** to mint Ed25519-signed serials — the pretty face
over today's `serial_generator.py` CLI — **without the private seed ever leaving the vendor
machine**. Fill in a clinic, pick a plan/expiry/device-cap, click **Mint**, get the serial +
signed token, copy or download as CSV/JSON. Generate the vendor keypair from the same screen and
copy the **public** key for baking into the build/cloud.

D is operator convenience around A1's signing core. It changes **no** token format and **no**
verification logic — it only wraps `serial_generator.py`'s existing functions in a UI.

## Initiative context

The standalone tool in the five-part overhaul (map in
`docs/superpowers/specs/2026-06-03-licensing-a1-cloud-authority-design.md`). It slots in **after**
A1 (which built the Ed25519 signer) whenever the CLI needs a GUI; it has no ordering dependency on
A2/A3/B/C. The existing `serial_generator.py` CLI covers minting in the meantime.

### Locked decisions carried into D

- **The private seed is the crown jewel — it never leaves the vendor machine.** (A1 security note;
  reinforced in memory.) Therefore D is a **local, vendor-side** app bound to **loopback only** —
  never the cloud node, never the clinic server, never `0.0.0.0`.
- **Public keys verify but cannot mint.** The GUI may *display* the public key (to copy into the
  build/cloud env); it must **never** display, log, or transmit the private seed.
- **Reuse the signer; don't reinvent it.** D imports `serial_generator.py` — no duplicated crypto.

## Existing mechanics (build on, do not break)

`serial_generator.py` public API (all reused verbatim):

- `generate_keypair() -> (priv_b64, pub_b64)` (`:32`) — new vendor keypair.
- `load_private_seed(key_file) -> str` (`:162`) — reads the base64 seed from
  `backend_ed25519_key.json` (`{"alg":"ed25519","private":"<b64>"}`); fails loudly if missing.
- `generate_device_serial_number(clinic_code, device_id, counter) -> serial` (`:78`) — the
  `DENTAL-CODE-DEV-NNNNN` format.
- `generate_license_token(serial, clinic_name, device_id, plan_name, max_devices, expiry_days,
  private_seed_b64) -> {serial, offline_token, payload, issued_at, expires_at}` (`:104`) — the v2
  signed token the cloud's `/api/license/validate` reads. **Requires** the private seed (no demo
  fallback).
- `sign_serial_token(payload, private_seed_b64) -> token` (`:47`) and
  `verify_serial_token(token, public_key_b64) -> (ok, payload)` (`:55`) — the round-trip primitives
  (the tests use `verify_serial_token` to prove minted tokens are valid).
- `create_serial_batch(...)` (`:175`) — the CLI batch path; D's batch mint mirrors its loop but
  returns JSON instead of writing a CSV server-side.

The `--genkey` subcommand + `backend_ed25519_key.json` (gitignored) already exist; D's "Generate
keypair" button is a GUI wrapper over `generate_keypair()` + the same file write.

## D scope

**In:** a new **standalone localhost Flask app `serial_admin.py`** (separate process from
`dental_clinic.py`) that:

1. Serves a **responsive single-page operator console** at `/` (loopback only).
2. `GET /api/key/status` → `{has_key, public_key}` — **public key only**, never the seed.
3. `POST /api/key/generate` → create a keypair, write the key file (refuses to clobber an existing
   key without an explicit confirm), return the **public** key to copy.
4. `POST /api/mint` → mint one or many signed serials from a clinic + device list; returns JSON
   records. Optional `?format=csv` streams a CSV attachment.
5. A hard **loopback bind + guard** so the seed-bearing process is never reachable off-machine.
6. Tests (`tests/test_serial_admin_d.py`) + a template/JS sweep.

**Out:** changing the token format/signer; any cloud or clinic-app change; multi-user auth /
roles (single trusted operator on their own machine — a proper admin-auth model was explicitly
deferred to "later" in A1); persistent minting history/DB (the vendor saves the CSV/JSON they
download). Packaging D into the shipped clinic installer (it is vendor-internal, distributed
separately).

## Architecture

`serial_admin.py` — a small Flask app, **distinct from** `dental_clinic.py`:

```text
serial_admin.py
  ├─ imports serial_generator  (the signer — DRY)
  ├─ KEY_FILE = env CLINIC_VENDOR_KEY_FILE or 'backend_ed25519_key.json'
  ├─ binds 127.0.0.1 only (run(host='127.0.0.1', port=8787))
  ├─ before_request: 403 unless request.remote_addr is loopback
  └─ routes: / , /api/key/status , /api/key/generate , /api/mint
```

The private seed is read **server-side** inside the process (via `load_private_seed`) only at the
moment of minting; it is never put in a response body, a log line, or the rendered HTML.

### `GET /api/key/status`

```json
{ "has_key": true, "public_key": "<base64>", "key_file": "backend_ed25519_key.json" }
```

`public_key` is derived from the stored seed (load seed → `Ed25519PrivateKey` →
`public_key().public_bytes` → base64) so the operator can copy it for `CLINIC_SERIAL_PUBLIC_KEY` /
the baked constant. If no key file: `{ "has_key": false }`.

### `POST /api/key/generate`

Body `{ "confirm_overwrite": false }`. If a key file already exists and `confirm_overwrite` is not
`true` → `409 { error:"A key already exists", reason:"exists" }` (guards the crown jewel against an
accidental clobber, which would invalidate every serial in the field). Otherwise call
`generate_keypair()`, write `{"alg":"ed25519","private":"<priv>"}` to `KEY_FILE` (0600 perms where
supported), and return `{ "public_key":"<pub>" }`. **The private seed is never returned.**

### `POST /api/mint`

Request:

```json
{ "clinic_name":"Smile Dental", "clinic_code":"SMD", "plan_name":"Standard",
  "expiry_days":365, "max_devices":3, "devices":["LAPTOP-01","PHONE-02"] }
```

- `devices` may be one or many; an empty/blank list mints a single non-device-locked serial using a
  generated device id (so a clinic-level serial is possible).
- For each device: `serial = generate_device_serial_number(code, device, idx)`, then
  `generate_license_token(serial, clinic_name, device, plan_name, max_devices, expiry_days,
  private_seed_b64)`.
- Response: `{ "records":[ {serial, offline_token, expires_at, issued_at, plan_name, max_devices,
  device_id} … ] }`.
- `?format=csv` → the same data as a `text/csv` attachment (`serials_<code>_<date>.csv`) built
  in-memory (no server-side temp file holding tokens).

Errors: missing key file → `400 { error:"No signing key — generate one first", reason:"no_key" }`;
`clinic_code` > 4 chars / missing `clinic_name` → `400` with the field message; never `500` on bad
input.

## Frontend (responsive operator console)

A single deliberate, dark "operator console" page (not a default template) served from `/`:

- A **key panel**: shows `has_key`, the public key (copy button), and a "Generate keypair" action
  (with an overwrite confirm dialog). When no key exists, the mint form is disabled with a clear
  "Generate a signing key first" hint.
- A **mint form**: clinic name, clinic code (maxlength 4), plan select, expiry (days), max devices,
  and a devices textarea (one id per line; blank = one clinic-level serial). **Mint** button.
- A **results table**: serial, expires, and the token (truncated, with copy-full and a per-row
  copy). **Download CSV** / **Download JSON** buttons build the file client-side from the response.
- Responsive: the form is a single column on narrow screens, two columns ≥ 720px; the results
  table scrolls horizontally on mobile. Uses CSS custom properties for the palette; no external
  assets.

**JS-escaping caveat:** the page is its own template string — apply the same double-escape rule and
`node --check` sweep used elsewhere (a literal `'\n'` in inline JS breaks the script).

## Security notes (set expectations)

- **Loopback-only** bind + a `before_request` guard rejecting non-loopback `remote_addr` keep the
  seed-bearing process off the network. The operator runs it on their own machine.
- The **private seed is never** in a response, log, or the DOM. Only the public key is shown.
- Minted CSV/JSON contain **real signed tokens** — the UI warns "treat downloads as secrets; don't
  commit them" (matching the gitignore policy for `*.csv`/serial outputs).
- D adds no new attack surface to the clinic app or cloud — it is a separate vendor tool.

## Test plan (D — `tests/test_serial_admin_d.py`)

Fixture: a temp `KEY_FILE` written from `generate_keypair()`; `serial_admin` app test client with
`CLINIC_VENDOR_KEY_FILE` pointed at it.

- **Key status:** with a key → `{has_key:true, public_key:<b64>}` and the public key **matches** the
  temp keypair; the response body contains **no** `"private"` substring (seed never leaks).
- **Generate guard:** `POST /api/key/generate` when a key exists → `409 exists`; with
  `confirm_overwrite:true` → `200` + a new public key; the response never contains the seed.
- **Mint single:** `POST /api/mint` with one device → one record whose `offline_token`
  `verify_serial_token(token, public_key)` returns `(True, payload)` with the right `serial`,
  `max_devices`, `plan_name`.
- **Mint batch:** three devices → three records with distinct serials, all verifying.
- **Mint clinic-level:** empty `devices` → one record (verifies).
- **No key:** point `KEY_FILE` at a missing path → `POST /api/mint` → `400 no_key` (never 500).
- **CSV:** `POST /api/mint?format=csv` → `text/csv` attachment with a header row + one row per
  device; tokens present.
- **Loopback guard:** a request with a non-loopback `REMOTE_ADDR` (via `environ_overrides`) → `403`.
- **No-500 fuzz:** malformed/oversized bodies → `400`, never `500`.

Frontend (`tests/test_serial_admin_ui_d.py`): the rendered page contains the key panel id, the mint
form id, and a `fetch('/api/mint'` call; `node --check` JS sweep passes.

## Dependencies

None new — reuses `serial_generator.py` (`cryptography` Ed25519) and Flask (already a dependency).
`serial_admin.py` is a separate entry point; it is **not** bundled into the shipped clinic
installer (`DentaCare.spec` is unchanged) — the vendor runs it from source on their machine.

## Deferred / open

- **Proper admin authentication / multi-operator roles** — out of scope (single trusted operator on
  loopback). If D is ever exposed beyond localhost, an auth model becomes mandatory first.
- **Minting history / audit DB** — the vendor keeps the downloaded CSV/JSON; a persistent ledger is
  a possible future addition.
- **Revoke/suspend from the GUI** — that is the cloud admin endpoint (`/api/license/admin/revoke`,
  A1); a future D iteration could add a panel calling it with `CLINIC_ADMIN_API_TOKEN`, but the
  minting tool deliberately stays separate from the live revocation control for now.
