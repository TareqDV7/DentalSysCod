# Security PR 1: Content-Security-Policy Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pragmatic Content-Security-Policy response header that locks down external script/style/frame/object sources while keeping every existing `onclick="..."` handler working unmodified.

**Architecture:** One line added to the existing `_add_security_headers` `after_request` hook in `dental_clinic.py` (no new hook, no new file). `'unsafe-inline'` stays in `script-src`/`style-src` deliberately — see spec Decision 2.

**Tech Stack:** Flask `after_request`, no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-07-security-hardening-rbac-design.md`, Decision 2 + Architecture › CSP.
- `'unsafe-inline'` MUST remain in `script-src` and `style-src` — do not attempt nonce-based CSP in this PR (that's the explicit Non-goal in the spec).
- The header must use `.setdefault()` semantics consistent with the other headers already in `_add_security_headers` (a handler that sets its own CSP wins) — actually verified: the existing headers use `response.headers.setdefault(...)`. Follow the same pattern.
- Verified this session: `templates.py` has zero external `fetch()`/`src="https://..."` calls — everything is same-origin. So `connect-src`/`img-src`/`font-src`/`style-src` need only `'self'` (+ `data:` for inlined base64 images/fonts), no external host exceptions.

---

### Task 1: Add the CSP header

**Files:**
- Modify: `dental_clinic.py:173-192` (the `_add_security_headers` function)
- Test: `tests/test_security_hardening.py`

**Interfaces:**
- Consumes: nothing new — reuses the existing `_add_security_headers` function and `request.is_secure` check already in that function.
- Produces: nothing consumed by later tasks (this PR is self-contained).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_security_hardening.py` (after `test_hsts_only_over_https`):

```python
def test_csp_header_present_and_locked_down(local_client):
    r = local_client.get('/healthz')
    csp = r.headers.get('Content-Security-Policy')
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data:" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_security_hardening.py::test_csp_header_present_and_locked_down -v`
Expected: FAIL — `AssertionError: assert None is not None` (no `Content-Security-Policy` header yet).

- [ ] **Step 3: Add the header in `_add_security_headers`**

In `dental_clinic.py`, replace the current function (lines 173-192):

```python
@app.after_request
def _add_security_headers(response):
    # Baseline browser hardening on every response. Harmless on JSON API replies,
    # meaningful on the HTML portal: nosniff stops MIME-confusion, DENY blocks
    # click-jacking via <iframe>, and the referrer/permissions policies trim what
    # leaks to third parties. setdefault() so a handler that sets its own wins.
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    # Pragmatic CSP: the portal is built entirely on inline onclick="..." handlers
    # (hundreds of them in templates.py), so 'unsafe-inline' stays in script-src/
    # style-src rather than forcing a large separate nonce-migration refactor
    # (see docs/superpowers/specs/2026-07-07-security-hardening-rbac-design.md,
    # Decision 2). Everything else is locked down: no external script/style/font
    # sources (verified zero external fetch()/src= calls in templates.py), no
    # framing, no <object>/<embed>, no base tag hijacking.
    response.headers.setdefault('Content-Security-Policy', (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'"
    ))
    # HSTS only over HTTPS (cloud node behind Caddy). Never on plain-HTTP LAN
    # access — a cached max-age would lock the clinic out of its own http:// server.
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security',
                                    'max-age=31536000; includeSubDomains')
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_security_hardening.py -v`
Expected: PASS (both existing tests + the new one, 3/3).

- [ ] **Step 5: Manual smoke check for a broken button**

The CSP keeps `'unsafe-inline'`, so no `onclick=` handler should break. Still, run the full suite once to catch any test that asserts on response headers elsewhere and might now see the new header unexpectedly:

Run: `python -m pytest tests/ -q`
Expected: full suite green, same pass count as before this change (no new failures).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_security_hardening.py
git commit -m "feat(security): add pragmatic Content-Security-Policy header

Locks down external script/style/font/frame/object sources while keeping
'unsafe-inline' for script-src/style-src so the inline onclick=-based
frontend keeps working unmodified. First of 3 security sub-project PRs."
```

## Self-review notes

- Spec coverage: this plan implements spec Decision 2 and the Architecture › CSP section in full. Decisions 1 (PR sequencing), 3-7 (RBAC/encryption) are out of scope for this file by design — covered in the other two plan files.
- No placeholders — the exact header string and exact diff are given above.
- Type/name consistency: `_add_security_headers` name and `request.is_secure` usage match the current code exactly (verified by reading `dental_clinic.py:173-192` directly before writing this plan).
