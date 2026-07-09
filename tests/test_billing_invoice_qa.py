"""QA reconciliation for the invoicing / billing math.

Acts as a tester over the two invoice surfaces:
  * patient Statement  -> GET /api/patients/<id>/invoice-summary  (all sessions or
    a date range), the source for the "Generate Total Invoice" print.
  * per-record invoice -> GET /invoice/<billing_id>               (one billing row).

Verifies every number reconciles to the unified-ledger identity
    outstanding = Σ(price − discount) + Σ(subtotal − discount) − Σpayments
and documents one known wart (over-discount).
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
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO patients (first_name, last_name, phone) VALUES (?,?,?)',
                ('Inv', 'Oice', '0500'))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _session(client, pid, date, price, discount=0, payment=0):
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': date, 'treatment_procedure': 'Tx',
        'price': price, 'discount': discount, 'payment': payment,
    })
    assert r.status_code == 200, r.get_json()


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def _outstanding(client, pid):
    return client.get(f'/api/patients/{pid}/full-profile').get_json()['outstanding']


def _credit(client, pid):
    return client.get(f'/api/patients/{pid}/credit').get_json()['balance']


# --- all-sessions statement -------------------------------------------------

def test_all_sessions_statement_totals_reconcile(client):
    pid = _patient()
    _session(client, pid, '01/02/2026', price=300, payment=100)
    _session(client, pid, '05/02/2026', price=200, discount=50)
    _session(client, pid, '10/02/2026', price=100, payment=100)

    summ = client.get(f'/api/patients/{pid}/invoice-summary').get_json()
    t = summ['totals']
    assert t['total_price'] == 600
    assert t['total_discount'] == 50
    assert t['total_to_pay'] == 550          # 600 − 50
    assert t['total_paid'] == 200
    assert t['total_left'] == 350            # 550 − 200

    # The statement's "Left" must equal the unified-ledger outstanding.
    assert _outstanding(client, pid) == t['total_left']

    # Per-line net_due = price − discount (lab excluded), and the running
    # Balance walks chronologically: 200 -> 350 -> 350.
    items = summ['items']
    assert [it['net_due'] for it in items] == [300, 150, 100]
    assert [it['remaining_amount'] for it in items] == [200, 350, 350]


# --- single-session (date-filtered) statement -------------------------------

def test_single_session_statement_via_date_filter(client):
    pid = _patient()
    _session(client, pid, '01/02/2026', price=300, payment=100)
    _session(client, pid, '05/02/2026', price=200, discount=50)
    _session(client, pid, '10/02/2026', price=100, payment=100)

    summ = client.get(
        f'/api/patients/{pid}/invoice-summary'
        '?start_date=2026-02-05&end_date=2026-02-05'
    ).get_json()
    assert len(summ['items']) == 1
    t = summ['totals']
    assert t['total_price'] == 200
    assert t['total_discount'] == 50
    assert t['total_to_pay'] == 150
    assert t['total_paid'] == 0
    assert t['total_left'] == 150


# --- per-record invoice page ------------------------------------------------

def test_billing_invoice_page_renders_correct_math(client):
    pid = _patient()
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 200, 'discount': 50, 'paid_amount': 100,
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body['amount'] == 150           # 200 − 50
    assert body['balance_due'] == 50       # 150 − 100
    assert body['payment_status'] == 'partial'

    # The printable invoice page shows the same figures (auth-gated route).
    _login(client)
    bid = dental_clinic.get_db_connection().execute(
        'SELECT id FROM billing WHERE patient_id = ?', (pid,)).fetchone()[0]
    html = client.get(f'/invoice/{bid}').get_data(as_text=True)
    assert '150.00' in html        # total
    assert '50.00' in html         # discount + balance
    assert '100.00' in html        # paid


# --- over-discount is now rejected (no phantom credit) ----------------------

def test_over_discount_billing_is_rejected(client):
    """A billing discount LARGER than the subtotal used to be accepted and would
    manufacture phantom credit (the ledger subtracts the raw negative while the
    invoice clamps to 0). It is now rejected at the boundary."""
    pid = _patient()
    r = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 100, 'discount': 150, 'paid_amount': 0,
    })
    assert r.status_code == 400
    # Equal-to-charge (100% off) is still allowed.
    ok = client.post('/api/billing', json={
        'patient_id': pid, 'subtotal': 100, 'discount': 100, 'paid_amount': 0,
    })
    assert ok.status_code == 200
    assert _outstanding(client, pid) == 0
    assert _credit(client, pid) == 0                   # no phantom credit


def test_over_discount_session_is_rejected(client):
    pid = _patient()
    r = client.post(f'/api/patients/{pid}/followups', json={
        'followup_date': '01/02/2026', 'treatment_procedure': 'Tx',
        'price': 100, 'discount': 150, 'payment': 0,
    })
    assert r.status_code == 400


# --- single-session invoice by id -------------------------------------------

def test_single_session_invoice_by_id(client):
    pid = _patient()
    _session(client, pid, '01/02/2026', price=300, payment=100)
    _session(client, pid, '05/02/2026', price=200, discount=50, payment=20)

    # Find the second session's id.
    rows = client.get(f'/api/patients/{pid}/followups').get_json()
    sid = [r for r in rows if r['price'] == 200][0]['id']

    summ = client.get(
        f'/api/patients/{pid}/invoice-summary?session_id={sid}').get_json()
    assert len(summ['items']) == 1
    it = summ['items'][0]
    # The line balance is the session's OWN balance, not the cumulative ledger:
    assert it['remaining_amount'] == 130           # 200 − 50 − 20
    t = summ['totals']
    assert t['total_to_pay'] == 150                 # 200 − 50
    assert t['total_paid'] == 20
    assert t['total_left'] == 130


# --- embed mode suppresses the page's own print() so the iframe drives it ----

def test_invoice_embed_suppresses_autoprint(client):
    _login(client)
    pid = _patient()
    client.post('/api/billing', json={'patient_id': pid, 'subtotal': 50, 'paid_amount': 50})
    bid = dental_clinic.get_db_connection().execute(
        'SELECT id FROM billing WHERE patient_id = ?', (pid,)).fetchone()[0]

    standalone = client.get(f'/invoice/{bid}').get_data(as_text=True)
    embedded = client.get(f'/invoice/{bid}?embed=1').get_data(as_text=True)
    assert 'window.print()' in standalone
    assert 'window.print()' not in embedded
