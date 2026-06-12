"""Unified patient ledger — the follow-up sheet and billing are ONE account.

    Outstanding = (Σ charges) − (Σ payments)   across BOTH ledgers
      charges  = sheet(price − discount)  +  billing(subtotal − discount)
      payments = sheet(payment)           +  billing(paid_amount)

Overpayment is simply a negative balance = credit (no separate credit ledger).
A billing entry may be a charge, a payment, or both; a payment-only entry has
subtotal 0. Every surface (profile, receivables, credit) reports the same number.
"""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient():
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                ('Cre', 'Dit', '055'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _add_followup(client, pid, **kw):
    body = {'followup_date': '01/02/2026', 'treatment_procedure': 'X',
            'price': 0, 'discount': 0, 'payment': 0}
    body.update(kw)
    r = client.post(f'/api/patients/{pid}/followups', json=body)
    assert r.status_code == 200, r.get_json()


def _outstanding(client, pid):
    return client.get(f'/api/patients/{pid}/full-profile').get_json()['outstanding']


def _credit(client, pid):
    return client.get(f'/api/patients/{pid}/credit').get_json()['balance']


def test_sheet_charge_plus_billing_payment_reconciles_to_zero(client):
    """Acceptance case: charge 300 / pay 100 on the sheet, then pay the remaining
    200 from the billing page (payment-only) → outstanding 0 everywhere."""
    pid = _patient()
    _add_followup(client, pid, price=300, payment=100)
    assert _outstanding(client, pid) == 200

    r = client.post('/api/billing', json={'patient_id': pid, 'subtotal': 0, 'paid_amount': 200})
    assert r.status_code == 200, r.get_json()

    assert _outstanding(client, pid) == 0
    # No longer a receivable.
    recv = client.get('/api/reports/receivables').get_json()
    assert all(row['patient_id'] != pid for row in recv['rows'])


def test_billing_charge_adds_to_balance(client):
    pid = _patient()
    r = client.post('/api/billing', json={'patient_id': pid, 'subtotal': 150, 'paid_amount': 0})
    assert r.status_code == 200
    assert _outstanding(client, pid) == 150


def test_overpayment_on_sheet_becomes_credit(client):
    pid = _patient()
    _add_followup(client, pid, price=40, payment=100)
    assert _outstanding(client, pid) == 0          # nothing owed
    assert _credit(client, pid) == 60              # 60 overpaid = credit
    prof = client.get(f'/api/patients/{pid}/full-profile').get_json()
    assert prof['credit_balance'] == 60


def test_overpayment_via_billing_also_credits(client):
    pid = _patient()
    _add_followup(client, pid, price=100, payment=0)
    client.post('/api/billing', json={'patient_id': pid, 'subtotal': 0, 'paid_amount': 130})
    assert _outstanding(client, pid) == 0
    assert _credit(client, pid) == 30


def test_billing_entry_must_carry_money(client):
    pid = _patient()
    r = client.post('/api/billing', json={'patient_id': pid, 'subtotal': 0, 'paid_amount': 0})
    assert r.status_code == 400


def test_all_surfaces_agree_on_outstanding(client):
    """Profile outstanding == receivables outstanding for the same patient."""
    pid = _patient()
    _add_followup(client, pid, price=500, payment=120)
    client.post('/api/billing', json={'patient_id': pid, 'subtotal': 80, 'paid_amount': 0})
    # 500 + 80 charged − 120 paid = 460
    assert _outstanding(client, pid) == 460
    recv = client.get('/api/reports/receivables').get_json()
    row = next(r for r in recv['rows'] if r['patient_id'] == pid)
    assert row['outstanding'] == 460
