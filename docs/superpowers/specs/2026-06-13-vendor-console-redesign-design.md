# Vendor Console Redesign — design spec (2026-06-13)

Premium redesign of the serial/license vendor console (`serial_admin.py`) — the
loopback-only tool a vendor runs to mint Ed25519-signed serials and publish them
to the cloud registry. Supersedes the UI of
[`2026-06-04-licensing-d-admin-minter-design.md`](2026-06-04-licensing-d-admin-minter-design.md);
the minting/crypto backend is unchanged in spirit, only consolidated and extended.

## Problem

The current console works but is **confusing and looks unfinished**, and a real
workflow bug makes it feel broken:

1. **Two cloud connections.** The cloud URL + admin token are entered in *two*
   separate panels (Results "Publish to cloud" and the bottom "Publish an existing
   serial"). The per-row **Publish** button in history silently reads the *bottom*
   panel's token, so it errors ("admin token required") when you filled the other
   box. This is the single biggest "it's not working" trap.
2. **No guided flow.** Five stacked panels with no sense of order (mint → publish →
   verify). Terse, technical labels.
3. **Raw `alert()`** for every error/success; no inline status, no loading or empty
   states, no connection health indicator.
4. **No license management.** No search/filter, no status at a glance, no
   revoke/suspend, no device-usage view — table stakes for a licensing console.

## Goals

- A premium, legible **enterprise-light console with sidebar nav** that a serious
  software vendor would ship (reference patterns: Keygen.sh, Cryptolens, Stripe/
  Linear admin UIs).
- **One** cloud connection, set once, reused everywhere.
- Full **license management**: unified searchable list (local ledger ⨝ live cloud
  registry), status badges, device usage, publish, and revoke/suspend/re-activate.
- Keep the proven backend (Ed25519 minting, loopback-only, private seed never
  leaves the machine, local mint ledger).

## Non-goals

- No framework / build step (stays vanilla JS + a single Flask app).
- No change to the serial/token crypto or the cloud's admin endpoints.
- **Per-device slot "release"** is deferred (see Open items).

## Architecture

Single self-contained **Flask app**, **loopback-only** (`127.0.0.1`, the existing
`_loopback_only` before_request guard stays), default port 8787. No new heavy deps
(Flask + `cryptography` + stdlib only).

The frontend is a small **vanilla-JS SPA** (no framework) with a client-side view
router. Because the premium template is large, the HTML/CSS/JS string moves out of
`serial_admin.py` into a new **`serial_admin_ui.py`** (`INDEX_TEMPLATE = r'''...'''`),
keeping `serial_admin.py` a focused routes/logic file (target < 500 lines) and the
UI file isolated and independently editable.

```
serial_admin.py        Flask routes, mint logic, ledger, cloud proxies, settings
serial_admin_ui.py     INDEX_TEMPLATE (HTML + CSS + JS) — the SPA
serial_generator.py    (unchanged) keypair + serial/token generation
minted_serials.db      (unchanged) local mint ledger, next to the signing key
console_settings.json  NEW — persisted connection settings (0600), next to the key
```

### Module boundaries

- `serial_admin.py` — owns all HTTP routes, the mint ledger helpers, cloud HTTP
  proxies, and settings persistence. Depends on `serial_generator` and
  `serial_admin_ui` (for the template string only).
- `serial_admin_ui.py` — owns *only* the `INDEX_TEMPLATE` string. No logic, no
  imports from `serial_admin` (avoids a cycle). Can be edited/visually reviewed
  without touching routes.

## Cloud connection model (fixes the core confusion)

A single in-memory JS object `conn = { cloud_url, admin_token }`, established in
**Settings**, reused by every cloud action (publish, view registry, revoke, ping).

- **Default:** session-only. Held in JS memory; nothing written to disk.
- **Opt-in "Remember on this machine":** a checkbox in Settings. When checked,
  `POST /api/settings` writes `{cloud_url, admin_token, remember:true}` to
  `console_settings.json` with `0600` perms next to the signing key (same trust
  level as the seed on a dedicated vendor PC). When unchecked, the file stores
  `{cloud_url, remember:false}` **without** the token, and any previously saved
  token is removed.
- On boot, `GET /api/settings` returns the saved `cloud_url`, `remember`, and the
  `admin_token` **only if** it was remembered, so the SPA rehydrates the connection.
- The admin token input is a `type=password` field; the token is **never logged**
  and never echoed into the page outside that field.

## Backend API

### Existing (kept, unchanged behavior)

| Route | Method | Purpose |
|---|---|---|
| `/api/key/status` | GET | Signing-key presence + public key |
| `/api/key/generate` | POST | Generate/rotate keypair (`confirm_overwrite`) |
| `/api/mint` | POST | Mint signed serials (`?format=csv` for download) |
| `/api/history` | GET | Local mint ledger (incl. activation codes, `published`) |
| `/api/upload-cloud` | POST | Publish a batch of just-minted records |
| `/api/publish-token` | POST | Publish one pasted Activation Code |
| `/api/cloud/serials` | POST | Proxy cloud `GET /api/license/admin/serials` |

### New

**`GET /api/settings`** → `{cloud_url, remember, admin_token?}`
Reads `console_settings.json`. `admin_token` present only when `remember` is true.
Loopback-only. Missing/unreadable file → `{cloud_url:"https://app.dentacare.tech", remember:false}`.

**`POST /api/settings`** → `{success:true}`
Body `{cloud_url, admin_token, remember}`. When `remember` is true, persists all
three at `0600`; when false, persists `{cloud_url, remember:false}` only and drops
any saved token. Best-effort write (never 500s on a read-only profile; returns
`{success:false, error}` instead).

**`POST /api/cloud/ping`** → `{reachable:bool, authorized:bool, count?:int, error?}`
Body `{cloud_url, admin_token}`. Calls the cloud's `GET /api/license/admin/serials`:
- network/DNS failure → `reachable:false`
- HTTP 401 → `reachable:true, authorized:false`
- HTTP 200 → `reachable:true, authorized:true, count:<n>`
Used by the Settings "Test connection" button and the sidebar Cloud status dot.

**`POST /api/cloud/revoke`** → `{success:bool, error?}`
Body `{cloud_url, admin_token, serial, status}` where `status ∈ {active,revoked,
suspended}`. Proxies the cloud `POST /api/license/admin/revoke`. Maps cloud 401 →
`{success:false, error:"admin token rejected"}`, other non-200 → surfaced error.

### Cloud endpoints consumed (already deployed, no redeploy needed)

- `GET  /api/license/admin/serials` → `{serials:[{serial,status,plan_name,clinic_name,max_devices,used_devices,has_token,issued_at,expires_at,grace_until,created_at,updated_at}], count}`
- `POST /api/license/admin/register-serial` → `{serial_token}` (publish)
- `POST /api/license/admin/revoke` → `{serial,status}` (status change) or `{serial,release:true,device_fingerprint}` (deferred)

## Frontend — views

Shell: fixed **left sidebar** (brand, nav: Dashboard / Issue / Licenses / Settings,
footer status dots Key ● + Cloud ●) + scrollable main content. Client-side router
swaps the active view; no full reloads.

### Dashboard
- Stat cards from the local ledger (`/api/history`): **Issued**, **Published**,
  **Local-only**. Key status card (loaded / none). Cloud status card (from ping).
- **Recent serials** (latest 5 from the ledger) with status.
- Quick-action buttons: **Issue serials**, **View licenses**.
- Empty state when no serials minted yet ("Mint your first serial").

### Issue (guided mint)
- Form: Clinic name, Clinic code (≤4), Plan (Standard/Premium/Enterprise), Expiry
  (days), Max devices, Device IDs (one per line; blank = one clinic-level serial).
  Inline validation (name required, code 1–4 chars, numbers numeric).
- On mint (`POST /api/mint`): a **Results** card lists each serial with **Copy
  serial number**, **Copy activation code**, expiry. Buttons: Download CSV, Download
  JSON, and **Publish all to cloud** (`POST /api/upload-cloud` using `conn`). If not
  connected, the publish button routes to Settings with a toast.
- Guidance line: "Give the clinic owner the **Serial Number** — they type it in the
  app to activate online. The full Activation Code is the offline fallback."

### Licenses (the management view)
- Data = **local ledger** (`/api/history`) **left-joined with the live cloud
  registry** (`/api/cloud/serials`, when connected) on `serial`. A serial may be:
  local-only, published (in cloud), or cloud-only (registered elsewhere).
- Table columns: **Serial** (mono) · **Clinic** · **Plan** · **Status** badge
  (active / revoked / suspended / expired-by-date / local-only) · **Devices**
  `used/max` with a mini progress bar · **Short-serial ready** (`has_token` ✓) ·
  **Expiry** · **Source** (local / cloud / both).
- Controls: text **search** (serial/clinic) + **filter chips** (All / Published /
  Local-only / Active / Revoked / Suspended / Expired).
- Row actions (overflow menu): **Copy Code**, **Publish** (local-only → register-
  serial), **Revoke** / **Suspend** / **Re-activate** (cloud status via
  `/api/cloud/revoke`; confirm dialog for revoke/suspend), **Details** drawer
  (full metadata, issued/expires/grace, device count).
- Cloud-dependent actions are disabled with a hint when not connected.

### Settings
- **Signing key**: status, public key (mono, copy), **Generate keypair** /
  **Rotate keypair** (rotate requires a typed confirm — invalidates all issued
  serials). Existing warning retained.
- **Cloud connection**: Cloud URL, Admin token (`password`), **Remember on this
  machine** checkbox, **Test connection** button (calls `/api/cloud/ping`, shows
  reachable/authorized + serial count). Save persists via `/api/settings`.
- **Security notes**: private seed never leaves the machine; activation codes are
  secrets; settings file is `0600` and gitignored.

## Visual design system (enterprise light)

CSS custom properties; no hardcoded repeats. Light surface, neutral slate text,
one teal accent matching the product brand (`--brand:#0f6d7b`, `--accent:#13b5a7`).

```
--bg:#f6f8fb  --surface:#ffffff  --line:#e3e9f0  --ink:#16212e  --muted:#64748b
--brand:#0f6d7b  --accent:#13b5a7  --ok:#1f9d6b  --warn:#c2410c  --danger:#dc2626
--radius:12px  --shadow:0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10)
```

- **Sidebar**: 230px, surface, nav items with active state; footer status dots.
- **Status badges**: pill, color-coded (active=ok, revoked=danger, suspended=warn,
  expired=muted, local-only=neutral, published=accent).
- **Tables**: dense rows, sticky header, hover row, mono serials, copy affordance.
- **Buttons**: primary (brand fill), secondary (outline), danger (for revoke).
- **Toasts**: bottom-right, auto-dismiss, success/error variants — replace `alert()`.
- Responsive: sidebar collapses to a top bar under 760px; tables scroll-x.
- All inline `<script>` uses double-escaped newlines / no bare `\n` literals
  (templates.py escaping trap), verified by a `node --check` render sweep.

## Error handling & states

- Every fetch wrapped; failures → a toast + inline message, never a thrown
  uncaught error.
- Loading states on async actions (button spinner / skeleton rows).
- Empty states for Dashboard (no serials) and Licenses (no results / not connected).
- Connection guard: cloud actions check `conn.admin_token`; if missing, toast +
  jump to Settings instead of a silent 400.
- Validation messages inline under fields.

## Security

- **Loopback-only** before_request guard retained (rejects non-`127.0.0.1`).
- Private seed read server-side at mint time, **never** returned/logged/rendered.
- Admin token: `password` input; session-memory by default; persisted only on
  opt-in Remember to a `0600` `console_settings.json`; never logged.
- `console_settings.json` and `minted_serials.db` added to `.gitignore`.
- Activation codes shown truncated with copy; "these are secrets" warnings kept.

## Testing

Extend the existing suites (`tests/test_serial_admin_d.py`,
`tests/test_serial_mint_ledger.py`, `tests/test_license_admin_serials.py`):

- **Settings**: `POST /api/settings` with `remember:true` writes all three + file is
  `0600`; `remember:false` omits/strips the token; `GET` returns the token only when
  remembered; unreadable file → defaults.
- **`/api/cloud/ping`**: maps reachable / 401-unauthorized / 200-authorized (mock
  the cloud HTTP via a stub like the existing upload tests).
- **`/api/cloud/revoke`**: success path + 401 mapping + missing-field 400.
- **Loopback guard** still 403s a non-loopback client across the new routes.
- **Regression**: mint, ledger upsert/publish flags, publish-token, cloud/serials
  proxy unchanged.
- **HTML sanity**: render `INDEX_TEMPLATE` + `node --check` the extracted inline
  script (catches the escaping trap).

Goal: full `pytest` suite stays green; ~12–16 new tests.

## File structure / size

- `serial_admin.py` shrinks (template extracted) → routes/logic, < 500 lines.
- `serial_admin_ui.py` new, holds the template (largest file; pure markup/CSS/JS).
- `.gitignore` += `console_settings.json`.

## Open items / deferred

- **Per-device slot release.** The cloud revoke endpoint supports
  `{release:true, device_fingerprint}`, but the serials list does not expose
  per-device fingerprints, so the console can't enumerate them. Deferred; would
  need a small new cloud endpoint (`GET /api/license/admin/devices?serial=`) + a
  redeploy. Status revoke/suspend/activate covers the practical need now.
- **Live cloud counts on Dashboard** beyond the ping count are out of scope for v1.
```
