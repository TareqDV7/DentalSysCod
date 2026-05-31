# Percentage discounts — design

## Goal

Let the user enter a discount as a percentage. Typing `%20` (or `20%`) in a discount
field sets the discount to 20% of that line's base amount, and the `20%` notation is
preserved on the sheet and the printed invoice — the same way the arithmetic
expression `20+20` is already preserved today.

Scope: the **follow-up Add** form, the **follow-up Edit** form, and the **Billing**
invoice form.

## Existing mechanics (do not change)

- Money fields are `class="calc-input" data-calc-field="1"` text inputs. On blur (and
  via a capture-phase submit interceptor at `templates.py:6359`), `evalCalcField(el)`
  evaluates the value: a plain number is left as-is; an arithmetic expression
  (`^[0-9\s+\-*/(). ]+$`) is evaluated by `evalArithmeticExpr`, the resolved number is
  written back into the field, and the verbatim string is stashed in `el.dataset.expr`.
- On submit, `calcExprOf(el)` returns the preserved expression and the numeric value is
  read from the (now-resolved) field. Both are POSTed: `discount` + `discount_expr`.
- Server `sanitize_amount_expr(raw, numeric_value)` (`dental_clinic.py:1249`) keeps a
  `*_expr` string **only** when it is digits/operators/parens, contains a real operator,
  and evaluates to the stored number — otherwise `None` (bare numbers and tampered
  values are dropped). This honesty check is covered by `tests/test_expression_preservation.py`.
- Discount is an absolute amount: net due = `price − discount` (follow-up),
  `total = max(0, subtotal − discount)` (billing).
- Display: on-screen sheet via `fmtAmount(num, expr)` → `20+20` with a `₪` tooltip
  (`templates.py:5751`); printed billing invoice via `amt_cell(value, expr)` →
  `20+20 = ₪ 20.00` (`dental_clinic.py:3460`).

## Why percent is different from arithmetic

A percent has no fixed value on its own — `20%` only means something relative to a
**base** (price or subtotal). So:

1. The client must know each discount field's base to resolve `%20` → an amount.
2. The server's honesty check needs the base too: keep `20%` only when
   `base × pct/100 ≈ stored discount`. Without the base it cannot verify, so percent is
   rejected for any field that doesn't supply one (price/payment/lab/subtotal/paid).

Normalization: both `%20` and `20%` are stored/displayed as `20%`; trailing zeros are
trimmed (`20.0` → `20`, `12.50` → `12.5`).

### Gotcha

`parseCurrency("20%")` returns `20` (literal — `parseFloat` stops at `%` and there's no
arithmetic operator to trigger expression eval). So a percent field **must** be resolved
by `evalCalcField` before any `parseCurrency`/`FormData` read. The capture-phase submit
interceptor already guarantees this on submit (it runs before each form's own handler);
on blur it's direct. No change to `parseCurrency`.

## Client design (`templates.py`)

- **`parsePercent(raw)`** helper: returns the percent number when `raw` is exactly one
  `%` (leading or trailing) wrapping a plain number, else `null`. Rejects `50%+10`,
  `%-20`, `20%%`, bare `%`.
- **`evalCalcField` extension**: before the arithmetic branch, if `parsePercent(raw)`
  matches:
  - If `el` has no `data-percent-base` → treat as error (`calc-error`), since percent is
    meaningless without a base.
  - Else resolve the base field's current number (reuse `evalArithmeticExpr`/`parseFloat`
    so it works whether or not the base was already resolved), compute
    `amount = base × pct / 100`, write `amount.toFixed(2)` into the field, and set
    `el.dataset.expr` to the normalized `"20%"`. Mark `calc-ok`.
  - Base 0/empty → amount `0`; `el.dataset.expr` still `"20%"` (honest: 20% of 0 is 0).
- **Wire bases** via a `data-percent-base="<id>"` attribute:
  - `#followup-discount` → `#followup-price`
  - `#ef-discount` → `#ef-price`
  - billing `[name="discount"]` → `#billing-subtotal` (add `id="billing-subtotal"` to the
    billing subtotal input)
