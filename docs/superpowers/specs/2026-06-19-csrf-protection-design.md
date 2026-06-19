# CSRF Protection — Design Spec

**Date:** 2026-06-19
**Branch:** `feat/csrf-protection`
**Status:** Approved (brainstorm complete) → ready for implementation plan
**Source item:** `docs/LAUNCH_READINESS.md` → Cross-cutting → "Add CSRF protection to the
session-authenticated Flask portal (currently none; matters most for the exposed cloud node)." 🔴

---

## 1. Problem

The DentaCare desktop/cloud Flask app has **no CSRF protection**. State-changing requests
(`POST/PUT/PATCH/DELETE`) are accepted from any origin as long as the request reaches the
server. Because the app is offline-first, **most `/api/*` endpoints require no session at all**
(only a small `_AUTH_REQUIRED_EXACT` set + `/invoice/` is login-gated), so a malicious website
visited by a clinic browser can drive that browser to mutate clinic data on
`http://<lan-ip>:5000/api/...` — with or without a logged-in session. The internet-exposed
cloud node widens this surface.

## 2. Scope (decided)

**Broad.** Protect **all** unsafe-method requests (`POST/PUT/PATCH/DELETE`) by default across
the session portal, the open SPA/LAN API, and the cloud node. **Exempt only** non-ambient-credential
clients: requests carrying an `X-Clinic-Token` header (mobile app, cloud sync) or an
`Authorization` header (vendor/admin API). Mobile and sync must keep working unchanged.

Safe methods (`GET/HEAD/OPTIONS/TRACE`) are never blocked.

## 3. Mechanism (decided): hand-rolled synchronizer token

Chosen over Flask-WTF because: the broad scope needs a **dynamic** exemption (presence of a
clinic/admin header) that maps cleanly onto a `before_request` hook but awkwardly onto
Flask-WTF's per-view `@csrf.exempt`; the app is **PyInstaller-frozen** (avoid a new bundled
dependency); and the codebase already hand-rolls its security gates as `before_request` hooks
(`_require_login_for_portal`, `_enforce_view_only`). The underlying mechanism — a per-session
token compared with `secrets.compare_digest` — is small and standard.

### 3.1 Token lifecycle
- `_get_or_create_csrf_token()` returns `session['csrf_token']`, lazily minting
  `secrets.token_urlsafe(32)` on first need. Flask's signed-cookie session is the synchronizer store.
- **Rotated** (regenerated) on successful login. Logout already calls `session.clear()`, so the
  token dies there naturally — no extra logout handling needed beyond confirming `session.clear()`.

### 3.2 Validation hook — `@app.before_request def _csrf_protect()`
Registered **after** the existing auth / view-only gates. Order of checks:
1. If `CLINIC_DISABLE_CSRF` is set (truthy) → return (enforcement off; see §6).
2. If `request.method` in `{GET, HEAD, OPTIONS, TRACE}` → return.
3. **Exempt** (return) if the request has an `X-Clinic-Token` header **or** an `Authorization`
   header present. (Rationale in §4.)
4. Read the submitted token from the `X-CSRFToken` header (SPA) **or** the `csrf_token` form
   field (the two no-JS forms).
5. Compare to `session.get('csrf_token')` using `secrets.compare_digest`. If the session has no
   token, or the submitted token is missing/mismatched → **reject** (see §5).

## 4. Exemption rationale (security-critical)

Exemption keys on the **presence of a custom request header** (`X-Clinic-Token` /
`Authorization`), **not** on the query-arg `clinic_token`.

- A classic CSRF vector — an HTML `<form>` submission, or a "simple" cross-origin `fetch` — **cannot
  set custom request headers**. Setting any non-safelisted header forces a CORS preflight that this
  server never approves cross-origin. So any request that *does* carry `X-Clinic-Token` /
  `Authorization` is provably not a forged cross-site request, and is safe to exempt.
- The query-arg `clinic_token` (also accepted by `_resolve_clinic_token`) **can** be set cross-site
  (it is just part of a URL), so it deliberately does **not** exempt. A write that authenticates only
  via query-arg `clinic_token` would still require a CSRF token.
- Verified: the mobile app and `_run_cloud_sync_once` both send `X-Clinic-Token` as a **header**, so
  they are exempt and unaffected.

## 5. Error handling / UX

Response type is decided by the **request path**, with no ambiguity:

- **The two no-JS form routes** (`POST /login`, `POST /change-password`) → re-render that form via
  `render_template_string` with an inline bilingual error (reusing the existing `error=` argument)
  and a fresh `csrf_token`. Returns HTTP **400**.
- **Every other rejected request** → `jsonify({'error': <message>, 'reason': 'csrf'}), 403`. The
  SPA detects `reason == 'csrf'` and shows a bilingual (EN/AR) "your session expired — please reload
  the page" toast.

