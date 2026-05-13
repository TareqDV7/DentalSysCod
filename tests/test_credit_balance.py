"""Patient credit balance — money the clinic is holding *for* the patient.

The feature used to be a dead end: nothing populated ``patient_credit_transactions``,
the billing form's ``credit_used`` was ignored, and the credit-adjustment endpoint
stored ``abs(amount)`` for both debits and credits. Now credit derives from
overpayment + signed manual adjustments, and ``credit_used`` actually settles
invoices and draws the balance down.
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


def test_overpayment_becomes_credit(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'X',
        'price': 40, 'discount': 0, 'payment': 100,
    })
    assert r.status_code == 200

    prof = client.get(f'/api/patients/{pid}/full-profile').get_json()
    assert prof['credit_balance'] == 60

    cr = client.get(f'/api/patients/{pid}/credit').get_json()
    assert cr['balance'] == 60


def test_credit_used_settles_invoice_and_draws_down_balance(client):
    pid = _patient()
    # Build up 60 of credit.
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'X',
        'price': 40, 'payment': 100,
    })

    # ₪100 invoice, pay ₪20 cash + ₪30 credit → balance_due ₪50, status partial.
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 100, 'paid_amount': 20, 'credit_used': 30,
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body['balance_due'] == 50
    assert body['payment_status'] == 'partial'

    # Credit dropped to 30.
    assert client.get(f'/api/patients/{pid}/credit').get_json()['balance'] == 30

    # The matching debit row was recorded.
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    rows = conn.execute(
        'SELECT amount, type FROM patient_credit_transactions WHERE patient_id=?',
        (pid,)).fetchall()
    conn.close()
    assert (-30.0, 'debit') in [(r[0], r[1]) for r in rows]


def test_credit_used_capped_at_available(client):
    pid = _patient()
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'X',
        'price': 40, 'payment': 100,
    })
    r = client.post('/api/billing',
                    json={'patient_id': pid, 'subtotal': 100, 'paid_amount': 0,
                          'credit_used': 9999})
    assert r.status_code == 400


def test_deleting_billing_reverses_credit_transaction(client):
    pid = _patient()
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'X',
        'price': 40, 'payment': 100,
    })
    client.post('/api/billing',
                json={'patient_id': pid, 'subtotal': 100, 'paid_amount': 0,
                      'credit_used': 30})
    bid = client.get('/api/billing').get_json()[0]['id']
    assert client.get(f'/api/patients/{pid}/credit').get_json()['balance'] == 30

    client.delete(f'/api/billing/{bid}')
    # The debit transaction is reversed, so credit is back to 60.
    assert client.get(f'/api/patients/{pid}/credit').get_json()['balance'] == 60


def test_credit_adjustment_stores_signed_amount(client):
    pid = _patient()
    # Add 50 credit manually, then debit 20.
    client.post(f'/api/patients/{pid}/credit-adjustment', json={'amount': 50, 'note': 'gift'})
    client.post(f'/api/patients/{pid}/credit-adjustment', json={'amount': -20, 'note': 'used'})

    cr = client.get(f'/api/patients/{pid}/credit').get_json()
    assert cr['balance'] == 30  # 50 + (-20)
