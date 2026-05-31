# Percentage Discount Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user enter a discount as a percentage (`%20` or `20%`) in the follow-up and billing discount fields; it resolves to that percent of the line's base (follow-up price / billing subtotal) and the `20%` notation is preserved on the sheet and printed invoice.

**Architecture:** Mirror the existing expression-preservation feature. Client `evalCalcField` gains a percent branch that resolves `%N` against a base field named in a new `data-percent-base` attribute and stashes the normalized `"N%"` in `dataset.expr`. Server `sanitize_amount_expr` gains an optional `base` so it can validate `base × pct/100 ≈ stored discount` and keep the `"N%"` label only when honest. `amt_cell` forwards the subtotal so the label survives invoice re-validation.

**Tech Stack:** Python 3 / Flask (single file `dental_clinic.py`), HTML+vanilla-JS template string `templates.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-percentage-discount-design.md`

---

## Reference: confirmed touch points

| What | Location |
|------|----------|
| `sanitize_amount_expr(raw, numeric_value)` | `dental_clinic.py:1249` |
| `_AMOUNT_EXPR_RE = re.compile(r'^[0-9.+\-*/() ]+$')` | `dental_clinic.py:1246` |
| follow-up POST discount sanitize | `dental_clinic.py:2047` |
| follow-up PUT discount sanitize | `dental_clinic.py:2190` |
| billing POST validation + sanitize (`subtotal`/`discount`/`paid_amount`) | `dental_clinic.py:3293-3335` |
| `amt_cell(value, expr=None)` + discount row | `dental_clinic.py:3460-3465`, `:3501` |
| invoice route `GET /invoice/<id>` (`b = dict(row)` from `SELECT b.*`) | `dental_clinic.py:3406` |
| `evalArithmeticExpr` / `evalCalcField` / `calcExprOf` | `templates.py:6243` / `:6258` / `:6288` |
| `parseCurrency` | `templates.py:3559` |
| follow-up ADD price/discount inputs (`#followup-price` / `#followup-discount`) | `templates.py:5612-5613` |
| follow-up EDIT price/discount inputs (`#ef-price` / `#ef-discount`) | `templates.py:2583` / `:2587` |
| billing subtotal/discount inputs (`name="subtotal"` / `name="discount"`) | `templates.py:2172` / `:2176` |
| `HTML_TEMPLATE = '''...'''` (importable module string) | `templates.py:8` |
| existing percent-free tests to model on | `tests/test_expression_preservation.py` |

**JS-in-Python note (Tasks 4–5):** `HTML_TEMPLATE` is a normal `'''...'''` string, so backslashes are **doubled** in source (`\\d` in the file → `\d` in served JS). Code blocks for `templates.py` below are written exactly as they must appear in the file (doubled). Braces `{}` and JS `${...}` are literal.

---

## Task 1: Server — percent parsing + `base`-aware `sanitize_amount_expr`

**Files:**
- Modify: `dental_clinic.py:1246-1265`
- Test: `tests/test_expression_preservation.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_expression_preservation.py`, after the existing `# ── sanitize_amount_expr (unit-level) ──` group (after `test_sanitize_rejects_unsafe_input`, ~line 56):

