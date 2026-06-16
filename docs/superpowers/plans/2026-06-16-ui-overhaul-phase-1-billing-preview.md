# UI/UX Overhaul Phase 1 — Real-time Billing Math Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live, read-only "billing math preview" side panel to the Record-Payment form and the patient follow-up entry form, showing net charge, paid, change/overpayment, and the effect on the patient's running balance — updating as the user types, before submit.

**Architecture:** All edits live in `templates.py` (`HTML_TEMPLATE`). One pure function `computeBillingPreview()` does the math; `renderBillingPreview()` paints a `.billing-preview` panel; `wireBillingPreview(formEl, opts)` wires a debounced `input` listener that reads the form's existing `calc-input` fields **without mutating them** (reusing `parsePercent`/`evalArithmeticExpr`/`parseCurrency`). The current balance comes from existing data (follow-up: the loaded profile's signed `outstanding`; billing: a `/api/patients/<id>/full-profile` fetch on patient-select, cached). The panel is styled with Phase 0 tokens (`--surface`, `--surface-border`, `--accent`, `--radius-lg`) and sits beside the inputs, collapsing below them under 720px.

**Tech Stack:** Python 3 / Flask (`render_template_string`), vanilla JS in `HTML_TEMPLATE`, pytest (substring sentinels), Playwright (behavior + math case-table via `page.evaluate`).

**Spec:** `docs/superpowers/specs/2026-06-16-ui-overhaul-phase-1-billing-preview-design.md`

**Branch:** `feat/ui-overhaul-p1` (stacked on `feat/ui-overhaul-p0`).

> ⚠️ **EXECUTION GATE:** Do NOT start until Phase 0 PR #8 is merged to `main`. Then `git checkout feat/ui-overhaul-p1 && git rebase origin/main` (after `git fetch`) before executing. The line numbers below are hints from the pre-rebase tree — locate anchors by content (ids/class names), not absolute lines.

> ⚠️ **templates.py JS-escaping trap** (memory `reference_templates_js_escaping`): `HTML_TEMPLATE` is a normal Python triple-quoted string. Any regex backslash must be written `\\d` / `\\.` so it survives into the rendered JS, and never introduce a bare `'\n'`/`'\t'` literal (use template literals with real line breaks or DOM APIs). Template literals use `${...}` (dollar-brace) which is NOT Jinja (`{{`), so they are safe. After the JS tasks, run the render sweep in Task 7.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `templates.py` | `.billing-preview` CSS; the two panels + field-id additions in markup; EN/AR i18n keys; `computeBillingPreview`/`renderBillingPreview`/`resolveCalcValue`/`previewDebounce`/`wireBillingPreview`; billing patient-select balance fetch + follow-up signed-balance + wire calls. | Modify |
| `tests/test_billing_preview_p1.py` | Substring sentinels: panels, field ids, i18n keys (×2 dicts), function presence, fetch + wire calls. | Create |

No changes to: mobile, `dental_clinic.py` logic, DB, APIs (the `/full-profile` endpoint already exists), or `DentaCare.spec`.

---

## Task 1: Preview panel CSS

**Files:**
- Modify: `templates.py` (in the `<style>` block, near the other `.section-card`/data-surface rules)
- Test: `tests/test_billing_preview_p1.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_billing_preview_p1.py`:

```python
from templates import HTML_TEMPLATE


def test_preview_css_present():
    assert ".billing-preview" in HTML_TEMPLATE
    assert ".form-with-preview" in HTML_TEMPLATE
    # solid surface using the Phase 0 token, never frosted
    assert "var(--surface)" in HTML_TEMPLATE
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_preview_css_present -v`
Expected: FAIL — `.billing-preview` not present.

- [ ] **Step 3: Add the CSS**

In `templates.py`, inside the main `<style>` block (after the `.section-card` rules is a good home), add:

