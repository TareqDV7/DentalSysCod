"""Follow-up running balance (the "Amount to Pay" column).

The old code stored a snapshot at insert time, so editing or deleting an earlier
row left every later row's balance stale, and out-of-date-order entries computed
wrong. ``_recompute_followup_balances`` now rewrites the column on every read
and after every write.
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


def _patient(name='Bal', last='Ance', phone='0599'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                (name, last, phone))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _add(client, pid, date_ddmmyyyy, *, price=0, discount=0, payment=0, name='X'):
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': date_ddmmyyyy, 'treatment_procedure': name,
        'price': price, 'discount': discount, 'payment': payment,
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def _rows(client, pid):
    r = client.get(f'/api/patients/{pid}/followups')
    assert r.status_code == 200
    return r.get_json()


def test_running_balance_uses_date_order(client):
    pid = _patient()
    # Insert deliberately out of date order: Mar, Jan, Feb.
    _add(client, pid, '10/03/2026', price=200, payment=50, name='Mar')
    _add(client, pid, '05/01/2026', price=100, payment=100, name='Jan')
    _add(client, pid, '01/02/2026', price=300, discount=50, payment=0, name='Feb')

    rows = _rows(client, pid)
    by_name = {r['treatment_procedure']: r for r in rows}
    # Jan: 100-100=0. Feb: prev 0 + (300-50-0)=250. Mar: prev 250 + (200-50)=400.
    assert by_name['Jan']['remaining_amount'] == 0
    assert by_name['Feb']['remaining_amount'] == 250
    assert by_name['Mar']['remaining_amount'] == 400


def test_editing_earlier_entry_fixes_downstream_balance(client):
    pid = _patient()
    _add(client, pid, '05/01/2026', price=100, payment=0, name='A')
    _add(client, pid, '05/02/2026', price=100, payment=0, name='B')
    _add(client, pid, '05/03/2026', price=100, payment=0, name='C')

    rows = _rows(client, pid)
    a_id = next(r['id'] for r in rows if r['treatment_procedure'] == 'A')

    # Now pay off A in full. B and C should drop by 100.
    client.put(f'/api/patients/{pid}/followups/{a_id}', json={
        'followup_date': '05/01/2026', 'treatment_procedure': 'A',
        'price': 100, 'discount': 0, 'payment': 100,
    })

    rows = _rows(client, pid)
    by_name = {r['treatment_procedure']: r['remaining_amount'] for r in rows}
    assert by_name == {'A': 0, 'B': 100, 'C': 200}


def test_deleting_entry_recomputes_balances_and_removes_lab_expense(client):
    pid = _patient()
    # A procedure that requires lab so the auto-expense is created.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO treatment_procedures (name, requires_lab, default_price, default_lab_expense, active) '
                'VALUES (?,?,?,?,?)', ('LabProc', 1, 500, 100, 1))
    proc_id = cur.lastrowid
    conn.commit()
    conn.close()

    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/04/2026', 'procedure_id': proc_id,
        'price': 500, 'discount': 0, 'payment': 100, 'lab_expense': 100,
    })
    assert r.status_code == 200
    rows = _rows(client, pid)
    fid = rows[0]['id']

    # Auto-expense was created.
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM expenses WHERE source_type='followup' AND reference_id=?", (fid,))
    assert cur.fetchone()[0] == 1
    conn.close()

    # Delete the follow-up — auto-expense should be removed and remaining_amount cleared.
    r = client.delete(f'/api/patients/{pid}/followups/{fid}')
    assert r.status_code == 200
    assert _rows(client, pid) == []

    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM expenses WHERE source_type='followup' AND reference_id=?", (fid,))
    assert cur.fetchone()[0] == 0
    # And a tombstone was recorded for the expense so the deletion syncs.
    cur.execute("SELECT COUNT(*) FROM sync_tombstones WHERE table_name='expenses'")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_deleted_followups_excluded_from_revenue_and_invoice(client):
    """Reports + invoice-summary used to sum deleted rows too."""
    pid = _patient()
    _add(client, pid, '01/06/2026', price=200, payment=200, name='Real')
    _add(client, pid, '02/06/2026', price=999, payment=999, name='Doomed')
    rows = _rows(client, pid)
    doomed_id = next(r['id'] for r in rows if r['treatment_procedure'] == 'Doomed')
    client.delete(f'/api/patients/{pid}/followups/{doomed_id}')

    # Revenue/profit should only include the surviving row.
    r = client.get('/api/reports/summary?start_date=2026-06-01&end_date=2026-06-30')
    payload = r.get_json()
    assert payload['revenue'] == 200, payload

    # Invoice summary likewise.
    inv = client.get(f'/api/patients/{pid}/invoice-summary').get_json()
    assert inv['totals']['total_paid'] == 200
    assert inv['totals']['total_price'] == 200
    assert len(inv['items']) == 1


def test_editing_followup_preserves_paid_lab_expense_status(client):
    """Marking the auto-created lab expense 'paid' must survive an unrelated
    edit to the follow-up entry — the PUT handler used to always recreate the
    linked expense row as 'postponed', silently reverting the paid status."""
    pid = _patient()
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO treatment_procedures (name, requires_lab, default_price, default_lab_expense, active) '
                'VALUES (?,?,?,?,?)', ('LabProc', 1, 500, 100, 1))
    proc_id = cur.lastrowid
    conn.commit()
    conn.close()

    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/04/2026', 'procedure_id': proc_id,
        'price': 500, 'discount': 0, 'payment': 100, 'lab_expense': 100,
    })
    assert r.status_code == 200
    fid = _rows(client, pid)[0]['id']

    conn = dental_clinic.get_db_connection(with_row_factory=True)
    cur = conn.cursor()
    exp_id = cur.execute(
        "SELECT id FROM expenses WHERE source_type='followup' AND reference_id=?", (fid,)
    ).fetchone()['id']
    cur.execute("UPDATE expenses SET payment_status='paid' WHERE id=?", (exp_id,))
    conn.commit()
    conn.close()

    # Edit an unrelated field (notes) on the follow-up.
    r = client.put(f'/api/patients/{pid}/followups/{fid}', json={
        'followup_date': '01/04/2026', 'treatment_procedure': 'LabProc',
        'price': 500, 'discount': 0, 'payment': 100, 'lab_expense': 100,
        'notes': 'unrelated edit',
    })
    assert r.status_code == 200

    conn = dental_clinic.get_db_connection(with_row_factory=True)
    cur = conn.cursor()
    status = cur.execute(
        "SELECT payment_status FROM expenses WHERE source_type='followup' AND reference_id=?", (fid,)
    ).fetchone()['payment_status']
    conn.close()
    assert status == 'paid'