```python
# ── percent discounts (unit-level) ──────────────────────────────────────────

def test_sanitize_keeps_matching_percent():
    # 20% of base 100 == stored discount 20 → keep, normalized to "20%"
    assert dental_clinic.sanitize_amount_expr('20%', 20, base=100) == '20%'
    assert dental_clinic.sanitize_amount_expr('%20', 20, base=100) == '20%'   # leading % normalizes
    assert dental_clinic.sanitize_amount_expr('12.5%', 10, base=80) == '12.5%'
    assert dental_clinic.sanitize_amount_expr('20.0%', 20, base=100) == '20%'  # trailing zero trimmed


def test_sanitize_percent_requires_base():
    # No base → cannot verify a percent → dropped.
    assert dental_clinic.sanitize_amount_expr('20%', 20) is None
    assert dental_clinic.sanitize_amount_expr('20%', 20, base=None) is None


def test_sanitize_drops_mismatched_percent():
    # 20% of 100 is 20, not 30 → tampered → dropped.
    assert dental_clinic.sanitize_amount_expr('20%', 30, base=100) is None


def test_sanitize_rejects_malformed_percent():
    assert dental_clinic.sanitize_amount_expr('50%+10', 60, base=100) is None
    assert dental_clinic.sanitize_amount_expr('%-20', 20, base=100) is None
    assert dental_clinic.sanitize_amount_expr('20%%', 20, base=100) is None
    assert dental_clinic.sanitize_amount_expr('%', 0, base=100) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_expression_preservation.py -k percent -v`
Expected: FAIL — `TypeError: sanitize_amount_expr() got an unexpected keyword argument 'base'`.

- [ ] **Step 3: Add the percent helpers above `sanitize_amount_expr`**

Insert immediately after the `_AMOUNT_EXPR_RE = ...` line (`dental_clinic.py:1246`):

```python
_PERCENT_NUM_RE = re.compile(r'^\d+(?:\.\d+)?$')


def _parse_percent(raw):
    """Return the percent magnitude when ``raw`` is a single leading/trailing ``%`` wrapping
    a plain non-negative number (``"20%"`` or ``"%20"`` → ``20.0``); otherwise ``None``."""
    s = str(raw or '').strip()
    if s.count('%') != 1 or not (s.startswith('%') or s.endswith('%')):
        return None
    core = s.replace('%', '').strip()
    if not _PERCENT_NUM_RE.match(core):
        return None
    return float(core)


def _format_percent(pct):
    """Normalise a percent magnitude for display: ``20.0`` → ``"20%"``, ``12.5`` → ``"12.5%"``."""
    text = f'{pct:.4f}'.rstrip('0').rstrip('.')
    return f'{text}%'
```

- [ ] **Step 4: Make `sanitize_amount_expr` base-aware**

Replace the function header and opening guard (`dental_clinic.py:1249-1256`).

Find:

```python
def sanitize_amount_expr(raw, numeric_value):
    """If the user typed a real arithmetic expression for an amount (e.g. ``"20+20"``)
    we keep it verbatim so it can be shown on the sheet / invoice. Returns the cleaned
    string only when it (a) is just digits / operators / parens, (b) actually contains
    an operator, and (c) evaluates to the numeric value we stored. Otherwise ``None``."""
    s = str(raw or '').strip()
    if not s or len(s) > 40 or not _AMOUNT_EXPR_RE.match(s):
        return None
```

Replace with:

```python
def sanitize_amount_expr(raw, numeric_value, base=None):
    """If the user typed a real arithmetic expression for an amount (e.g. ``"20+20"``)
    we keep it verbatim so it can be shown on the sheet / invoice. Returns the cleaned
    string only when it (a) is just digits / operators / parens, (b) actually contains
    an operator, and (c) evaluates to the numeric value we stored. Otherwise ``None``.

    A percent (``"20%"`` / ``"%20"``) is also kept — normalized to ``"20%"`` — but only
    when ``base`` is supplied and ``base * pct/100`` equals the stored ``numeric_value``
    (so it can't be tampered into a lie). Callers that don't pass ``base`` reject percents."""
    s = str(raw or '').strip()
    if not s or len(s) > 40:
        return None
    pct = _parse_percent(s)
    if pct is not None:
        if base is None:
            return None
        expected = round(float(base) * pct / 100.0, 2)
        if abs(expected - float(numeric_value or 0)) > 0.01:
            return None
        return _format_percent(pct)
    if not _AMOUNT_EXPR_RE.match(s):
        return None
```