```css
        /* ── Phase 1: live billing math preview ───────────────────────────── */
        .form-with-preview { display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
        .form-with-preview > form { flex: 1 1 360px; min-width: 0; }
        .billing-preview {
            flex: 0 1 260px; min-width: 220px;
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--elev-card);
            padding: 14px 16px;
            font-size: 0.9rem;
        }
        .billing-preview__title {
            font-size: 0.7rem; font-weight: 800; letter-spacing: .08em;
            text-transform: uppercase; color: var(--ink-subtle); margin-bottom: 10px;
        }
        .billing-preview__row {
            display: flex; justify-content: space-between; gap: 12px; padding: 3px 0;
            font-variant-numeric: tabular-nums;
        }
        .billing-preview__row b { font-weight: 700; }
        .billing-preview__row--muted { color: var(--ink-muted); }
        .billing-preview__row--net {
            border-top: 1px solid var(--surface-border); margin-top: 4px; padding-top: 6px;
        }
        .billing-preview__balance {
            display: flex; justify-content: space-between; gap: 12px;
            border-top: 1px solid var(--surface-border); margin-top: 6px; padding-top: 8px;
            font-size: 1.02rem; font-variant-numeric: tabular-nums;
        }
        .billing-preview__balance--owes b { color: var(--warning); }
        .billing-preview__balance--credit b,
        .billing-preview__balance--settled b { color: var(--ok); }
        .billing-preview__hint { color: var(--ink-subtle); font-size: 0.82rem; margin-top: 6px; }
        @media (max-width: 720px) {
            .form-with-preview > form, .billing-preview { flex-basis: 100%; }
        }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_preview_css_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_billing_preview_p1.py
git commit -m "feat(ui-p1): billing-preview panel CSS (P0 tokens, responsive)"
```

---

## Task 2: Billing form — field ids + flex wrapper + panel

The billing Record-Payment form already has `id="billing-subtotal"` (charge) but the discount and paid inputs have no id, and the form isn't wrapped for a side panel.

**Files:**
- Modify: `templates.py` — the `<form id="billing-form">` block (~line 2595) and its inputs (~2615 discount, ~2621 paid)
- Test: `tests/test_billing_preview_p1.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_billing_preview_p1.py`:

```python
def test_billing_form_has_preview_panel_and_field_ids():
    assert 'id="billing-preview"' in HTML_TEMPLATE
    assert 'id="billing-discount"' in HTML_TEMPLATE
    assert 'id="billing-paid"' in HTML_TEMPLATE
    assert 'class="form-with-preview"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_billing_form_has_preview_panel_and_field_ids -v`
Expected: FAIL.

- [ ] **Step 3: Add ids to the discount and paid inputs**

Find (discount input):
```html
                            <input type="text" inputmode="decimal" name="discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="billing-subtotal" placeholder="0" autocomplete="off">
```
Add `id="billing-discount"`:
```html
                            <input type="text" inputmode="decimal" name="discount" id="billing-discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="billing-subtotal" placeholder="0" autocomplete="off">
```

Find (paid input):
```html
                            <input type="text" inputmode="decimal" name="paid_amount" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
```
Add `id="billing-paid"`:
```html
                            <input type="text" inputmode="decimal" name="paid_amount" id="billing-paid" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
```

- [ ] **Step 4: Wrap the form + add the panel**

Find the form open tag:
```html
                <form id="billing-form">
```
Replace with a flex wrapper opening + the form:
```html
                <div class="form-with-preview">
                <form id="billing-form">
```

Find the form close tag (the `</form>` that ends the Record-Payment form, immediately before `</div>` `</details>` ~line 2633-2635):
```html
                    <button class="btn btn-primary" type="submit" data-i18n="record_payment">Record Payment</button>
                </form>
```
Replace with the form close + the panel + wrapper close:
```html
                    <button class="btn btn-primary" type="submit" data-i18n="record_payment">Record Payment</button>
                </form>
                <div class="billing-preview" id="billing-preview" aria-live="polite"></div>
                </div>
```

- [ ] **Step 5: Run to verify it passes + render check**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_billing_form_has_preview_panel_and_field_ids -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_billing_preview_p1.py
git commit -m "feat(ui-p1): billing form field ids + preview panel wrapper"
```

---

## Task 3: Follow-up entry form — flex wrapper + panel

The follow-up form (`#patient-followup-form`, ~line 6509) is built inside a JS template-literal string. Its fields already have ids (`followup-price`, `followup-discount`, `followup-payment`).

**Files:**
- Modify: `templates.py` — the `patient-followup-form` template-literal markup (~6509) and its closing
- Test: `tests/test_billing_preview_p1.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_followup_form_has_preview_panel():
    assert 'id="followup-preview"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_followup_form_has_preview_panel -v`
Expected: FAIL.

- [ ] **Step 3: Wrap the follow-up form + add the panel**

