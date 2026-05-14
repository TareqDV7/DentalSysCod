import requests, json, sys
BASE = "http://localhost:5000"

OK="PASS"; BAD="FAIL"
bugs = []

def check(label, ok, got, expected=None, note=""):
    tag = OK if ok else BAD
    exp_str = f" | expected={expected}" if expected is not None else ""
    print(f"  [{tag}] {label}")
    print(f"         got={got}{exp_str}{' | '+note if note else ''}")
    if not ok:
        bugs.append((label, got, expected, note))

def near(a, b, eps=0.01):
    return abs(float(a or 0) - float(b or 0)) < eps

patients = requests.get(f"{BASE}/api/patients").json()
ali  = next(p for p in patients if p["first_name"]=="Ali")
sara = next(p for p in patients if p["first_name"]=="Sara")
p1, p2 = ali["id"], sara["id"]

# ============================================================
print("\n" + "="*60)
print("BLOCK 1: SUMMARY REPORT -- math accuracy")
print("="*60)
s = requests.get(f"{BASE}/api/reports/summary").json()

check("SUMMARY: revenue = sum(payments)=780",     near(s["revenue"], 780),          s["revenue"], 780)
check("SUMMARY: expenses total = 2800",           near(s["expenses"], 2800),         s["expenses"], 2800)
check("SUMMARY: expenses_paid = 2500",            near(s["expenses_paid"], 2500),    s["expenses_paid"], 2500)
check("SUMMARY: expenses_postponed = 300",        near(s["expenses_postponed"], 300),s["expenses_postponed"], 300)
check("SUMMARY: profit = revenue - expenses",     near(s["profit"], s["revenue"]-s["expenses"]),
      f"{s['profit']} = {s['revenue']}-{s['expenses']}")
check("SUMMARY: clinic_gross_profit = 1650",      near(s["clinic_gross_profit"], 1650), s["clinic_gross_profit"], 1650)
check("SUMMARY: lab_expenses = 150",              near(s["lab_expenses"], 150),      s["lab_expenses"], 150)

# ============================================================
print("\n" + "="*60)
print("BLOCK 2: WEEKLY REPORT -- math accuracy")
print("="*60)
w = requests.get(f"{BASE}/api/reports/weekly?start=04/05/2026&end=10/05/2026").json()

check("WEEKLY: revenue in Mon-Sun range = 350",   near(w["revenue"], 350),  w["revenue"], 350)
check("WEEKLY: clinic_gross_profit = 700",        near(w["clinic_gross_profit"], 700), w["clinic_gross_profit"], 700)
check("WEEKLY: expenses = 2300",                  near(w["expenses"], 2300), w["expenses"], 2300)
check("WEEKLY: profit = revenue - expenses",      near(w["profit"], w["revenue"]-w["expenses"]),
      f"{w['profit']} vs {w['revenue']}-{w['expenses']}")
check("WEEKLY: week_start = Monday 04/05",        w.get("week_start","").endswith("-04"),  w.get("week_start"), "2026-05-04")
check("WEEKLY: week_end = Sunday 10/05",          w.get("week_end","").endswith("-10"),    w.get("week_end"),   "2026-05-10")

dup = "follow_ups" in w and "followups" in w
check("WEEKLY: no duplicate follow_ups/followups field", not dup,
      f"follow_ups={w.get('follow_ups')} followups={w.get('followups')}",
      "only one key", "duplicate key = response noise")

check("WEEKLY: patient_count = 2",               w.get("patient_count",0) == 2,  w.get("patient_count"), 2)
print(f"         invoice_count={w.get('invoice_count')}  (informational)")

# ============================================================
print("\n" + "="*60)
print("BLOCK 3: WEEKLY -- Saturday edge case (date range spanning Sat 03/05)")
print("="*60)
w_sat = requests.get(f"{BASE}/api/reports/weekly?start=03/05/2026&end=10/05/2026").json()
print(f"  When start=03/05(Sat): week_start={w_sat.get('week_start')} week_end={w_sat.get('week_end')}")
print(f"  revenue={w_sat['revenue']}  (with Sat entries included=430, excluded=350)")
sat_included = near(w_sat["revenue"], 430)
check("WEEKLY: Sat 03/05 entries included when user specifies start=03/05",
      sat_included, w_sat["revenue"], 430,
      "BUG if 350: auto-week-shift silently excludes user-specified Sat dates")

# ============================================================
print("\n" + "="*60)
print("BLOCK 4: RECEIVABLES -- discount correctness")
print("="*60)
rec = requests.get(f"{BASE}/api/reports/receivables").json()
rows = rec.get("rows", rec if isinstance(rec, list) else [])

ali_rec  = next((r for r in rows if r.get("patient_id")==p1), None)
sara_rec = next((r for r in rows if r.get("patient_id")==p2), None)

