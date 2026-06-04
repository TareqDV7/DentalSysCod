# Licensing overhaul — A3: First-Run Gate UX + Renewal + Advisory Revocation — design

## Goal

Turn the licensing **backend** (A1 cloud authority + A2 hardened local activation) into a
**product experience**:

1. A **first-run online gate** — a fresh desktop install shows an activation screen and the
   clinic app stays blocked until a valid serial is activated.
2. **Subscription renewal** — when the window is inside its grace period, the app keeps working
   but nudges the operator to renew (re-activate with a fresh serial token).
3. **Advisory (view-only) revocation** — when the serial is revoked or expired past grace, the
   app **degrades to read-only** instead of hard-locking: the clinic can still *see* its data
   (never held hostage) but cannot *modify* it until they renew. Enforced on the server, mirrored
   in the UI.
4. **Decoupled from cloud sync** — activating or re-validating a license must **never** turn on
   cloud sync. Licensing and sync are independent toggles.

A3 ships no new crypto and no new tables — it is the **gate + degrade + nudge** layer over the
state A2 already caches, plus a periodic re-check so revocation/expiry is *learned* without a
manual re-activation.

## Initiative context

Third of the five licensing sub-projects (map in
`docs/superpowers/specs/2026-06-03-licensing-a1-cloud-authority-design.md`). Depends on A2:
A2 makes `/api/license/activate` trustworthy and caches `licenses.status`/window as cloud truth;
A3 *reacts* to that cached state. Build order: **A1 ✅ → A2 → A3 (this) → B → C**.

### Locked decisions carried into A3

- **Online once, then offline; never lock for being offline.** The gate blocks an *unactivated*
  install and a *revoked/expired* one — never a merely-offline one. (Brainstorming, 2026-06-03.)
- **Revocation is advisory/view-only, not a hard lock.** The owner's data is never taken hostage;
  a lapsed subscription degrades to read-only. (Brainstorming, 2026-06-03.)
- **Validation is decoupled from cloud-save.** (A1 locked decision #6 — A3 is where the UX makes
  this visible: two separate switches, neither implies the other.)
- **Desktop is the authority; mobile derives over LAN.** The desktop gate is the real one; the
  mobile app reflects the desktop's `/api/license/gate` answer.

## Existing mechanics (build on, do not break)

- **Main app** is served at `/` → `index()` (`dental_clinic.py:1841`) →
  `render_template_string(HTML_TEMPLATE, **CLINIC_CONFIG)`. Today it is gated by **login only**
  (`_require_login_for_portal`, `:1766`; `_AUTH_REQUIRED_EXACT`, `:1761`) — there is **no license
  gate**. The SPA lives entirely in `templates.HTML_TEMPLATE`.
- **License state** is the cached `licenses` row read via `fetch_license_record` (`:1687`) +
  `evaluate_license_window` (`:1666`), which already yields `{licensed, in_grace, …}`.
- **`GET /api/license/status`** (`:4968`, hardened in A2) reports `{licensed, status, expires_at,
  grace_until, in_grace, …}`.
- **`POST /api/license/activate`** (A2) is the activation entry point (signed token → verify →
  cloud-validate-and-cache).
- **Cloud sync is enabled by `cloud_url` + `cloud_clinic_token`** in `app_settings`, written
  **only** by `/api/cloud/pair` (`:4445`/`:4478`). `_cloud_sync_config()` (`:6029`) reads them;
  the sync worker (`cloud_sync_worker`, `:6098`) runs only when both are set. **The license path
  (A2 `_validate_with_cloud` / `_license_cloud_url`) reads the URL but never writes these keys —
  so licensing is already decoupled at the data layer; A3 must preserve that and surface it.**
- **A2 helpers reused:** `_validate_with_cloud(serial_token, fp, name)` (the re-check seam) and
  `_license_cloud_url()` (env `CLINIC_LICENSE_CLOUD_URL` → paired URL → None).