The reject helper therefore branches on `request.path in {'/login', '/change-password'}` →
HTML 400, else → JSON 403.

## 6. Configuration / kill-switch

`CLINIC_DISABLE_CSRF` env var. **Default off → CSRF enforced everywhere.** It is read at
launch/deploy time (not flippable by a request, so it adds no attacker surface) and exists as an
operational safety valve consistent with the existing `CLINIC_ALLOW_OFFLINE_ACTIVATION` pattern —
so an unforeseen edge case on the live single-workstation appliance can be unblocked without a
redeploy. When enforcement is disabled, log a loud `WARNING` at startup.

## 7. Frontend integration

`templates.py` constants are rendered via Jinja `render_template_string`, so the token is passed as
a clean `{{ csrf_token }}` variable (no Python-string-substitution / JS-escaping trap).

- **SPA (`HTML_TEMPLATE`):**
  - Inject `<meta name="csrf-token" content="{{ csrf_token }}">` into `<head>`.
  - Add **one** `window.fetch` interceptor at the very top of the inline script (before any other
    code calls `fetch`). On **same-origin, unsafe-method** requests it sets `X-CSRFToken` from the
    meta tag if not already present. This covers all ~97 scattered `fetch()` call sites — including
    `FormData` uploads (header only; request body untouched) — with **zero per-call-site edits**.
  - `/` route (`index()`) passes `csrf_token=_get_or_create_csrf_token()` into `render_template_string`.
- **No-JS forms (`LOGIN_TEMPLATE`, `FORCE_CHANGE_TEMPLATE`):**
  - Hidden `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">` inside each `<form>`.
  - Their `render_template_string` calls (login GET, change-password GET) pass `csrf_token=`.
- **Planning audit:** the vendor/serial-admin console (`serial_admin_ui.py`) — if it performs
  session-cookie writes from a browser, it gets the same meta-tag + fetch-interceptor treatment.
  Confirm during plan/implementation.

## 8. Test-suite migration (primary cost)

Existing tests each build their own `dental_clinic.app.test_client()` and POST **without** a token
(e.g. `client.post('/api/appointments', json=...)`). Under broad enforcement these would all 403.

- Add **`tests/conftest.py`** with a session-scoped autouse fixture that sets
  `dental_clinic.app.test_client_class` to a `_CsrfTestClient` subclass. Its `open()` override:
  seeds `session['csrf_token']` via `client.session_transaction()` and attaches a matching
  `X-CSRFToken` header on unsafe methods — **mirroring the real frontend interceptor**. Every test
  file calls `app.test_client()`, so all inherit this with **zero per-test edits**, while still
  routing through the real CSRF middleware (token present + valid → passes).
- Dedicated CSRF tests opt out of the auto-pass (bare client, or an explicit bad/missing token) to
  assert rejection.

## 9. Files touched

- `dental_clinic.py` — `_get_or_create_csrf_token()`, `_csrf_protect()` before_request hook, rotate
  token on login success, pass `csrf_token=` into the 3 `render_template_string` calls
  (`index`, login GET, change-password GET), confirm logout `session.clear()`.
- `templates.py` — meta tag + fetch interceptor in `HTML_TEMPLATE`; hidden input in
  `LOGIN_TEMPLATE` + `FORCE_CHANGE_TEMPLATE`; SPA bilingual `reason:'csrf'` toast mapping.
- `tests/conftest.py` — **new**, the `_CsrfTestClient` auto-pass fixture.
- `tests/test_csrf.py` — **new**, the CSRF behavior suite (§10).
- `serial_admin_ui.py` — **conditional**, pending §7 audit.
- `docs/LAUNCH_READINESS.md` — tick the CSRF item.

## 10. Test plan (what the suite proves)

1. `GET /` HTML response contains `<meta name="csrf-token" ...>`.
2. Unsafe request with a session but **no** token → 403, `reason:'csrf'`.
3. Unsafe request with a **correct** `X-CSRFToken` matching the session → 200 / expected.
4. Unsafe request with an **`X-Clinic-Token` header** (no CSRF token) → exempt, passes.
5. Unsafe request with an **`Authorization` header** → exempt, passes.
6. Query-arg `clinic_token` does **not** exempt — still 403 without a CSRF token.
7. Safe methods (`GET/HEAD/OPTIONS`) are never blocked.
8. Mismatched token → 403.
9. `POST /login` without `csrf_token` field → 400 + re-render; with correct field → logs in.
10. `POST /change-password` — same missing/correct behavior.
11. Token **rotates** on login (token before login ≠ token after).
12. `CLINIC_DISABLE_CSRF` set → enforcement off (unsafe request without token passes).

## 11. Out of scope

- Splitting `templates.py` into Jinja files / static assets (separate LAUNCH_READINESS item; CSP
  depends on it, not on this).
- Rate limiting, encryption-at-rest, audit log (separate items).
- Any change to the mobile app or cloud-sync wire protocol.
