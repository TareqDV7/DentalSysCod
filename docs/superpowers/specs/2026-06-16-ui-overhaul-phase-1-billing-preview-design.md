# UI/UX Overhaul — Phase 1: Real-time Billing Math Preview

**Date:** 2026-06-16
**Status:** Design approved (scope + content + layout); spec pending final user sign-off
**Branch:** `feat/ui-overhaul-p1` (stacked on `feat/ui-overhaul-p0` — P1 uses the P0 tokens; rebase onto `main` after PR #8 merges)
**Predecessors:** Approved 4-phase overhaul plan (memory `project_ui_overhaul_plan`) and Phase 0 (foundation + shared chrome, PR #8). This is Phase 1 of 4 — the **proof slice**.

---

## 1. Context & Why

Three forms in the desktop portal take money — Charge/Price, Discount, Payment — and feed the unified patient ledger (`get_patient_balance`: `Outstanding = Σcharges − Σpayments`):

- **Billing → Record Payment** (`#billing-form`): `subtotal` (charge), `discount`, `paid_amount`.
- **Patient follow-up entry** (`#patient-followup-form`): `price`, `discount`, `lab_expense`, `payment`.
- **Edit follow-up** (`#edit-followup-form`): same fields (out of scope this phase).

A `calc-input` engine (`evalCalcField`) already exists, but it only resolves **one field at a time, in place, on blur** — `"20%"` → `"100.00"`, flashing green/red. It computes **no cross-field result**: no net charge, no change due, and nothing about the patient's balance. The user commits the entry blind and only learns the outcome *after* submitting (in the history table / balance).

Phase 1 adds a **live, read-only breakdown** of the whole transaction and its effect on the patient's balance — the "proof slice" that demonstrates the overhaul's value on the highest-stakes interaction (money).

---

## 2. Goals & Non-Goals

### Goals
1. A reusable preview component that updates **as the user types** (debounced), reading the form's existing calc fields **without mutating them**.
2. Show: **net charge** (charge − discount), **paid now**, **change/overpayment**, and the **effect on the patient's running balance** (owes / settled / in credit).
3. Wire it into **two** surfaces: the billing Record-Payment form and the patient follow-up entry form.
4. Visual continuity with Phase 0 (P0 tokens, both themes, EN/AR, RTL, ₪).

### Non-Goals (deferred)
- The edit-follow-up modal (`#edit-followup-form`) — the component is reusable there, but wiring it is a one-line follow-on, not part of the slice.
- Any change to how charges/payments are **stored or computed server-side** — the preview mirrors existing ledger math, it does not change it.
- Mobile (Flutter). Desktop `templates.py` only.
- New billing features (line items, multi-charge invoices, etc.).

---

## 3. Locked Design Decisions (from brainstorm)

| Decision | Choice |
|---|---|
| Scope | **Both** target forms (billing Record-Payment + follow-up entry), built as one reusable component |
| Content | **Full**: net charge, paid now, change/overpayment, **and** effect on patient balance |
| Layout | **Side panel** beside the inputs; collapses **below** the inputs under ~720px |
| Balance source | Reuse existing data — no new endpoint (see §5) |
| Math semantics | Derived from the unified ledger; overpay = credit (negative balance) |
| Styling | Phosphor/P0 tokens (`--surface`, `--surface-border`, `--accent`, `--radius-lg`), solid surface (not glass), both themes, bilingual |
| Mutation | Preview is **read-only** — never overwrites the user's field values (the existing `evalCalcField` still normalizes on blur) |

---

## 4. The Component (one clear unit)

`wireBillingPreview(formEl, opts)` — a self-contained JS unit added to `HTML_TEMPLATE`'s script section.

- **What it does:** on `input` (debounced ~120ms) it reads the mapped calc fields, computes the breakdown (§6), and renders into a sibling `.billing-preview` panel. Idempotent wiring (guards against double-binding, like `wireCalcInputs`).
- **Interface:**
  ```
  wireBillingPreview(formEl, {
    chargeId, discountId, paidId,   // field ids (charge/price, discount, payment)
    panelId,                        // the .billing-preview container to render into
    getBalance: () => number|null   // current patient outstanding, or null if unknown
  })
  ```
- **Reads values via** the existing helpers `parseCurrency`, `parsePercent` (with the field's `data-percent-base`), and `evalArithmeticExpr` — reused, not reimplemented. No server round-trip of its own.
- **Renders** labelled rows; when `getBalance()` returns `null` (no patient selected yet) the balance row shows a "select a patient" hint and the per-transaction math still displays.

This keeps the math in one testable place and the two call sites trivial.

---

## 5. Data Flow — current balance

No new endpoint; reuse what each surface already has:

- **Follow-up entry:** the sheet already loads the patient profile (which carries `outstanding`). `getBalance` returns the **raw signed `outstanding`** — NOT the existing `currentFollowupBalance` (templates.py ~6439), which is floored at 0 via `max(0, …)` and would hide an existing credit. The preview needs the signed value so an already-in-credit patient renders correctly.
- **Billing form:** on `#billing-patient-select` change, fetch `/api/patients/<id>/full-profile` (already returns `outstanding`), cache the signed value in a module variable; `getBalance` returns the cached value. Re-fetch on patient change; `null` until a patient is chosen.

Both surfaces therefore feed the preview the **same signed-balance semantics** (negative = credit), so the "new balance" line is consistent across forms.

---

## 6. The Math + Edge Cases (mirrors the unified ledger)

Let `charge`, `discount`, `paid` be the resolved field values; `bal` = current outstanding (or `null`).

- `net = max(0, charge − discount)` — discount capped at charge. If `discount > charge`, show a subtle "discount exceeds charge" hint.
- `change = max(0, paid − net)` — shown as "Change / overpayment ₪X" when positive.
- `newBalance = bal + net − paid` (only when `bal !== null`):
  - `> 0` → **"Patient owes ₪X"** (amber `--warning`)
  - `== 0` → **"Settled"** (ok `--ok`)
  - `< 0` → **"In credit ₪X"** (green `--ok`) — negative balance = credit, matching the unified ledger.
- **Payment-only** (charge 0): net 0 → pure balance reduction / credit.
- **Lab expense is intentionally excluded** from the patient-facing math. Per the unified ledger, the patient balance is `price − discount − payment`; `lab_expense` is a clinic cost (it affects clinic profit, not what the patient owes), so the follow-up preview ignores it.
- **Invalid / blank** expression in a field: that input contributes 0 and its row shows "—"; the panel never throws.
- Currency ₪, 2 decimals, `tabular-nums`.

---

## 7. UI — Side Panel

- Markup: a `.billing-preview` panel adjacent to each form, inside a flex wrapper so it sits **beside** the inputs ≥720px and **stacks below** under 720px (`flex-wrap` + min-width, or a container query).
- Solid surface using P0 tokens: `background: var(--surface)`, `border: 1px solid var(--surface-border)`, `border-radius: var(--radius-lg)`, subtle `--elev-card`. Accent rule line / emphasis uses `--accent`; status colors use `--warning`/`--ok`.
- Rows: Charge, − Discount (with resolved %/expr echoed), Net charge (rule above), Paid now, Change (only if > 0), and the emphasized **New balance** line.
- Fully bilingual (`data-i18n` keys added to both EN + AR dictionaries), RTL-aware (logical properties), legible in light **and** dark.

---

## 8. Risks & Decisions to Confirm

1. **`templates.py` JS-escaping trap.** P1 adds real inline `<script>` (unlike P0's CSS-only edits), so every `'\n'`/backslash must be double-escaped and the change render-checked (node/`render_template_string` sweep) — see memory `reference_templates_js_escaping`.
2. **Stacked on an unmerged P0.** Implementation must not start until PR #8 merges; then rebase `feat/ui-overhaul-p1` onto `main` (`git pull` first). The spec/plan are safe to write now.
3. **`full-profile` fetch cost.** One small fetch per patient-select on the billing form; cache to avoid refetching while the user edits. Acceptable.
4. **Decimal/locale parsing.** Reuse `parseCurrency` exactly so the preview and the server agree on the resolved numbers (no second parser).

---

## 9. Verification

- **pytest** (`tests/test_billing_preview_p1.py`): assert the two `.billing-preview` panels, the new i18n keys (EN + AR), and `wireBillingPreview` are present in `HTML_TEMPLATE`; full suite stays green.
- **Render check:** `render_template_string(HTML_TEMPLATE, …)` succeeds (the escaping-trap sweep).
- **Playwright behavior smoke (light + dark, both forms):** type charge `500`, discount `20%`, paid `300` → panel shows Net `₪400`, Paid `₪300`, and "owes ₪100" against a seeded balance; overpay shows credit; payment-only shows balance reduction; no console errors.
- **Offline:** no new network beyond the existing `full-profile` endpoint.

---

## 10. Units Touched

- `templates.py` — two `.billing-preview` panels (markup), the `wireBillingPreview` component + wiring calls, CSS for the panel, EN/AR i18n keys, and the billing-form patient-select balance fetch/cache.
- `tests/test_billing_preview_p1.py` (new).
- No Python logic, DB, API additions, or mobile changes.

---

## 11. Next Step After This Spec

On approval → invoke **writing-plans** to produce the ordered, testable implementation plan. Implementation begins only after PR #8 (Phase 0) merges and this branch is rebased onto `main`.
