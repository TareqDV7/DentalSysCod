"""Amount fields keep verbatim expressions (e.g. "20+20").

The user enters an arithmetic expression in any money field on a follow-up or
billing record; the number is used for maths but the original string is stored
in a paired ``*_expr`` column and shown on the sheet / invoice. The sanitizer
keeps only real expressions that evaluate to the stored number — bare numbers
and tampered values are dropped.
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
    cur.execute('INSERT INTO patients (first_name, last_name) VALUES (?,?)', ('E', 'X'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


# ── sanitize_amount_expr (unit-level) ───────────────────────────────────────

def test_sanitize_keeps_matching_expression():
    assert dental_clinic.sanitize_amount_expr('20+20', 40) == '20+20'
    assert dental_clinic.sanitize_amount_expr(' 10 + 5 * 2 ', 20) == '10 + 5 * 2'


def test_sanitize_drops_bare_numbers():
    assert dental_clinic.sanitize_amount_expr('40', 40) is None
    assert dental_clinic.sanitize_amount_expr(' 12.50 ', 12.5) is None


def test_sanitize_drops_mismatched_expressions():
    # "1+1" doesn't evaluate to 40 — should be dropped, not stored as a lie.
    assert dental_clinic.sanitize_amount_expr('1+1', 40) is None


def test_sanitize_rejects_unsafe_input():
    assert dental_clinic.sanitize_amount_expr('__import__("os")', 0) is None
    assert dental_clinic.sanitize_amount_expr('a+b', 0) is None
    assert dental_clinic.sanitize_amount_expr('x' * 50, 0) is None


# ── follow-up round-trip ────────────────────────────────────────────────────

def test_followup_round_trip_keeps_expression(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'X',
        'price': 40, 'price_expr': '20+20',
        'payment': 100, 'payment_expr': '50+50',
    })
    assert r.status_code == 200

    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['price_expr'] == '20+20'
    assert rows[0]['payment_expr'] == '50+50'

    inv = client.get(f'/api/patients/{pid}/invoice-summary').get_json()
    assert inv['items'][0]['price_expr'] == '20+20'
    assert inv['items'][0]['payment_expr'] == '50+50'


def test_followup_drops_tampered_expression(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '02/02/2026', 'treatment_procedure': 'Y',
        'price': 40, 'price_expr': '1+1',   # evaluates to 2, not 40
        'payment': 0,
    })
    assert r.status_code == 200

    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    assert rows[0]['price_expr'] is None


# ── billing round-trip ──────────────────────────────────────────────────────

def test_billing_round_trip_keeps_expressions(client):
    pid = _patient()
    r = client.post('/api/billing', json={
        'patient_id': pid,
        'subtotal': 100, 'subtotal_expr': '40+60',
        'discount': 10,  'discount_expr': '5+5',
        'paid_amount': 30, 'paid_amount_expr': '10+20',
    })
    assert r.status_code == 200

    row = client.get('/api/billing').get_json()[0]
    assert row['subtotal_expr'] == '40+60'
    assert row['discount_expr'] == '5+5'
    assert row['paid_amount_expr'] == '10+20'