- **Hint copy**: extend the `(or expression)` small-text to mention `%` (EN + AR i18n
  keys).

`setAmt` (edit-form loader, `templates.py:5798`) needs no change — it already loads a
stored `*_expr` back as the field's text and re-wires calc inputs, so a saved `20%`
round-trips through `evalCalcField` on next blur/submit.

## Server design (`dental_clinic.py`)

- **`sanitize_amount_expr(raw, numeric_value, base=None)`** — add optional `base`:
  - New `_parse_percent(s)` mirrors the client: one `%` (leading/trailing) + plain number.
  - When `raw` is a percent: return `None` if `base is None`; else keep the normalized
    `"<pct>%"` only when `abs(base × pct/100 − numeric_value) <= 0.01` (same tolerance and
    tamper-drop behavior as the arithmetic path). The stored money amount is unchanged —
    the percent string is only a validated display label.
  - Arithmetic and rejection paths are otherwise untouched; the `len(s) > 40` guard still
    applies.
- **Pass the base** at the discount call sites only:
  - follow-up POST (`~2047`) and PUT (`~2190`): `base=price`
  - billing POST (`~3334`): `base=subtotal`
  - All other `*_expr` calls keep `base=None` → percent rejected there.
- **`amt_cell(value, expr=None, base=None)`** — forward `base` to `sanitize_amount_expr`
  and pass `b.get("subtotal")` for the **discount** row only (`dental_clinic.py:3501`).
  Without this the re-validation on the printed invoice has no base and would silently
  drop a stored `20%`.

The client-side patient-statement print (`fmtAmount`/`amtCellHtml`) displays the stored
`discount_expr` as-is (no re-validation), so `20%` already renders there.

## Edge cases

| Input | Result |
|-------|--------|
| `%20`, `20%`, `12.5%` | resolved to `pct` of base; stored/shown as `20%` / `12.5%` |
| base 0 / empty | amount `0`, label `20%` kept (honest) |
| `%150` | discount > base; allowed (matches today's behavior for an oversized absolute discount; billing keeps its `discount < 0` guard) |
| `50%+10`, `%-20`, `20%%`, bare `%` | not a clean percent → arithmetic path → rejected (field turns red), unchanged |
| tampered: `discount=30` sent with `discount_expr="20%"`, price `100` | `20 ≠ 30` → expr dropped (`None`) |

## Testing

Extend `tests/test_expression_preservation.py` (pytest), following the existing structure:

- **Sanitizer units**: `sanitize_amount_expr('20%', 20, base=100) == '20%'`;
  `'%20'` normalizes to `'20%'`; `'12.5%'` with base 80 → value 10 kept;
  mismatch (`'20%', 30, base=100`) → `None`; no base (`'20%', 20`) → `None`;
  unsafe/garbage still `None`.
- **Follow-up round-trip**: POST `price=100, discount=20, discount_expr='%20'` →
  GET `followups` and `invoice-summary` return `discount_expr == '20%'`.
- **Billing round-trip**: POST `subtotal=100, discount=20, discount_expr='20%'` →
  GET `billing` returns `discount_expr == '20%'`.
- **Tamper drop**: follow-up POST `discount=30, discount_expr='20%'` (price 100) →
  stored `discount_expr is None`.
- **Invoice render**: the billing invoice for a `20%` row shows `20% = ₪ 20.00`
  (exercises `amt_cell` with base).

Inline JS is not unit-tested in this repo (consistent with the existing expression
feature); the field behavior is verified manually and reported honestly.

## Files

| File | Change |
|------|--------|
| `dental_clinic.py` | `_parse_percent` + `base` param in `sanitize_amount_expr`; base at 3 discount call sites; `base` param in `amt_cell` + subtotal on the discount row |
| `templates.py` | `parsePercent`; percent branch in `evalCalcField`; `data-percent-base` on 3 discount inputs + `id="billing-subtotal"`; hint copy (EN/AR) |
| `tests/test_expression_preservation.py` | percent unit + round-trip + tamper + invoice tests |
| `README.md` | document percentage discounts |