(The rest of the function — operator check, `eval`, value comparison, `return s` — is unchanged.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_expression_preservation.py -k percent -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full expression suite to confirm no regression**

Run: `python -m pytest tests/test_expression_preservation.py -v`
Expected: PASS (existing arithmetic tests + 4 new percent tests).

- [ ] **Step 7: Commit**

```bash
git add dental_clinic.py tests/test_expression_preservation.py
git commit -m "feat: parse and validate percent discounts in sanitize_amount_expr"
```

---

## Task 2: Server — pass the base at the three discount call sites

**Files:**
- Modify: `dental_clinic.py:2047` (follow-up POST), `:2190` (follow-up PUT), `:3334` (billing POST)
- Test: `tests/test_expression_preservation.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_expression_preservation.py`, after `test_followup_drops_tampered_expression` (~line 90):

```python
def test_followup_keeps_percent_discount(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '03/02/2026', 'treatment_procedure': 'Z',
        'price': 100, 'discount': 20, 'discount_expr': '%20',  # 20% of 100 == 20
        'payment': 0,
    })
    assert r.status_code == 200

    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['discount'] == 20
    assert rows[0]['discount_expr'] == '20%'   # leading-% normalized, preserved


def test_followup_drops_tampered_percent(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '04/02/2026', 'treatment_procedure': 'Z',
        'price': 100, 'discount': 30, 'discount_expr': '20%',  # 20% of 100 != 30
        'payment': 0,
    })
    assert r.status_code == 200
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['discount_expr'] is None
```

Add to the billing group, after `test_billing_round_trip_keeps_expressions` (~line 108):

```python
def test_billing_keeps_percent_discount(client):
    pid = _patient()
    r = client.post('/api/billing', json={
        'patient_id': pid,
        'subtotal': 100, 'discount': 20, 'discount_expr': '20%',  # 20% of subtotal
        'paid_amount': 0,
    })
    assert r.status_code == 200
    row = client.get('/api/billing').get_json()[0]
    assert row['discount_expr'] == '20%'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_expression_preservation.py -k "percent_discount or tampered_percent" -v`
Expected: FAIL — `discount_expr` is `None` (the call sites don't pass `base` yet, so the percent is dropped).

- [ ] **Step 3: Pass `base=price` at the follow-up POST**

`dental_clinic.py:2047`. Find:

```python
    discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount)
```

This exact line appears at both `:2047` (POST) and `:2190` (PUT). Replace **both** occurrences with:

```python
    discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount, base=price)
```

(In both functions `price` is already computed just above via `as_float(data.get('price'))`.)

- [ ] **Step 4: Pass `base=subtotal` at the billing POST**

`dental_clinic.py:3334`. Find:

```python
        discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount)
```

Replace with:

```python
        discount_expr = sanitize_amount_expr(data.get('discount_expr'), discount, base=subtotal)
```

(`subtotal` is computed at `:3293`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_expression_preservation.py -k "percent_discount or tampered_percent" -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_expression_preservation.py
git commit -m "feat: resolve percent discounts against price/subtotal on save"
```

---

## Task 3: Server — keep the percent label on the printed invoice (`amt_cell`)

**Files:**
- Modify: `dental_clinic.py:3460-3465` (`amt_cell` def), `:3501` (discount row)
- Test: `tests/test_expression_preservation.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_expression_preservation.py`, after `test_billing_keeps_percent_discount`:

```python
def test_invoice_renders_percent_discount(client):
    pid = _patient()
    client.post('/api/billing', json={
        'patient_id': pid,
        'subtotal': 100, 'discount': 20, 'discount_expr': '20%',
        'paid_amount': 0,
    })
    bid = client.get('/api/billing').get_json()[0]['id']
    html = client.get(f'/invoice/{bid}').get_data(as_text=True)
    # amt_cell must re-keep the percent (it re-validates with the subtotal as base).
    assert '20% = ' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_expression_preservation.py::test_invoice_renders_percent_discount -v`
Expected: FAIL — `amt_cell` re-sanitizes with no base, so `20%` is dropped and `'20% = '` is absent.

- [ ] **Step 3: Give `amt_cell` a base and forward it**

`dental_clinic.py:3460-3465`. Find:

```python
    def amt_cell(value, expr=None):
        # Show the verbatim expression the user typed (e.g. "20+20") when there is one.
        expr = sanitize_amount_expr(expr, value)
        if expr:
            return f'{escape(expr)} = {currency} {float(value or 0):.2f}'
        return f'{currency} {float(value or 0):.2f}'
```

Replace with:

```python
    def amt_cell(value, expr=None, base=None):
        # Show the verbatim expression the user typed (e.g. "20+20" or "20%") when there is one.
        expr = sanitize_amount_expr(expr, value, base=base)
        if expr:
            return f'{escape(expr)} = {currency} {float(value or 0):.2f}'
        return f'{currency} {float(value or 0):.2f}'
```

- [ ] **Step 4: Pass the subtotal on the discount row**

`dental_clinic.py:3501`. Find:

```python
  <tr><th>{lbl["discount"]}</th><td>{amt_cell(b.get("discount"), b.get("discount_expr"))}</td></tr>
```

Replace with:

```python
  <tr><th>{lbl["discount"]}</th><td>{amt_cell(b.get("discount"), b.get("discount_expr"), base=b.get("subtotal"))}</td></tr>
```

(Leave the `subtotal`/`paid_amount` rows unchanged — they keep `base=None` so percent stays rejected there.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_expression_preservation.py::test_invoice_renders_percent_discount -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_expression_preservation.py
git commit -m "feat: keep percent discount label on printed invoice"
```

---

## Task 4: Client — percent helpers + `evalCalcField` percent branch

**Files:**
- Modify: `templates.py` — add helpers before `evalCalcField` (`:6258`); add a branch inside `evalCalcField`
- Test: `tests/test_expression_preservation.py` (presence guard) + manual browser check

Reminder: write backslashes **doubled** (this is `HTML_TEMPLATE` source).

- [ ] **Step 1: Write the failing presence guard**

Add a new test at the end of `tests/test_expression_preservation.py`:

```python
# ── client wiring (template presence guards) ────────────────────────────────

def test_template_has_percent_support():
    import templates
    html = templates.HTML_TEMPLATE
    assert 'function parsePercent' in html
    assert 'percentBase' in html              # evalCalcField reads el.dataset.percentBase
    assert 'data-percent-base="followup-price"' in html
    assert 'data-percent-base="ef-price"' in html
    assert 'data-percent-base="billing-subtotal"' in html
    assert 'id="billing-subtotal"' in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_expression_preservation.py::test_template_has_percent_support -v`
Expected: FAIL — none of those strings exist yet.

- [ ] **Step 3: Add `parsePercent` / `formatPercent` before `evalCalcField`**

`templates.py:6256-6257` — insert between the end of `evalArithmeticExpr` (`}`) and `function evalCalcField(el) {`:

```javascript
        function parsePercent(raw) {
            const s = String(raw || '').trim();
            if ((s.match(/%/g) || []).length !== 1) return null;
            if (!s.startsWith('%') && !s.endsWith('%')) return null;
            const core = s.replace('%', '').trim();
            if (!/^\\d+(\\.\\d+)?$/.test(core)) return null;
            return parseFloat(core);
        }

        function formatPercent(pct) {
            return String(pct) + '%';   // parseFloat already trimmed trailing zeros
        }
```

- [ ] **Step 4: Add the percent branch inside `evalCalcField`**

`templates.py:6271-6272` — insert the branch immediately after the plain-number `if (...) { ... return; }` block closes and before `const result = evalArithmeticExpr(raw);`.

Find:

```javascript
                return;
            }
            const result = evalArithmeticExpr(raw);
```

Replace with:

```javascript
                return;
            }
            const pct = parsePercent(raw);
            if (pct !== null) {
                const baseEl = el.dataset.percentBase ? document.getElementById(el.dataset.percentBase) : null;
                if (!baseEl) {
                    // Percent only means something against a base (discount fields only).
                    el.classList.add('calc-error');
                    el.classList.remove('calc-ok');
                    return;
                }
                const base = parseCurrency(baseEl.value);
                const amount = Math.max(0, base * pct / 100);
                el.value = amount.toFixed(2);
                el.dataset.expr = formatPercent(pct);   // normalized "20%" for sheet / invoice
                el.classList.remove('calc-error');
                el.classList.add('calc-ok');
                setTimeout(() => el.classList.remove('calc-ok'), 1200);
                return;
            }
            const result = evalArithmeticExpr(raw);
```

- [ ] **Step 5: Run the presence guard (it still fails — attributes added in Task 5)**

Run: `python -m pytest tests/test_expression_preservation.py::test_template_has_percent_support -v`
Expected: still FAIL on the `data-percent-base="..."` asserts (helpers now present). This is fine — Task 5 finishes the wiring. (The `function parsePercent` / `percentBase` asserts now pass.)

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_expression_preservation.py
git commit -m "feat: percent input branch in client calc field"
```

---

## Task 5: Client — wire `data-percent-base`, the subtotal id, and the hint copy

**Files:**
- Modify: `templates.py` — `:2172` (billing subtotal), `:2176` (billing discount), `:2587` (edit discount), `:5613` (add discount), and the discount hint text

- [ ] **Step 1: Add `id` to the billing subtotal input**

`templates.py:2172`. Find:

```html
                            <input type="text" inputmode="decimal" name="subtotal" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off" required>
```

Replace with:

```html
                            <input type="text" inputmode="decimal" name="subtotal" id="billing-subtotal" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off" required>
```

- [ ] **Step 2: Wire + hint the billing discount input**

`templates.py:2175-2176`. Find:

```html
                            <label data-i18n="discount">Discount</label>
                            <input type="text" inputmode="decimal" name="discount" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
```

Replace with:

```html
                            <label data-i18n="discount">Discount <small style="font-weight:400;color:var(--muted);">(or %, e.g. 20%)</small></label>
                            <input type="text" inputmode="decimal" name="discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="billing-subtotal" placeholder="0" autocomplete="off">
```

- [ ] **Step 3: Wire + hint the follow-up EDIT discount input**

`templates.py:2586-2587`. Find:

```html
                        <label data-i18n="discount">Discount <small style="font-weight:400;color:var(--muted);">(or expression)</small></label>
                        <input type="text" inputmode="decimal" id="ef-discount" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
```

Replace with:

```html
                        <label data-i18n="discount">Discount <small style="font-weight:400;color:var(--muted);">(or expression, or % e.g. 20%)</small></label>
                        <input type="text" inputmode="decimal" id="ef-discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="ef-price" placeholder="0" autocomplete="off">
```

- [ ] **Step 4: Wire + hint the follow-up ADD discount input**

`templates.py:5613`. Find:

```javascript
                                <div class="form-group"><label>${t('discount','Discount')} <small style="font-weight:400;color:var(--muted);">(${t('or_expression','or expression')})</small></label><input type="text" inputmode="decimal" name="discount" id="followup-discount" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off"></div>
```

Replace with:

```javascript
                                <div class="form-group"><label>${t('discount','Discount')} <small style="font-weight:400;color:var(--muted);">(${t('or_expression','or expression')}, ${t('or_percent','or % e.g. 20%')})</small></label><input type="text" inputmode="decimal" name="discount" id="followup-discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="followup-price" placeholder="0" autocomplete="off"></div>
```

- [ ] **Step 5: Add the `or_percent` i18n key (EN + AR)**

`templates.py` — find the EN strings object containing `or_expression: 'or expression',` (~`:2993`). Add directly below it:

```javascript
                or_percent: 'or % e.g. 20%',
```

Then find the AR strings object containing `or_expression: 'أو تعبير',` (~`:3348`). Add directly below it:

```javascript
                or_percent: 'أو نسبة مثل ٪20',
```

- [ ] **Step 6: Run the presence guard to verify it now passes**

Run: `python -m pytest tests/test_expression_preservation.py::test_template_has_percent_support -v`
Expected: PASS (all asserts satisfied).

- [ ] **Step 7: Manual browser verification**

Launch the app (`python dental_clinic.py`, or `start.bat`) and open the clinic in the browser; log in if prompted.

1. **Add follow-up:** open a patient → add a follow-up. Set Price `100`, then in Discount type `%20` and press Tab.
   - Expect: Discount field shows `20.00` and briefly flashes the green `calc-ok` border.
   - Save. In the follow-up sheet the Discount column shows `20%` (hover → `₪20.00`); Net = `₪80.00`.
2. **Trailing form / leading form:** repeat with `20%` and confirm identical result.
3. **Edit follow-up:** reopen that row → Discount shows `20%`; change Price to `200`, re-type `%20`, Tab → `40.00`; save → column shows `20%`, net `₪160.00`.
4. **Billing:** Billing tab → Subtotal `100`, Discount `%10`, Tab → `10.00`; create invoice; open the printed invoice (`/invoice/<id>`) → Discount row reads `10% = ₪ 10.00`.
5. **Negative path:** in any price/payment/lab field type `%20` → field turns red (`calc-error`), no resolution. In a discount field type `50%+10` → red.

Record the result honestly in the task notes (pass/fail per step).

- [ ] **Step 8: Commit**

```bash
git add templates.py
git commit -m "feat: wire percent discounts in follow-up and billing forms"
```

---

## Task 6: Docs + full suite

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the feature in `README.md`**

Find the section that describes the follow-up sheet / money fields / expression entry (search the README for "expression" or "discount"). Add a short subsection near it:

```markdown
### Percentage discounts

In any discount field (follow-up Add/Edit, Billing) you can type a percentage instead
of an amount — `%20` or `20%`. It resolves to that percent of the line's base (the
follow-up **price**, or the billing **subtotal**) the moment you leave the field. The
`20%` notation is preserved and shown on the sheet (hover for the ₪ amount) and on the
printed invoice (`20% = ₪ 20.00`), the same way arithmetic expressions like `20+20` are.

Percentages work in discount fields only; typing `%` in price/payment/lab/subtotal/paid
is rejected (the field turns red).
```

If the README tracks a test count, update it to reflect the new tests in `tests/test_expression_preservation.py` (run the suite first to get the number — see Step 2).

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -q`
Expected: PASS — all previously-passing tests plus the new percent tests (8 added across Tasks 1–4). No failures, no errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document percentage discounts"
```

---

## Self-review notes

- **Spec coverage:** percent parse + base validation (Task 1); resolve against price/subtotal on save (Task 2); preserve on printed invoice (Task 3); client resolution + base wiring + hint (Tasks 4–5); README (Task 6). All spec sections mapped.
- **Type/name consistency:** client `parsePercent`/`formatPercent`/`dataset.percentBase` ↔ attribute `data-percent-base`; server `_parse_percent`/`_format_percent`; `sanitize_amount_expr(..., base=...)` signature used identically at all four call sites (3 saves + `amt_cell`). The presence-guard test asserts the exact attribute strings the wiring uses.
- **Edge cases** from the spec (`%150` allowed, base 0 → ₪0, malformed → arithmetic→reject, tamper→drop) are covered by Task 1/2 unit + round-trip tests and the Task 5 manual negative path.
- **No new restrictions** added to existing discount bounds; billing's `discount < 0` guard is untouched.
