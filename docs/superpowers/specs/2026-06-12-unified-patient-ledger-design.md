# Unified Patient Ledger — design spec (2026-06-12)

## Problem

Billing invoices and the follow-up sheet were two **independent** money ledgers.
A billing payment did not reduce the patient's owed balance; a billing charge
never appeared in receivables; yet "Total Collected" summed both. Same clinic
also showed **different Revenue** on desktop vs mobile. Result: a patient could
read "owes 300" and "paid 300" at the same time.

## The single invariant (enforced everywhere, both platforms)

```
Outstanding(patient) = TotalCharged − TotalPaid

  TotalCharged = Σ sheet (price − discount)  +  Σ billing (subtotal − discount)
  TotalPaid    = Σ sheet (payment)           +  Σ billing (paid_amount)

  Outstanding > 0 → owes   |   = 0 → settled   |   < 0 → credit (−Outstanding)
```

Charges **and** payments can be entered from **either** the follow-up sheet or
the billing page. A billing entry may be a charge, a payment, or both; a
**payment-only** billing entry has `subtotal = 0`.

## Decisions (from the user, 2026-06-12)

1. Charges allowed from **both** the sheet and the billing page.
2. **Discard** existing billing test rows on migration (pre-launch).
3. **Credit = overpayment = negative balance.** Remove the separate credit
   system (`credit_used` field, `patient_credit_transactions`, credit-adjustment
   endpoint, "Use credit" UI). Overpayment auto-offsets the next charge.

## Worked example (the acceptance case)

Sheet: price 300, discount 0, payment 100 → charged 300, paid 100.
Billing: payment-only, paid 200 (subtotal 0).
`Outstanding = (300+0) − (100+200) = 0` — shown as **0 everywhere**
(profile, sheet header, billing tab, receivables, payment history).

## Touchpoints

### Desktop (`dental_clinic.py`)
- [ ] `get_patient_balance(cursor, pid)` → `{charged, paid, outstanding, credit}` — new single source of truth.
- [ ] `get_patient_credit_balance` → `balance['credit']`.
- [ ] Billing POST: allow `subtotal == 0`; reject only when `subtotal<=0 AND paid_amount<=0`; drop `credit_used` + credit-txn insert + available-credit check.
- [ ] Billing DELETE: drop credit reversal.
- [ ] Receivables: outstanding from the unified helper.
- [ ] Patient-list balance (`balance_raw`) + full-profile: unified outstanding/credit.
- [ ] Payment-history total: `paid` (sheet + billing payments); drop credit_used column.
- [ ] Dashboard + reports **Revenue** = sheet payments + billing payments, same date basis as mobile.
- [ ] Remove `/credit-adjustment`; keep `/credit` returning computed credit.

### Mobile (`clinic_mobile_app`)
- [ ] `database_service`: `getPatientBalance` (unified); rewrite `getReceivables`, `getBillingAccounts`, dashboard revenue; `getPatientCreditBalance` → unified; drop `recordCreditUsed`/`addCreditAdjustment`/`clearCreditForInvoice`.
- [ ] `billing_record.dart`: `settled = paidAmount` (drop creditUsed); allow subtotal 0.
- [ ] `financial_screen`: Add-Billing sheet supports payment-only; remove "Use credit".
- [ ] `patient_detail_screen`: balance/credit from unified; profile `_runningBalance` already = sheet running balance, but the **header outstanding** must use the unified figure.
- [ ] payment history: drop creditUsed.

## QA / test matrix
- 300/100 sheet + 200 billing-payment → outstanding 0 (desktop pytest + mobile).
- Billing-only charge 150, paid 0 → outstanding 150.
- Overpay (charge 40, pay 100) → outstanding −60, credit 60.
- Payment-only billing entry (subtotal 0, paid 50) accepted; all-zero rejected.
- Desktop Revenue == mobile Revenue for same data.
- Receivables / profile / billing-accounts all report the same outstanding for a patient.
