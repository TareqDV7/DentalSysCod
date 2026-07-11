"""Unified clinic gross profit: billing revenue was previously invisible to
clinic_gross_profit (follow-up-sheet-only), and profit omitted lab_expense
entirely -- the two numbers disagreed. Both /api/reports/summary and
/api/reports/weekly must now return one correct, identical figure via both
the clinic_gross_profit and profit keys (profit key kept for API back-compat
with mobile's Dart models -- see plan Global Constraints)."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'gross_profit_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


DATE_RANGE = ('2020-01-01', '2099-12-31')  # wide enough to include "now" at any test-run time


def _patient(name='Gross', last='Profit', phone='0599'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _lab_procedure_id():
    # lab_expense is only persisted for procedures catalogued as
    # lab-requiring (dental_clinic.py's followups POST route zeroes it
    # otherwise via `if not requires_lab: lab_expense = 0`) -- an existing
    # business rule unrelated to this fix. Any test that wants a non-zero
    # lab_expense must go through a procedure_id pointing at such a row.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM treatment_procedures WHERE name = 'Lab Work Test'")
    row = cur.fetchone()
    if row:
        pid = row[0]
    else:
        cur.execute("INSERT INTO treatment_procedures (name, requires_lab) VALUES ('Lab Work Test', 1)")
        pid = cur.lastrowid
        conn.commit()
    conn.close()
    return pid


def _followup(client, pid, *, price, discount=0, lab_expense=0, payment=0, date='15/06/2026'):
    payload = {
        'followup_date': date, 'treatment_procedure': 'Filling',
        'price': price, 'discount': discount, 'lab_expense': lab_expense, 'payment': payment,
    }
    if lab_expense:
        payload['procedure_id'] = _lab_procedure_id()
    r = client.post(f'/api/patients/{pid}/followups', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def _billing(client, pid, *, subtotal, discount=0, paid_amount=0):
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': subtotal, 'discount': discount, 'paid_amount': paid_amount,
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def test_summary_gross_profit_includes_billing_revenue(client):
    # Before this fix, billing charges were invisible to clinic_gross_profit
    # entirely -- this is the exact bug the unification closes.
    pid = _patient()
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)

    r = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}')
    payload = r.get_json()
    # 500 - 50 discount - 0 lab_expense - 0 general expenses = 450
    assert payload['clinic_gross_profit'] == 450, payload
    assert payload['profit'] == 450, payload


def test_summary_gross_profit_combines_followup_and_billing(client):
    pid = _patient()
    _followup(client, pid, price=300, discount=20, lab_expense=30, payment=250)
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)

    r = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}')
    payload = r.get_json()
    # followup: 300 - 20 - 30 = 250. billing: 500 - 50 = 450. total = 700.
    assert payload['clinic_gross_profit'] == 700, payload
    assert payload['profit'] == 700, payload


def test_summary_profit_and_clinic_gross_profit_always_match(client):
    # The two keys must never disagree again -- that divergence was the bug.
    pid = _patient()
    _followup(client, pid, price=100, lab_expense=10, payment=100)
    _billing(client, pid, subtotal=200, paid_amount=200)

    r = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}')
    payload = r.get_json()
    assert payload['clinic_gross_profit'] == payload['profit'], payload


import datetime


def _monday_of_this_week():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def test_weekly_gross_profit_includes_billing_revenue(client):
    monday = _monday_of_this_week()
    pid = _patient()
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)  # created_at = now, falls in this week

    r = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}')
    payload = r.get_json()
    assert payload['clinic_gross_profit'] == 450, payload
    assert payload['profit'] == 450, payload


def test_weekly_gross_profit_combines_followup_and_billing(client):
    monday = _monday_of_this_week()
    followup_date = monday + datetime.timedelta(days=2)  # Wednesday of this week
    pid = _patient()
    _followup(client, pid, price=300, discount=20, lab_expense=30, payment=250,
              date=followup_date.strftime('%d/%m/%Y'))
    _billing(client, pid, subtotal=500, discount=50, paid_amount=450)

    r = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}')
    payload = r.get_json()
    # followup: 300 - 20 - 30 = 250. billing: 500 - 50 = 450. total = 700.
    assert payload['clinic_gross_profit'] == 700, payload
    assert payload['profit'] == 700, payload