Locate the follow-up form open (inside the template literal):
```html
                        <form id="patient-followup-form">
```
Replace with:
```html
                        <div class="form-with-preview">
                        <form id="patient-followup-form">
```

Locate the matching `</form>` for the follow-up form (the submit button is the last field; the form closes before the surrounding container — confirm by reading the block). Replace:
```html
                        </form>
```
with:
```html
                        </form>
                        <div class="billing-preview" id="followup-preview" aria-live="polite"></div>
                        </div>
```
(If the `</form>` token is ambiguous because of `edit-followup-form`, anchor on the unique surrounding markup of `patient-followup-form` — read ~6509–6614 first and match the exact closing line.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_followup_form_has_preview_panel -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_billing_preview_p1.py
git commit -m "feat(ui-p1): follow-up form preview panel wrapper"
```

---

## Task 4: i18n keys (EN + AR)

The app uses a `t(key, fallback)` helper backed by two dictionaries (EN ~line 3288, AR ~line 3686).

**Files:**
- Modify: `templates.py` — the English strings object and the Arabic strings object
- Test: `tests/test_billing_preview_p1.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_preview_i18n_keys_present_both_langs():
    for key in ("preview_title", "preview_net", "preview_new_balance",
                "preview_owes", "preview_credit", "preview_settled",
                "preview_change", "preview_select_patient", "preview_discount_exceeds"):
        # one definition in the EN dict + one in the AR dict
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_preview_i18n_keys_present_both_langs -v`
Expected: FAIL.

- [ ] **Step 3: Add the EN keys**

In the English strings object (near `subtotal_required: 'Charge',`), add:

```javascript
                preview_title: 'Live summary',
                preview_charge: 'Charge',
                preview_discount: 'Discount',
                preview_net: 'Net charge',
                preview_paid: 'Paid now',
                preview_change: 'Change / overpayment',
                preview_new_balance: 'New balance',
                preview_owes: 'owes',
                preview_credit: 'in credit',
                preview_settled: 'Settled',
                preview_select_patient: 'Select a patient to see the balance',
                preview_discount_exceeds: 'Discount exceeds charge',
```

- [ ] **Step 4: Add the AR keys**

In the Arabic strings object (near `subtotal_required: 'المبلغ',`), add:

```javascript
                preview_title: 'ملخص مباشر',
                preview_charge: 'المبلغ',
                preview_discount: 'الخصم',
                preview_net: 'الصافي بعد الخصم',
                preview_paid: 'المدفوع الآن',
                preview_change: 'الفائض / الباقي للمريض',
                preview_new_balance: 'الرصيد الجديد',
                preview_owes: 'مستحق على المريض',
                preview_credit: 'رصيد دائن',
                preview_settled: 'مسدّد بالكامل',
                preview_select_patient: 'اختر مريضًا لعرض الرصيد',
                preview_discount_exceeds: 'الخصم أكبر من المبلغ',
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_preview_i18n_keys_present_both_langs -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_billing_preview_p1.py
git commit -m "feat(ui-p1): EN/AR i18n keys for billing preview"
```

---

## Task 5: Core JS — compute, format, resolve, render

Pure math + rendering, no wiring yet. Add these in the `<script>` section near the existing calc helpers (`evalCalcField`, `parsePercent`, `evalArithmeticExpr`).

**Files:**
- Modify: `templates.py` — `<script>` block
- Test: `tests/test_billing_preview_p1.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_preview_core_functions_present():
    for fn in ("function computeBillingPreview",
               "function renderBillingPreview",
               "function resolveCalcValue",
               "function previewDebounce"):
        assert fn in HTML_TEMPLATE, f"{fn} missing"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_preview_core_functions_present -v`
Expected: FAIL.

- [ ] **Step 3: Add the core JS**

In the `<script>` block (after `evalArithmeticExpr`/`parsePercent` are defined), add. **Note the `\\d` / `\\.` double-escapes — they must survive into the rendered JS:**

```javascript
        function previewDebounce(fn, ms) {
            let timer;
            return function () { clearTimeout(timer); timer = setTimeout(fn, ms); };
        }

        function fmtPreviewMoney(n) {
            const v = Math.round((Number(n) || 0) * 100) / 100;
            return '₪ ' + v.toFixed(2);
        }

        // Read a calc field's live numeric value WITHOUT mutating it (mirrors evalCalcField).
        function resolveCalcValue(el, base) {
            if (!el) return 0;
            const raw = String(el.value || '').trim();
            if (!raw) return 0;
            if (/^[\\d]*\\.?[\\d]*$/.test(raw)) return parseFloat(raw) || 0;
            const pct = parsePercent(raw);
            if (pct !== null) return base ? Math.max(0, base * pct / 100) : 0;
            const expr = evalArithmeticExpr(raw);
            if (expr !== null) return expr;
            return parseCurrency(raw) || 0;
        }

        // Pure transaction math. balance may be null (no patient selected).
        function computeBillingPreview(o) {
            const charge = Math.max(0, Number(o.charge) || 0);
            const discountRaw = Math.max(0, Number(o.discount) || 0);
            const discount = Math.min(discountRaw, charge);     // capped at charge
            const paid = Math.max(0, Number(o.paid) || 0);
            const net = charge - discount;
            const change = Math.max(0, paid - net);
            const hasBalance = (o.balance !== null && o.balance !== undefined && !isNaN(o.balance));
            const prev = hasBalance ? Number(o.balance) : 0;
            const newBalance = prev + net - paid;
            let state = 'unknown';
            if (hasBalance) {
                if (Math.abs(newBalance) < 0.005) state = 'settled';
                else if (newBalance > 0) state = 'owes';
                else state = 'credit';
            }
            return { charge, discount, net, paid, change,
                     discountExceeds: discountRaw > charge,
                     hasBalance, newBalance, state };
        }

        function renderBillingPreview(panel, r) {
            if (!panel) return;
            const row = (label, val, cls) =>
                `<div class="billing-preview__row ${cls || ''}"><span>${label}</span><b>${val}</b></div>`;
            const rows = [];
            rows.push(row(t('preview_charge', 'Charge'), fmtPreviewMoney(r.charge)));
            if (r.discount > 0) {
                rows.push(row('− ' + t('preview_discount', 'Discount'),
                              '− ' + fmtPreviewMoney(r.discount), 'billing-preview__row--muted'));
            }
            rows.push(row(t('preview_net', 'Net charge'), fmtPreviewMoney(r.net), 'billing-preview__row--net'));
            rows.push(row(t('preview_paid', 'Paid now'), fmtPreviewMoney(r.paid)));
            if (r.change > 0) {
                rows.push(row(t('preview_change', 'Change / overpayment'),
                              fmtPreviewMoney(r.change), 'billing-preview__row--muted'));
            }
            let tail;
            if (r.hasBalance) {
                const word = r.state === 'owes' ? t('preview_owes', 'owes')
                          : r.state === 'credit' ? t('preview_credit', 'in credit') : '';
                const amount = r.state === 'settled'
                    ? t('preview_settled', 'Settled')
                    : word + ' ' + fmtPreviewMoney(Math.abs(r.newBalance));
                tail = `<div class="billing-preview__balance billing-preview__balance--${r.state}">` +
                       `<span>${t('preview_new_balance', 'New balance')}</span><b>${amount}</b></div>`;
            } else {
                tail = `<div class="billing-preview__hint">${t('preview_select_patient', 'Select a patient to see the balance')}</div>`;
            }
            const warn = r.discountExceeds
                ? `<div class="billing-preview__hint">${t('preview_discount_exceeds', 'Discount exceeds charge')}</div>`
                : '';
            panel.innerHTML = `<div class="billing-preview__title">${t('preview_title', 'Live summary')}</div>` +
                              rows.join('') + tail + warn;
        }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_preview_core_functions_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_billing_preview_p1.py
git commit -m "feat(ui-p1): core preview math + render (computeBillingPreview/renderBillingPreview)"
```

---

## Task 6: Wiring — wireBillingPreview, balance sources, call sites

**Files:**
- Modify: `templates.py` — `<script>` block (add `wireBillingPreview`, billing balance fetch), the billing patient-select handler, the follow-up render path (~6439 signed balance, ~6614 wire call), and `DOMContentLoaded`
- Test: `tests/test_billing_preview_p1.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_wiring_present():
    assert "function wireBillingPreview" in HTML_TEMPLATE
    assert "wireBillingPreview(" in HTML_TEMPLATE         # at least one call site
    assert "/full-profile" in HTML_TEMPLATE               # billing balance fetch
    assert "currentFollowupBalanceSigned" in HTML_TEMPLATE  # signed balance for follow-up
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_wiring_present -v`
Expected: FAIL.

- [ ] **Step 3: Add `wireBillingPreview` + billing balance fetch**

In the `<script>` block (after `renderBillingPreview`), add:

```javascript
        let billingPatientBalance = null;   // signed; null = no patient selected

        async function loadBillingPatientBalance(pid) {
            billingPatientBalance = null;
            if (pid) {
                try {
                    const res = await fetch(`/api/patients/${pid}/full-profile`);
                    if (res.ok) {
                        const d = await res.json();
                        billingPatientBalance = parseCurrency(d.outstanding);
                    }
                } catch (e) { billingPatientBalance = null; }
            }
            const form = document.getElementById('billing-form');
            if (form && form.recomputePreview) form.recomputePreview();
        }

        function wireBillingPreview(formEl, opts) {
            if (!formEl || formEl.dataset.previewWired) return;
            formEl.dataset.previewWired = '1';
            const panel = document.getElementById(opts.panelId);
            const byId = id => document.getElementById(id);
            const recompute = () => {
                const charge = resolveCalcValue(byId(opts.chargeId));
                const discount = resolveCalcValue(byId(opts.discountId), charge);
                const paid = resolveCalcValue(byId(opts.paidId));
                const balance = opts.getBalance ? opts.getBalance() : null;
                renderBillingPreview(panel, computeBillingPreview({ charge, discount, paid, balance }));
            };
            const debounced = previewDebounce(recompute, 120);
            [opts.chargeId, opts.discountId, opts.paidId].forEach(id => {
                const el = byId(id);
                if (el) { el.addEventListener('input', debounced); el.addEventListener('blur', recompute); }
            });
            formEl.recomputePreview = recompute;   // patient-select can refresh
            recompute();
        }
```

- [ ] **Step 4: Wire the billing form (on load) + patient-select fetch**

In the `DOMContentLoaded` handler (where `wireCalcInputs(document)` runs), add:

```javascript
            const billingForm = document.getElementById('billing-form');
            if (billingForm) {
                wireBillingPreview(billingForm, {
                    chargeId: 'billing-subtotal', discountId: 'billing-discount', paidId: 'billing-paid',
                    panelId: 'billing-preview', getBalance: () => billingPatientBalance
                });
            }
            const billingPatientSel = document.getElementById('billing-patient-select');
            if (billingPatientSel) {
                billingPatientSel.addEventListener('change', e => loadBillingPatientBalance(e.target.value));
            }
```

- [ ] **Step 5: Add the signed follow-up balance + wire the follow-up form**

Find (the floored balance, ~line 6439):
```javascript
            currentFollowupBalance = Math.max(0, parseCurrency(profile.outstanding || 0));
```
Add a signed sibling immediately after it:
```javascript
            currentFollowupBalanceSigned = parseCurrency(profile.outstanding || 0);
```
Declare `currentFollowupBalanceSigned` next to the existing `currentFollowupBalance` declaration (a `let`/`var` at the same scope — match how `currentFollowupBalance` is declared).

Find where the follow-up form's submit listener is attached (~line 6614):
```javascript
                document.getElementById('patient-followup-form').addEventListener('submit', async (e) => {
```
Immediately **before** that line, add the wire call:
```javascript
                wireBillingPreview(document.getElementById('patient-followup-form'), {
                    chargeId: 'followup-price', discountId: 'followup-discount', paidId: 'followup-payment',
                    panelId: 'followup-preview', getBalance: () => currentFollowupBalanceSigned
                });
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_billing_preview_p1.py::test_wiring_present -v`
Expected: PASS. Then the whole file: `python -m pytest tests/test_billing_preview_p1.py -v` → all green.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_billing_preview_p1.py
git commit -m "feat(ui-p1): wire live preview into billing + follow-up forms"
```

---

## Task 7: Verification — render sweep, full suite, Playwright (math + UI)

**Files:** none (verification only; commit any fixes).

- [ ] **Step 1: Render sweep (the escaping trap)**

Run (PowerShell-safe via a temp file is fine; inline shown here):
```bash
python -c "from flask import Flask, render_template_string; from templates import HTML_TEMPLATE; a=Flask(__name__); a.app_context().push(); h=render_template_string(HTML_TEMPLATE, SYSTEM_NAME='D', CLINIC_NAME='C', DOCTOR_NAME='Dr', ALLOW_OFFLINE_ACTIVATION=False); print('RENDER OK', 'billing-preview' in h, 'computeBillingPreview' in h)"
```
Expected: `RENDER OK True True` (no Jinja/syntax error). If it throws, a `\n`/backslash escaped wrong — fix the offending JS line.

- [ ] **Step 2: Full suite stays green**

Run: `python -m pytest tests/` then check `$LASTEXITCODE` (summary suppressed; 0 = green).
Expected: exit 0. No server behavior changed.

- [ ] **Step 3: Playwright — math case table via `page.evaluate`**

Render the portal to a temp file (as in the P0 smoke), load it, and exercise the pure function with a case table:

```python
cases = [
    # charge, discount, paid, balance -> net, change, state, newBalance
    (500, 100, 300, 0,    400, 0,   'owes',    100),
    (500, 100, 400, 0,    400, 0,   'settled', 0),
    (500, 100, 500, 0,    400, 100, 'credit',  -100),
    (0,   0,   200, 300,  0,   200, 'owes',    100),   # payment-only reduces balance
    (100, 200, 0,   0,    0,   0,   'settled', 0),     # discount capped at charge
]
for c in cases:
    r = page.evaluate("(a) => computeBillingPreview({charge:a[0],discount:a[1],paid:a[2],balance:a[3]})", c)
    assert round(r["net"],2) == c[4] and round(r["change"],2) == c[5]
    assert r["state"] == c[6] and round(r["newBalance"],2) == c[7]
```
Expected: all assertions pass (real math coverage). Also assert `computeBillingPreview({charge:1,discount:0,paid:0,balance:None})` → `hasBalance False`, `state 'unknown'`.

- [ ] **Step 4: Playwright — live UI, both themes**

With the rendered page: set the billing fields' values, dispatch `input`, and assert `#billing-preview` text contains the right `₪` amounts and the balance word; repeat in `data-theme="dark"`. Confirm no console errors (ignore `file://` `/api/...` fetch failures). Screenshot light + dark and view them.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "test(ui-p1): render sweep + Playwright math/UI verification notes" || echo "nothing to commit"
```

---

## Task 8 (deferred to user): packaged-exe check

After merge, rebuild `installer\Output\DentaCare-Setup.exe` and confirm the preview renders/updates in the WebView2 shell. User-side step.

---

## Self-Review

**1. Spec coverage:**
- Reusable component (compute/render/wire) → Tasks 5–6. ✓
- Both surfaces (billing + follow-up) → Tasks 2, 3, 6. ✓
- Content: net / paid / change / balance effect → Task 5 (`computeBillingPreview` + `renderBillingPreview`). ✓
- Balance source: follow-up signed `outstanding` (not floored), billing `/full-profile` fetch → Task 6. ✓
- Edge cases: discount capped, overpay=credit, payment-only, lab-expense excluded (preview reads only charge/discount/paid — never `followup-lab-expense`), invalid→0 → Task 5. ✓
- Side panel + responsive + P0 tokens + EN/AR → Tasks 1, 4. ✓
- Read-only (no mutation) → Task 5 `resolveCalcValue` does not write `el.value`. ✓
- Verification (render sweep, suite, Playwright math + UI both themes) → Task 7. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has complete code. The only "locate by content" notes are anchor-finding aids (line numbers will drift post-rebase), each with the exact literal to match.

**3. Type/name consistency:** `computeBillingPreview` returns `{charge,discount,net,paid,change,discountExceeds,hasBalance,newBalance,state}` — consumed verbatim by `renderBillingPreview` and the Task 7 case table. `wireBillingPreview` opts `{chargeId,discountId,paidId,panelId,getBalance}` match both call sites. `resolveCalcValue(el, base)` signature matches its uses (discount passes `charge` as base). `formEl.recomputePreview` set in Task 6 Step 3 and called in Step 4's `loadBillingPatientBalance`. Field ids (`billing-subtotal`/`billing-discount`/`billing-paid`, `followup-price`/`followup-discount`/`followup-payment`) match the markup tasks. Panel ids (`billing-preview`, `followup-preview`) consistent across CSS/markup/wiring/tests.

---

## Execution Handoff

(Gated on Phase 0 PR #8 merge + rebase. Then choose subagent-driven or inline execution.)