- **Background workers** are started in the `__main__` block near the sync worker (`:6172`+);
  A3 adds a license re-check worker beside it (guarded so tests don't spawn threads).
- **Template-presence test pattern** already exists (`tests/test_expression_preservation.py:195`)
  — assert marker strings are present in `HTML_TEMPLATE`. A3's UI tasks use the same pattern plus
  a `node --check` sweep (the `templates.py` JS-escaping trap: `HTML_TEMPLATE` is a *normal*
  Python string, so a literal `'\n'` in inline JS collapses to a real newline and breaks the whole
  script — always double-escape and verify).

## A3 scope

**In:**

1. **`_license_gate_state(cursor)`** → one of `unlicensed | active | grace | view_only`, plus the
   window fields, derived from the cached license. Single source of truth for the gate.
2. **`GET /api/license/gate`** — exposes that state to the SPA and the mobile app.
3. **View-only write-guard** — a `before_request` that, when the state is `view_only`, blocks
   state-changing business API calls (`POST/PUT/PATCH/DELETE`) with `403 {reason:'view_only'}`,
   while allowing all reads and the license/auth/cloud endpoints.
4. **License re-check worker** — periodic, decoupled-from-sync background refresh that calls the
   cloud via the A2 seam and updates the cached `licenses.status`/window, so revocation/expiry is
   learned automatically. Never raises; no-ops when no license/URL.
5. **Frontend** (`templates.HTML_TEMPLATE`): first-run activation overlay (unlicensed), renewal
   banner (grace), view-only banner + control lockout (view_only).
6. **Decoupling guarantees + tests.**

**Out:** baked cloud URL / zero-typing onboarding (**B** — A3 uses env/paired URL); the
toggle-only sync collapse (**C**); admin GUI (**D**); the Flutter mobile gate screen ships in **B**
(A3 exposes `/api/license/gate`; the desktop SPA consumes it now, mobile in B).

## Gate state machine

`_license_gate_state(cursor)` reads the active serial (`active_serial_number`, else the newest
`active` license) and its cached row, then:

| Condition (from cached `licenses` row) | State | App behaviour |
| --- | --- | --- |
| No active serial / no `licenses` row | `unlicensed` | First-run activation overlay; app blocked |
| `status='active'` and `today ≤ expires_at` | `active` | Normal |
| `status='active'` and `expires_at < today ≤ grace_until` (`in_grace`) | `grace` | Normal + renewal banner |
| `status` in (`revoked`,`suspended`) **or** `today > grace_until` | `view_only` | Read-only + banner |

Response shape (`GET /api/license/gate`):

```json
{
  "state": "active|grace|view_only|unlicensed",
  "licensed": true,
  "status": "active",
  "serial_number": "DENTAL-…",
  "clinic_name": "…",
  "plan_name": "…",
  "expires_at": "2027-06-03",
  "grace_until": "2027-06-17",
  "in_grace": false
}
```

`unlicensed` returns `{state:'unlicensed', licensed:false}` with no serial. The endpoint is a
**read** and is reachable in view-only mode (it is on the write-guard allowlist).

## View-only write-guard

A new `before_request` (ordered after the existing auth gate) enforces read-only degrade:

```text
if method in (POST, PUT, PATCH, DELETE)
   and path starts with /api/
   and path NOT in the license/auth/cloud allowlist
   and _license_gate_state() == 'view_only':
       → 403 { "error": "License expired — view only. Renew to make changes.",
               "reason": "view_only" }
```

**Allowlist (always writable, even view-only):** `/api/license/*` (activate/renew/login/
offline-verify/gate/status), `/api/auth/*` (login/logout/change-password), `/api/cloud/*`
(pair/unpair/sync — so the operator can still manage connectivity), and `/healthz`. Everything
else clinical (patients, treatments, appointments, billing, expenses, …) is **read-only** until
renewal. GET/HEAD/OPTIONS are never blocked — the clinic can always *read* its data.

This is the teeth behind "advisory revocation": the friendly UI lockout (below) is convenience;
the server guard is the enforcement, so disabling JS does not bypass it.

## License re-check worker (decoupled from sync)

A periodic background job (`license_recheck_once(http=…)` + a thread `license_recheck_worker`):

1. Read the active serial + its cached offline/serial token (A2 stored the activation; the
   re-check re-sends the **vendor** `serial_token` if retained, else falls back to a status-only
   ping). Resolve the URL via `_license_cloud_url()`; **no clinic token** is used (validate is
   cloud-open).
2. Call `_validate_with_cloud(serial_token, fingerprint)`. On `None` (offline) → no-op (keep
   current cached state — offline never downgrades). On an answer, update the cached
   `licenses.status`/`expires_at`/`grace_until` to match (this is how a cloud-side `revoke`
   becomes a local `view_only` on the next check-in).
3. Cadence from `CLINIC_LICENSE_RECHECK_HOURS` (default `24`). Runs **independently** of the sync
   worker — it starts even when cloud sync is unpaired, and pairing for sync does not start it.
4. **Never raises**; all network/DB errors are swallowed and recorded in `app_settings`
   (`license_last_recheck_at` / `license_last_recheck_result`).

**Decoupling invariant (tested):** neither `activate_license` nor `license_recheck_once` ever
writes `cloud_url` / `cloud_clinic_token` / `cloud_clinic_id`. Activating a license leaves cloud
sync exactly as it was.

## Frontend (templates.HTML_TEMPLATE)

On `DOMContentLoaded`, the SPA fetches `/api/license/gate` once and branches:

- **`unlicensed`** → render a full-screen **activation overlay** (cannot be dismissed): a serial-
  token textarea + "Activate" button → `POST /api/license/activate {serial_token}`. On success,
  reload. This is the first-run gate. (Paste-the-serial UX; B makes it nicer/zero-config.)
- **`grace`** → a dismissible **renewal banner** at the top: "Subscription expired — in grace
  period until `<grace_until>`. Renew to avoid interruption." with a "Renew" action that opens the
  same activation overlay (re-activate with a fresh token).
- **`view_only`** → a persistent **view-only banner** ("License inactive — view only. Renew to make
  changes.") + a global `body.view-only` class that disables create/edit/delete controls (CSS
  `pointer-events:none; opacity:.5` on `[data-write]` actions) and short-circuits the app's
  mutating fetch helper to show the renewal prompt instead of calling the API.
- **`active`** → nothing extra.

**JS-escaping caveat (mandatory):** any newline inside the injected inline script must be written
`'\\n'` (double-escaped) because `HTML_TEMPLATE` is a plain Python string. After editing, run the
`node --check` sweep (Task verification) — a single bad escape silently kills every button.

The activation overlay and banners are **markers** the tests assert
(`assert 'id="license-gate-overlay"' in HTML_TEMPLATE`, etc.), matching the existing
template-presence test pattern.

## Error handling

- Gate/guard failures are deterministic JSON (`403 {reason:'view_only'}` / `{state:…}`), never
  `500`. The write-guard wraps its `_license_gate_state` call in try/except and **fails open**
  (allows the write) on an internal error — a licensing bug must never brick a paying clinic's
  ability to record a patient.
- `license_recheck_once` never raises; offline never downgrades state.

## Security / product notes

- View-only is **advisory** and offline-tolerant by design — a determined local attacker can
  bypass it (the A1 security review's standing caveat). It exists to make lapsed subscriptions
  *inconvenient and honest*, not unbreakable, and to never hold a paying clinic's data hostage.
- **Fail-open** on the write-guard is a deliberate product choice: false-positive lockouts are
  worse than a brief false-negative; the cloud re-check corrects state within `CLINIC_LICENSE_
  RECHECK_HOURS`.

## Test plan (A3)

Backend (`tests/test_license_gate_a3.py`, local mode, reuses the A2 fixture + signed-token
helper):

- **State mapping:** seed a cached `licenses` row and assert `_license_gate_state` →
  `active` (future window), `grace` (in grace), `view_only` (past grace), `view_only`
  (status `revoked`), `unlicensed` (no row). `GET /api/license/gate` returns the matching `state`.
- **Write-guard:** in `view_only`, `POST /api/patients` (or any clinical write) → `403
  view_only`; `GET /api/patients` → `200`; `POST /api/license/activate` → reaches the handler
  (not blocked); in `active`, the same `POST /api/patients` is allowed.
- **Fail-open:** monkeypatch `_license_gate_state` to raise → a clinical write still succeeds.
- **Decoupling:** after `POST /api/license/activate`, assert `app_settings` has **no** `cloud_url`
  / `cloud_clinic_token`; `cloud_status` still reports sync disabled.
- **Re-check:** stub `_validate_with_cloud` → `{valid:false, reason:'revoked'}`; run
  `license_recheck_once` → cached `licenses.status` becomes a state that maps to `view_only`;
  stub → `None` (offline) → state unchanged (no downgrade).

Frontend (`tests/test_license_gate_ui_a3.py`, template-presence + JS sweep):

- `HTML_TEMPLATE` contains `id="license-gate-overlay"`, the renewal banner id, the view-only
  banner id, and a `fetch('/api/license/gate'` call.
- **JS sweep:** extract the SPA `<script>` block(s) and run `node --check` — exit 0 (guards the
  escaping trap).

## Dependencies

None new. Reuses A1 `cryptography`, A2 `_validate_with_cloud`/`_license_cloud_url`, stdlib
`urllib`/`threading`. Frontend is vanilla JS in `HTML_TEMPLATE` (no build step). `node` is used
only by the test sweep (already an implicit dev dependency per the templates JS-escaping memory).

## Deferred / open

- **Baked cloud URL** so first-run activation needs zero typing/config → **B**. A3 requires the
  license URL to be resolvable (env or paired) for the *online* claim; with none, activation falls
  back to the signed token offline (A2 behaviour) and `unlicensed`→`active` still works, just
  without a cloud slot claim until the URL exists.
- **Mobile gate screen** (Flutter consuming `/api/license/gate` over the LAN) → **B**.
- **Renewal payments / self-serve billing portal** is out of scope for the whole initiative —
  renewal here means "present a fresh vendor-signed serial token."