if ali_rec:
    check("RECEIVABLES: Ali total_to_pay = 1150",     near(ali_rec["total_to_pay"], 1150), ali_rec["total_to_pay"], 1150)
    check("RECEIVABLES: Ali total_paid = 680",        near(ali_rec["total_paid"], 680),    ali_rec["total_paid"], 680)
    check("RECEIVABLES: Ali outstanding accounts for 20 discount (=450)",
          near(ali_rec["outstanding"], 450), ali_rec["outstanding"], 450,
          "BUG if 470: discount not subtracted from receivables outstanding")

if sara_rec:
    check("RECEIVABLES: Sara total_to_pay = 650",     near(sara_rec["total_to_pay"], 650), sara_rec["total_to_pay"], 650)
    check("RECEIVABLES: Sara total_paid = 100",       near(sara_rec["total_paid"], 100),   sara_rec["total_paid"], 100)
    check("RECEIVABLES: Sara outstanding accounts for 400 discount (=150)",
          near(sara_rec["outstanding"], 150), sara_rec["outstanding"], 150,
          "BUG if 550: fully-discounted 400 incorrectly counted as owed")

correct_total = 450 + 150
check("RECEIVABLES: total_receivables = 600 (with discounts)",
      near(rec["total_receivables"], correct_total), rec["total_receivables"], correct_total,
      "BUG if 1020: sum of outstanding ignores discounts")

# ============================================================
print("\n" + "="*60)
print("BLOCK 5: FOLLOWUP RUNNING BALANCE -- remaining_amount math")
print("="*60)
fu_ali  = requests.get(f"{BASE}/api/patients/{p1}/followups").json()
fu_sara = requests.get(f"{BASE}/api/patients/{p2}/followups").json()

# Ali order of insertion (by ID): Filling(150,pay150), RootCanal(400,pay200),
#   Extraction(100,disc20,pay80), Crown(500,lab150,pay250), Checkup(0), FreeService(100,disc200)
# Skip edge-case entries; look at the Crown (4th entry = highest ID among the first 4)
fu_ali_core = [f for f in fu_ali if f["treatment_procedure"] not in ("Checkup","FreeService")]
last_ali = sorted(fu_ali_core, key=lambda x: x["id"])[-1]
print(f"  Ali last core entry: proc={last_ali['treatment_procedure']} price={last_ali['price']} disc={last_ali.get('discount')} pay={last_ali['payment']} remaining={last_ali['remaining_amount']}")
check("FOLLOWUP: Ali last remaining_amount = 450",
      near(last_ali["remaining_amount"], 450), last_ali["remaining_amount"], 450,
      "BUG: discount not subtracted in running balance")

fu_sara_core = [f for f in fu_sara]
last_sara = sorted(fu_sara_core, key=lambda x: x["id"])[-1]
print(f"  Sara last entry: proc={last_sara['treatment_procedure']} price={last_sara['price']} disc={last_sara.get('discount')} pay={last_sara['payment']} remaining={last_sara['remaining_amount']}")
check("FOLLOWUP: Sara last remaining_amount = 150",
      near(last_sara["remaining_amount"], 150), last_sara["remaining_amount"], 150,
      "BUG: fully-discounted entry inflates Sara balance")

# ============================================================
print("\n" + "="*60)
print("BLOCK 6: BILLING RECORDS -- discount & balance")
print("="*60)
bills = requests.get(f"{BASE}/api/billing").json()
if isinstance(bills, list):
    b_full = next((b for b in bills if near(b.get("amount",0), 600) and b["patient_id"]==p1), None)
    b_disc = next((b for b in bills if near(b.get("amount",0), 400) and b["patient_id"]==p1), None)
    b_pend = next((b for b in bills if b.get("patient_id")==p2), None)
    if b_full:
        check("BILLING: full-paid balance_due = 0",    near(b_full["balance_due"], 0),   b_full["balance_due"], 0)
        check("BILLING: full-paid status = paid",      b_full["payment_status"]=="paid", b_full["payment_status"])
    if b_disc:
        check("BILLING: partial payment balance = 200", near(b_disc["balance_due"], 200), b_disc.get("balance_due"), 200)
        check("BILLING: discount stored = 100",         near(b_disc.get("discount",0), 100), b_disc.get("discount"), 100)
    if b_pend:
        check("BILLING: pending invoice status",       b_pend["payment_status"]=="pending", b_pend["payment_status"])
        check("BILLING: pending balance_due = 150",    near(b_pend["balance_due"], 150), b_pend.get("balance_due"), 150)

