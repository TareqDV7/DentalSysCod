# CSRF Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hand-rolled synchronizer-token CSRF protection to the DentaCare Flask portal so cross-site requests cannot mutate clinic data, without breaking the offline-first mobile app or cloud sync.

**Architecture:** A per-session CSRF token (`secrets.token_urlsafe`) stored in Flask's signed-cookie session. A single `@app.before_request` hook validates an `X-CSRFToken` header on all unsafe-method requests, exempting requests that carry an `X-Clinic-Token` or `Authorization` header (mobile/sync/vendor — provably not forgeable cross-site). The SPA attaches the header via one `window.fetch` interceptor reading a `<meta>` tag; the two no-JS HTML forms (`/login`, `/change-password`) self-validate a hidden `csrf_token` field and re-render on failure. A `tests/conftest.py` test-client subclass auto-attaches a valid token so the existing suite stays green.

**Tech Stack:** Python 3.10–3.12, Flask, `render_template_string` (Jinja), pytest, vanilla JS in `templates.py`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-19-csrf-protection-design.md`. Every task implicitly includes its requirements.
- Safe methods `GET/HEAD/OPTIONS/TRACE` are **never** blocked.
- Exempt only on the **presence** of an `X-Clinic-Token` **header** or an `Authorization` **header** — never on the query-arg `clinic_token`.
- Mobile app and `_run_cloud_sync_once` send `X-Clinic-Token` as a **header** — must keep working unchanged.
- Token compare uses `secrets.compare_digest`.
- Kill-switch env `CLINIC_DISABLE_CSRF` (default off = enforced), read once at module load; log a `WARNING` when disabled.
- `secrets` and `logging` are already imported in `dental_clinic.py`. `os`, `session`, `request`, `jsonify`, `render_template_string` are already imported.
- Commit type prefixes: `feat`/`test`/`docs`. No attribution trailer (disabled globally).
- Use `rtk` prefix for git/test commands per repo convention. Run tests with `python -m pytest` and check exit code (summary is suppressed by RTK).
- Branch: `feat/csrf-protection` (already created; spec already committed).

---

### Task 1: CSRF token helpers

**Files:**
- Modify: `dental_clinic.py` (add helpers just above the `@app.route('/')` index, ~line 2155)
- Test: `tests/test_csrf.py` (new)

**Interfaces:**
- Produces: `_new_csrf_token() -> str`, `_get_or_create_csrf_token() -> str` (reads/writes `session['csrf_token']`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_csrf.py`:

```python
import secrets

import pytest

import dental_clinic


@pytest.fixture()
def app_ctx(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    return dental_clinic.app


def test_get_or_create_csrf_token_is_stable_within_session(app_ctx):
    with app_ctx.test_request_context('/'):
        from flask import session
        first = dental_clinic._get_or_create_csrf_token()
        second = dental_clinic._get_or_create_csrf_token()
        assert first and isinstance(first, str)
        assert first == second
        assert session['csrf_token'] == first


def test_new_csrf_token_is_random(app_ctx):
    a = dental_clinic._new_csrf_token()
    b = dental_clinic._new_csrf_token()
    assert a != b and len(a) >= 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_csrf.py -q`
Expected: FAIL — `AttributeError: module 'dental_clinic' has no attribute '_new_csrf_token'`.

- [ ] **Step 3: Write minimal implementation**

In `dental_clinic.py`, immediately before `@app.route('/')` (line ~2156), add:

```python
def _new_csrf_token():
    """A fresh, URL-safe CSRF token."""
    return secrets.token_urlsafe(32)


def _get_or_create_csrf_token():
    """Return the session's CSRF token, minting one on first use. Flask's
    signed-cookie session is the synchronizer store."""
    token = session.get('csrf_token')
    if not token:
        token = _new_csrf_token()
        session['csrf_token'] = token
    return token
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_csrf.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_csrf.py
rtk git commit -m "feat: CSRF token session helpers"
```

---

### Task 2: Enforcement hook + test-client auto-pass

**Files:**
- Modify: `dental_clinic.py` (add module constants + `_csrf_protect` before_request hook after `_require_password_change`, ~line 2050)
- Create: `tests/conftest.py`
- Test: `tests/test_csrf.py`

