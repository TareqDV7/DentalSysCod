"""Regression cover for the sync-import resilience fixes.

A bad row in a push payload used to crash the whole batch (e.g. a billing row
without ``amount`` would raise ``NOT NULL constraint failed`` and the route
returned 500 — every sibling row in the same payload was lost). The route now
isolates per-row failures (counted as ``skipped``) and continues processing.
The mobile-side rename helper also fills ``amount`` from ``subtotal − discount``
so the row is accepted in the first place; this test verifies the *server*
contract those mobile fixes target.
"""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / 'sync.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()

    # Seed a paired device + a patient so /api/sync/import is authorized.
    conn = dental_clinic.get_db_connection()
    conn.execute(
        "INSERT INTO paired_devices (device_id, device_name, device_token) VALUES (?, ?, ?)",
        ('dev-test', 'Mobile', 'tok-test'),
    )
    conn.execute('INSERT INTO patients (id, first_name, last_name) VALUES (1, "A", "B")')
    conn.commit()
    conn.close()

    with dental_clinic.app.test_client() as c:
        yield c


def _post(client, payload):
    return client.post(
        '/api/sync/import',
        headers={'X-Device-Token': 'tok-test'},
        json=payload,
    )


def test_bad_row_does_not_crash_batch(client):
    # A billing row missing the NOT NULL ``amount`` column used to 500 the whole
    # request, taking the sibling patient row down with it. The bad row must be
    # counted as skipped and the good row must still apply.
    payload = {
        'tables': {
            'patients': [
                {'id': 10, 'first_name': 'New', 'last_name': 'Patient',
                 'updated_at': '2030-01-01T00:00:00Z'}
            ],
            'billing': [
                {'id': 99, 'patient_id': 1, 'subtotal': 100, 'discount': 0,
                 'paid_amount': 100, 'payment_method': 'cash',
                 'payment_date': '2026-05-13', 'updated_at': '2030-01-01T00:00:00Z'},
            ],
        },
        'tombstones': [],
    }
    r = _post(client, payload)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['applied_total'] == 1, body
    assert body['skipped_total'] >= 1, body

    conn = dental_clinic.get_db_connection()
    assert conn.execute('SELECT id FROM patients WHERE id = 10').fetchone() is not None
    assert conn.execute('SELECT id FROM billing WHERE id = 99').fetchone() is None
    conn.close()


def test_billing_with_amount_is_accepted(client):
    # The mobile fix computes ``amount = subtotal − discount`` before pushing.
    # The server should accept the row and store every column.
    payload = {
        'tables': {
            'billing': [
                {'id': 50, 'patient_id': 1, 'amount': 80, 'subtotal': 100,
                 'discount': 20, 'paid_amount': 50, 'payment_method': 'cash',
                 'payment_date': '2026-05-13', 'updated_at': '2030-01-01T00:00:00Z'}
            ],
        },
        'tombstones': [],
    }
    r = _post(client, payload)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['applied_total'] == 1

    conn = dental_clinic.get_db_connection()
    row = conn.execute(
        'SELECT amount, subtotal, discount, paid_amount FROM billing WHERE id = 50'
    ).fetchone()
    conn.close()
    assert row == (80, 100, 20, 50)


def test_treatment_procedure_drift_terms(client):
    # When the mobile sends rows with the server-side names (after the rename
    # in _toServerRow), the row applies and the columns are preserved.
    payload = {
        'tables': {
            'treatment_procedures': [
                {'id': 100, 'name': 'Mobile-Originated', 'default_price': 75,
                 'default_lab_expense': 20, 'requires_lab': 1, 'active': 1,
                 'updated_at': '2030-01-01T00:00:00Z'}
            ],
        },
        'tombstones': [],
    }
    r = _post(client, payload)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['applied_total'] == 1

    conn = dental_clinic.get_db_connection()
    row = conn.execute(
        'SELECT name, default_price, default_lab_expense, requires_lab, active '
        'FROM treatment_procedures WHERE id = 100'
    ).fetchone()
    conn.close()
    assert row == ('Mobile-Originated', 75, 20, 1, 1)