# ============================================================
print("\n" + "="*60)
print("BLOCK 7: EXPENSES -- listing & filter")
print("="*60)
exp = requests.get(f"{BASE}/api/expenses").json()
check("EXPENSES: returns list",            isinstance(exp, list), type(exp).__name__)
if isinstance(exp, list):
    total = sum(e["amount"] for e in exp)
    check("EXPENSES: total amount = 2800", near(total, 2800), total, 2800)
    paid_total = sum(e["amount"] for e in exp if e.get("payment_status")=="paid")
    check("EXPENSES: paid total = 2500",   near(paid_total, 2500), paid_total, 2500)
    postponed = [e for e in exp if e.get("payment_status")=="postponed"]
    check("EXPENSES: 2 postponed entries", len(postponed)==2, len(postponed), 2)

# ============================================================
print("\n" + "="*60)
print("BLOCK 8: EDGE CASES")
print("="*60)
r = requests.post(f"{BASE}/api/patients/{p1}/followups", json={
    "followup_date":"10/05/2026","treatment_procedure":"Checkup2","price":0,"discount":0,"payment":0
})
check("EDGE: zero-price entry accepted",          r.status_code==200, r.status_code)

r = requests.post(f"{BASE}/api/patients/{p1}/followups", json={
    "followup_date":"10/05/2026","treatment_procedure":"FreeService2","price":100,"discount":200,"payment":0
})
print(f"  EDGE: discount > price -> status={r.status_code} resp={r.json()}")
if r.status_code == 200:
    fu_check = requests.get(f"{BASE}/api/patients/{p1}/followups").json()
    bad = next((f for f in fu_check if f.get("treatment_procedure")=="FreeService2"), None)
    if bad:
        check("EDGE: discount>price no negative balance",
              bad["remaining_amount"] >= 0, bad["remaining_amount"], ">=0")

r = requests.post(f"{BASE}/api/patients/{p1}/followups", json={
    "followup_date":"","treatment_procedure":"Test","price":100,"payment":0
})
check("EDGE: empty date returns 400",             r.status_code==400, r.status_code, 400)

r = requests.post(f"{BASE}/api/patients/{p1}/followups", json={
    "followup_date":"not-a-date","treatment_procedure":"Test","price":100,"payment":0
})
check("EDGE: invalid date returns 400",           r.status_code==400, r.status_code, 400)

r = requests.post(f"{BASE}/api/patients/{p1}/followups", json={
    "followup_date":"10/05/2026","price":100,"payment":0
})
check("EDGE: missing procedure returns 400",      r.status_code==400, r.status_code, 400)

r = requests.post(f"{BASE}/api/patients/99999/followups", json={
    "followup_date":"10/05/2026","treatment_procedure":"X","price":0,"payment":0
})
check("EDGE: nonexistent patient returns 404",    r.status_code==404, r.status_code, 404)

r = requests.post(f"{BASE}/api/expenses", json={})
check("EDGE: expense missing category returns 4xx", r.status_code>=400, r.status_code)

r = requests.post(f"{BASE}/api/expenses", json={"category":"Test","amount":-500,"expense_date":"10/05/2026","payment_status":"paid"})
print(f"  EDGE: negative expense amount -> status={r.status_code} resp={r.json()}")
check("EDGE: negative expense rejected or flagged", r.status_code>=400 or "error" in r.json(), r.status_code)

# ============================================================
print("\n" + "="*60)
print("BLOCK 9: MONTHLY / long-range report (April 2026)")
print("="*60)
m = requests.get(f"{BASE}/api/reports/weekly?start=01/04/2026&end=30/04/2026").json()
print(f"  April range: rev={m['revenue']} exp={m['expenses']} profit={m['profit']}")
print(f"  week_start={m.get('week_start')} week_end={m.get('week_end')}")
# April entries: Crown(pay=250,10/04) + SaraExtraction(pay=100,10/04) = 350
check("MONTHLY-APR: revenue = 350",    near(m["revenue"], 350), m["revenue"], 350)
# April expenses: Utilities 200 = 200
check("MONTHLY-APR: expenses = 200",   near(m["expenses"], 200), m["expenses"], 200)

# ============================================================
print("\n" + "="*60)
print("BLOCK 10: REPORT CONSISTENCY -- summary vs full-period weekly")
print("="*60)
# Run weekly for all time (or very wide range) and compare with summary
all_time = requests.get(f"{BASE}/api/reports/weekly?start=01/01/2020&end=31/12/2030").json()
print(f"  All-time weekly: rev={all_time['revenue']} exp={all_time['expenses']}")
check("CONSISTENCY: wide-range weekly rev matches summary rev",
      near(all_time["revenue"], s["revenue"]), all_time["revenue"], s["revenue"])

# ============================================================
print("\n" + "="*60)
print("FINAL BUG REPORT")
print("="*60)
if bugs:
    print(f"  Total bugs: {len(bugs)}")
    for i, (name, got, exp, note) in enumerate(bugs, 1):
        print(f"\n  BUG-{i}: {name}")
        print(f"     got={got}  expected={exp}")
        if note: print(f"     note: {note}")
else:
    print("  No bugs found!")
