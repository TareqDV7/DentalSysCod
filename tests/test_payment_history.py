"""Per-patient payment history — ``/api/patients/<id>/payment-history``.

The Billing → Payment Record tab swaps its all-records table for one
patient's *combined* payment history when a patient is picked. That
history must merge two sources: the per-entry ``payment`` column on the
follow-up sheet, and the ``billing`` payment records. This suite locks
that merge, the ordering, the totals, and what gets excluded.
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


def _patient(first='Pay', last='Hist', phone='0500'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (first, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_unknown_patient_returns_404(client):
    assert client.get('/api/patients/99999/payment-history').status_code == 404


def test_followup_payments_appear(client):
    pid = _patient()
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'Filling',
        'tooth_no': '14', 'price': 200, 'payment': 80,
    })
    data = client.get(f'/api/patients/{pid}/payment-history').get_json()
    assert data['totals']['count'] == 1
    ev = data['events'][0]
    assert ev['source'] == 'followup'
    assert ev['amount'] == 80
    assert ev['description'] == 'Filling'
    assert data['totals']['total_paid'] == 80


def test_billing_records_appear(client):
    pid = _patient()
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 150, 'paid_amount': 150,
        'payment_method': 'Card',
    })
    assert r.status_code == 200
    data = client.get(f'/api/patients/{pid}/payment-history').get_json()
    assert data['totals']['count'] == 1
    ev = data['events'][0]
    assert ev['source'] == 'billing'
    assert ev['amount'] == 150
    assert ev['method'] == 'Card'


def test_combined_sources_sorted_oldest_first(client):
    pid = _patient()
    # Follow-up payment dated later than the billing record.
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '10/03/2026', 'treatment_procedure': 'Crown',
        'price': 300, 'payment': 120,
    })
    client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 100, 'paid_amount': 50,
        'payment_date': '01/03/2026',
    })
    data = client.get(f'/api/patients/{pid}/payment-history').get_json()
    assert data['totals']['count'] == 2
    # Oldest first: the 01/03 billing record before the 10/03 follow-up.
    assert data['events'][0]['source'] == 'billing'
    assert data['events'][1]['source'] == 'followup'
    assert data['totals']['total_paid'] == 170


def test_zero_payment_entries_excluded(client):
    pid = _patient()
    # Follow-up with no payment, and a billing record that moved no money.
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'Checkup',
        'price': 50, 'payment': 0,
    })
    client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 90, 'paid_amount': 0,
    })
    data = client.get(f'/api/patients/{pid}/payment-history').get_json()
    assert data['totals']['count'] == 0
    assert data['events'] == []


def test_deleted_followup_excluded(client):
    pid = _patient()
    client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'Filling',
        'price': 200, 'payment': 80,
    })
    conn = dental_clinic.get_db_connection()
    fid = conn.execute('SELECT id FROM patient_followups WHERE patient_id=?',
                       (pid,)).fetchone()[0]
    conn.close()
    client.delete(f'/api/patients/{pid}/followups/{fid}')
    data = client.get(f'/api/patients/{pid}/payment-history').get_json()
    assert data['totals']['count'] == 0


def test_history_scoped_to_one_patient(client):
    pid_a = _patient('Alice', 'A', '0501')
    pid_b = _patient('Bob', 'B', '0502')
    client.post(f'/api/patients/{pid_a}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'X',
        'price': 100, 'payment': 40,
    })
    client.post(f'/api/patients/{pid_b}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'Y',
        'price': 100, 'payment': 70,
    })
    data_a = client.get(f'/api/patients/{pid_a}/payment-history').get_json()
    assert data_a['totals']['count'] == 1
    assert data_a['totals']['total_paid'] == 40
    assert data_a['patient']['name'] == 'Alice A'