**Interfaces:**
- Consumes: `_get_or_create_csrf_token` (Task 1).
- Produces: module globals `_CSRF_ENABLED: bool`, `_CSRF_SAFE_METHODS: set`, `_CSRF_FORM_ROUTES: set`; functions `_request_is_csrf_exempt() -> bool`, `_form_csrf_ok() -> bool`; before_request `_csrf_protect`. Test-client class `tests.conftest._CsrfTestClient` (attaches `X-CSRFToken` + form `csrf_token` on unsafe requests unless `csrf=False`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_csrf.py`:

```python
@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def test_unsafe_without_token_is_rejected(client):
    # csrf=False => the auto-pass client does NOT attach a token.
    resp = client.post('/api/appointments', json={'patient_id': 1}, csrf=False)
    assert resp.status_code == 403
    assert resp.get_json().get('reason') == 'csrf'


def test_unsafe_with_matching_token_passes_csrf(client):
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'known-token'
    # Bad patient id still returns a non-403 (CSRF passed, handler ran).
    resp = client.post('/api/appointments', json={'patient_id': 999999},
                       headers={'X-CSRFToken': 'known-token'}, csrf=False)
    assert resp.status_code != 403


def test_get_is_never_blocked(client):
    resp = client.get('/api/appointments', csrf=False)
    assert resp.status_code != 403


def test_kill_switch_disables_enforcement(client, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_CSRF_ENABLED', False)
    resp = client.post('/api/appointments', json={'patient_id': 999999}, csrf=False)
    assert resp.status_code != 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_csrf.py -q`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'csrf'` (no conftest client yet) and/or rejection tests fail because no hook exists.

- [ ] **Step 3: Create the auto-pass test client**

Create `tests/conftest.py`:

```python
"""Shared test fixtures. The CSRF middleware (feat/csrf-protection) rejects
unsafe-method requests without a valid token. The whole existing suite POSTs
without one, so this test-client subclass mirrors the real frontend fetch
interceptor: it seeds a session CSRF token and attaches a matching X-CSRFToken
header (and a csrf_token form field) on unsafe methods. Pass csrf=False to opt
out and exercise the rejection path."""
import secrets

from flask.testing import FlaskClient

import dental_clinic

_UNSAFE = {'POST', 'PUT', 'PATCH', 'DELETE'}


class _CsrfTestClient(FlaskClient):
    def open(self, *args, **kwargs):
        attach = kwargs.pop('csrf', True)
        method = (kwargs.get('method') or 'GET').upper()
        if attach and method in _UNSAFE:
            with self.session_transaction() as sess:
                token = sess.get('csrf_token')
                if not token:
                    token = secrets.token_urlsafe(32)
                    sess['csrf_token'] = token
            headers = dict(kwargs.get('headers') or {})
            headers.setdefault('X-CSRFToken', token)
            kwargs['headers'] = headers
            data = kwargs.get('data')
            if isinstance(data, dict) and 'csrf_token' not in data:
                data = dict(data)
                data['csrf_token'] = token
                kwargs['data'] = data
        return super().open(*args, **kwargs)


# Applied at collection time, before any test builds a client.
dental_clinic.app.test_client_class = _CsrfTestClient
```

- [ ] **Step 4: Write the enforcement hook**

In `dental_clinic.py`, after the `_require_password_change` before_request hook (ends ~line 2050), add:

```python
_CSRF_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}
_CSRF_FORM_ROUTES = {'/login', '/change-password'}
_CSRF_ENABLED = os.environ.get('CLINIC_DISABLE_CSRF', '0').strip().lower() \
    not in ('1', 'true', 'yes', 'on')
if not _CSRF_ENABLED:
    logging.getLogger(__name__).warning(
        'CSRF protection is DISABLED via CLINIC_DISABLE_CSRF — re-enable for production.')


def _request_is_csrf_exempt():
    # A classic CSRF vector (an HTML form, or a "simple" cross-origin fetch) cannot
    # set custom request headers without a CORS preflight this server never approves.
    # So the presence of X-Clinic-Token / Authorization proves the request is not a
    # forged cross-site one. Mobile + cloud-sync use the X-Clinic-Token header.
    return bool(request.headers.get('X-Clinic-Token') or request.headers.get('Authorization'))


def _form_csrf_ok():
    """Validate the hidden csrf_token field for the no-JS HTML form POSTs."""
    submitted = request.form.get('csrf_token') or ''
    expected = session.get('csrf_token') or ''
    return bool(expected and submitted and secrets.compare_digest(str(submitted), str(expected)))


@app.before_request
def _csrf_protect():
    if not _CSRF_ENABLED:
        return None
    if request.method in _CSRF_SAFE_METHODS:
        return None
    # The two no-JS form routes self-validate + re-render in their own handlers.
    if (request.path or '') in _CSRF_FORM_ROUTES:
        return None
    if _request_is_csrf_exempt():
        return None
    submitted = request.headers.get('X-CSRFToken') or request.form.get('csrf_token') or ''
    expected = session.get('csrf_token') or ''
    if expected and submitted and secrets.compare_digest(str(submitted), str(expected)):
        return None
    return jsonify({'error': 'Security check failed — please reload the page.',
                    'reason': 'csrf'}), 403
```

- [ ] **Step 5: Run the new tests + the full suite**

Run: `python -m pytest tests/test_csrf.py -q`
Expected: PASS.
Run: `python -m pytest tests/ -q; echo "exit=$?"`
Expected: `exit=0` — the conftest auto-pass keeps every existing write-test green.

- [ ] **Step 6: Commit**

```bash
rtk git add dental_clinic.py tests/conftest.py tests/test_csrf.py
rtk git commit -m "feat: CSRF before_request enforcement hook + test-client auto-pass"
```

---

### Task 3: Exemptions for token-authenticated clients

**Files:**
- Test: `tests/test_csrf.py` (the hook logic already exists from Task 2; these tests pin the exemption contract and prove mobile/sync are unaffected)

**Interfaces:**
- Consumes: `_csrf_protect`, `_request_is_csrf_exempt` (Task 2).

- [ ] **Step 1: Write the tests**

Append to `tests/test_csrf.py`:

```python
def test_x_clinic_token_header_exempts(client):
    resp = client.post('/api/appointments', json={'patient_id': 999999},
                       headers={'X-Clinic-Token': 'whatever'}, csrf=False)
    assert resp.status_code != 403  # exempt: handler ran (mobile/sync path)


def test_authorization_header_exempts(client):
    resp = client.post('/api/appointments', json={'patient_id': 999999},
                       headers={'Authorization': 'Bearer x'}, csrf=False)
    assert resp.status_code != 403


def test_query_arg_clinic_token_does_not_exempt(client):
    resp = client.post('/api/appointments?clinic_token=whatever',
                       json={'patient_id': 999999}, csrf=False)
    assert resp.status_code == 403
    assert resp.get_json().get('reason') == 'csrf'
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/test_csrf.py -q`
Expected: PASS — exemption keys on the header, never on the query arg.

> Note: these pass against the Task-2 hook (the exemption logic shipped there because mobile/sync must never break). They are a separate task because a reviewer evaluates the *exemption contract* independently.

- [ ] **Step 3: Commit**

```bash
rtk git add tests/test_csrf.py
rtk git commit -m "test: pin CSRF header-only exemption contract"
```

---

### Task 4: SPA token delivery — meta tag + fetch interceptor

**Files:**
- Modify: `dental_clinic.py:2158` (index passes `csrf_token=`)
- Modify: `templates.py:15` (meta tag) and `templates.py:3268` (fetch interceptor)
- Test: `tests/test_csrf.py`

**Interfaces:**
- Consumes: `_get_or_create_csrf_token` (Task 1).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_csrf.py`:

```python
def test_index_html_contains_csrf_meta_and_interceptor(client):
    # Seed a license-free portal: '/' requires login, so authenticate.
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'admin'
    resp = client.get('/')
    html = resp.get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert 'X-CSRFToken' in html  # the fetch interceptor is present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_csrf.py::test_index_html_contains_csrf_meta_and_interceptor -q`
Expected: FAIL — meta tag / interceptor not yet in the template.

- [ ] **Step 3a: Pass the token from the index route**

In `dental_clinic.py`, change `index()` (line 2158):

```python
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, **CLINIC_CONFIG,
                                  ALLOW_OFFLINE_ACTIVATION=ALLOW_OFFLINE_ACTIVATION,
                                  csrf_token=_get_or_create_csrf_token())
```

- [ ] **Step 3b: Add the meta tag**

In `templates.py`, after line 15 (`<meta name="viewport" ...>`) add:

```html
    <meta name="csrf-token" content="{{ csrf_token }}">
```

- [ ] **Step 3c: Add the fetch interceptor**

In `templates.py`, immediately after `<script>` (line 3268), insert as the first statements:

```javascript
        // CSRF: attach the per-session token to same-origin unsafe requests.
        // One interceptor covers every fetch() call site (incl. FormData uploads).
        (function () {
            const _csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
            const _origFetch = window.fetch.bind(window);
            const _unsafe = { POST: 1, PUT: 1, PATCH: 1, DELETE: 1 };
            window.fetch = function (input, init) {
                init = init || {};
                const method = (init.method
                    || (input && typeof input === 'object' && input.method)
                    || 'GET').toUpperCase();
                const url = (typeof input === 'string') ? input
                    : ((input && input.url) || '');
                const sameOrigin = url.startsWith('/')
                    || url.startsWith(window.location.origin);
                if (_unsafe[method] && sameOrigin && _csrfToken) {
                    const headers = new Headers(init.headers
                        || (input && typeof input === 'object' ? input.headers : null)
                        || {});
                    if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', _csrfToken);
                    init.headers = headers;
                }
                return _origFetch(input, init);
            };
        })();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_csrf.py::test_index_html_contains_csrf_meta_and_interceptor -q`
Expected: PASS.

- [ ] **Step 5: Audit the vendor console**

Run: `rtk grep -n "fetch(\|<form\|method=.*post" serial_admin_ui.py`
If `serial_admin_ui.py` performs session-cookie writes from a browser, apply the same `<meta name="csrf-token">` + fetch-interceptor treatment to its template and pass `csrf_token=` into its render call. If it only uses the admin bearer token (exempt) or has no browser writes, note "no change needed" and move on.

- [ ] **Step 6: Commit**

```bash
rtk git add dental_clinic.py templates.py tests/test_csrf.py
rtk git commit -m "feat: SPA CSRF token delivery (meta tag + fetch interceptor)"
```

---

### Task 5: No-JS form protection + login token rotation

**Files:**
- Modify: `dental_clinic.py` — login GET/POST (2095–2118), change-password GET/POST (2050–2092)
- Modify: `templates.py:8832` (login hidden input), `templates.py:8913` (force-change hidden input)
- Test: `tests/test_csrf.py`

**Interfaces:**
- Consumes: `_get_or_create_csrf_token`, `_new_csrf_token` (Task 1), `_form_csrf_ok` (Task 2).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_csrf.py`:

```python
def _seed_user(username='admin', password='admin', must_change=0):
    import sqlite3
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute(
        'INSERT INTO users (username, password_hash, is_active, must_change_password) '
        'VALUES (?, ?, 1, ?)',
        (username, generate_password_hash(password), must_change))
    conn.commit()
    conn.close()


def test_login_without_csrf_field_is_rejected(client):
    _seed_user()
    resp = client.post('/login', data={'username': 'admin', 'password': 'admin'},
                       csrf=False)
    assert resp.status_code == 400
    assert b'reload' in resp.data.lower() or b'security' in resp.data.lower()


def test_login_with_csrf_field_succeeds_and_rotates_token(client):
    _seed_user()
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'pre-login-token'
    resp = client.post('/login',
                       data={'username': 'admin', 'password': 'admin',
                             'csrf_token': 'pre-login-token'},
                       csrf=False, follow_redirects=False)
    assert resp.status_code in (301, 302)  # redirect to index on success
    with client.session_transaction() as sess:
        assert sess.get('uid')
        assert sess.get('csrf_token') and sess['csrf_token'] != 'pre-login-token'


def test_login_page_get_contains_csrf_field(client):
    resp = client.get('/login')
    assert b'name="csrf_token"' in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_csrf.py -k login -q`
Expected: FAIL — login accepts the form without a token / no hidden field present / token not rotated.

- [ ] **Step 3a: Add hidden inputs to the forms**

In `templates.py`, in `LOGIN_TEMPLATE` after line 8832 (`<input type="hidden" name="next" ...>`) add:

```html
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
```

In `templates.py`, in `FORCE_CHANGE_TEMPLATE` after line 8913 (the `{% if error %}...{% endif %}` line) add:

```html
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
```

- [ ] **Step 3b: Pass `csrf_token` into the form renders + self-validate + rotate**

In `dental_clinic.py`, `login_page()`:

- At the top of the `POST` branch (after line 2098 `if request.method == 'POST':`), insert:

```python
        if not _form_csrf_ok():
            return render_template_string(
                LOGIN_TEMPLATE,
                error='Security check failed — please reload and try again.',
                next_url=next_url, csrf_token=_get_or_create_csrf_token()), 400
```

- After successful login, after line 2112 (`session['uname'] = user['username']`), add:

```python
            session['csrf_token'] = _new_csrf_token()  # rotate on privilege change
```

- Update both `LOGIN_TEMPLATE` renders (the 401 fail at 2115 and the GET at 2118) to pass `csrf_token=_get_or_create_csrf_token()`:

```python
        return render_template_string(LOGIN_TEMPLATE, error='Invalid username or password.',
                                      next_url=next_url,
                                      csrf_token=_get_or_create_csrf_token()), 401
    ...
    return render_template_string(LOGIN_TEMPLATE, error=None, next_url=next_url,
                                  csrf_token=_get_or_create_csrf_token())
```

In `dental_clinic.py`, `change_password` route:

- The GET render at line 2062 → `return render_template_string(FORCE_CHANGE_TEMPLATE, error=None, csrf_token=_get_or_create_csrf_token())`
- The `_fail` helper at 2068–2069 → `return render_template_string(FORCE_CHANGE_TEMPLATE, error=msg, csrf_token=_get_or_create_csrf_token()), 400`
- At the top of the POST handling (after line 2063, before reading `current`), insert:

```python
    if not _form_csrf_ok():
        return _fail('Security check failed — please reload and try again.')
```

(Define `_fail` before this check, or move the `_fail` definition above it — `_fail` currently sits at 2068; relocate it to just after the GET branch so the CSRF check can call it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_csrf.py -k "login or change" -q`
Expected: PASS.
Run: `python -m pytest tests/test_force_password_change.py -q`
Expected: PASS (conftest injects `csrf_token` into form `data` dicts, so existing force-change tests stay green).

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py templates.py tests/test_csrf.py
rtk git commit -m "feat: CSRF-protect login + change-password forms; rotate token on login"
```

---

### Task 6: Full verification + docs

**Files:**
- Modify: `docs/LAUNCH_READINESS.md` (tick the CSRF item)
- Modify: `README.md` (if it documents env vars / security — add `CLINIC_DISABLE_CSRF` + CSRF note)

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest tests/ -q; echo "exit=$?"`
Expected: `exit=0`, no regressions.

- [ ] **Step 2: Lint**

Run: `rtk ruff check dental_clinic.py tests/conftest.py tests/test_csrf.py`
Expected: clean (fix any issues, e.g. unused imports).

- [ ] **Step 3: JS render sanity sweep**

Per the templates.py escaping trap, confirm the inline script still parses. Run:
`python -c "import dental_clinic; from flask import Flask; app=dental_clinic.app; c=app.test_client();
import sqlite3"` then render `/` in a request context with a session and assert the served HTML
contains both `name=\"csrf-token\"` and the interceptor — already covered by
`test_index_html_contains_csrf_meta_and_interceptor`. Additionally run a Node syntax check if
available: extract is not required; rely on the existing render test.

- [ ] **Step 4: Update LAUNCH_READINESS**

In `docs/LAUNCH_READINESS.md`, change the CSRF line under "Security hardening" from `- [ ]` to `- [x]` and append: `Hand-rolled synchronizer token (X-CSRFToken header / hidden field), before_request hook, broad scope exempting X-Clinic-Token/Authorization header clients; CLINIC_DISABLE_CSRF kill-switch. See docs/superpowers/specs/2026-06-19-csrf-protection-design.md.`

- [ ] **Step 5: Commit**

```bash
rtk git add docs/LAUNCH_READINESS.md README.md
rtk git commit -m "docs: mark CSRF protection done; document CLINIC_DISABLE_CSRF"
```

---

## Self-Review

**Spec coverage:**
- §2 broad scope → Task 2 hook + Task 3 exemptions ✓
- §3.1 token lifecycle / rotation → Task 1 + Task 5 (rotate on login) ✓
- §3.2 validation hook → Task 2 ✓
- §4 header-only exemption rationale → Task 2 `_request_is_csrf_exempt` + Task 3 tests ✓
- §5 error handling (JSON 403 vs form 400) → Task 2 (JSON) + Task 5 (form self-validate 400) ✓
- §6 kill-switch → Task 2 (`_CSRF_ENABLED`, startup warning, test) ✓
- §7 frontend (meta + interceptor + hidden inputs + serial_admin audit) → Tasks 4 & 5 ✓
- §8 test migration (conftest auto-pass) → Task 2 ✓
- §9 files touched → all covered ✓
- §10 test plan items 1–12 → mapped across Tasks 2–5 ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. The `serial_admin_ui.py` step is a conditional audit with explicit grep + decision criteria, not a placeholder.

**Type consistency:** `_get_or_create_csrf_token` / `_new_csrf_token` / `_form_csrf_ok` / `_request_is_csrf_exempt` / `_CSRF_ENABLED` names are identical across all tasks. Header name `X-CSRFToken` and field name `csrf_token` are consistent in middleware, frontend, forms, and conftest. Reject `reason` value `'csrf'` consistent in hook and tests.
