"""Per-dentist revenue/margin breakdown on /api/reports/summary and
/api/reports/weekly -- see docs/superpowers/specs/2026-07-12-per-dentist-reporting-design.md.
No general-expense allocation: gross_margin = revenue - the dentist's own
lab_expense only."""
import dental_clinic
import permissions
import pytest


DATE_RANGE = ('2020-01-01', '2099-12-31')  # wide enough to include "now" at any test-run time


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'per_dentist_reporting_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _patient():
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _dentist(username, display_name):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist) VALUES (?, ?, ?, 1)',
        (username, 'x', display_name),
    )
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _lab_procedure_id():
    # Mirrors tests/test_reports_gross_profit.py: lab_expense is only
    # persisted for procedures catalogued as lab-requiring.
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


def _followup(client, pid, dentist_id=None, *, price, discount=0, lab_expense=0, payment=0, date='15/06/2026'):
    payload = {
        'followup_date': date, 'treatment_procedure': 'Filling',
        'price': price, 'discount': discount, 'lab_expense': lab_expense, 'payment': payment,
    }
    if lab_expense:
        payload['procedure_id'] = _lab_procedure_id()
    if dentist_id is not None:
        payload['dentist_id'] = dentist_id
    r = client.post(f'/api/patients/{pid}/followups', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def _billing(client, pid, dentist_id=None, *, subtotal, discount=0, paid_amount=0):
    payload = {'patient_id': pid, 'subtotal': subtotal, 'discount': discount, 'paid_amount': paid_amount}
    if dentist_id is not None:
        payload['dentist_id'] = dentist_id
    r = client.post('/api/billing', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def test_summary_breakdown_has_one_row_per_dentist(client):
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    zed = _dentist('zed', 'Dr. Zed')
    _followup(client, pid, amy, price=300, discount=20, lab_expense=30, payment=250)
    _billing(client, pid, zed, subtotal=200, paid_amount=200)

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[amy]['dentist_name'] == 'Dr. Amy'
    assert breakdown[amy]['revenue'] == 280      # 300 - 20
    assert breakdown[amy]['lab_expense'] == 30
    assert breakdown[amy]['gross_margin'] == 250  # 280 - 30
    assert breakdown[zed]['dentist_name'] == 'Dr. Zed'
    assert breakdown[zed]['revenue'] == 200
    assert breakdown[zed]['gross_margin'] == 200


def test_summary_breakdown_combines_followup_and_billing_for_same_dentist(client):
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    _followup(client, pid, amy, price=100, payment=100)
    _billing(client, pid, amy, subtotal=200, paid_amount=200)

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[amy]['revenue'] == 300  # 100 + 200


def test_summary_breakdown_has_unassigned_bucket_sorted_last(client):
    pid = _patient()
    zed = _dentist('zed', 'Dr. Zed')  # alphabetically after "Unassigned" would sort... but Unassigned must be last regardless
    _followup(client, pid, zed, price=100, payment=100)
    _followup(client, pid, None, price=50, payment=50)  # no dentist_id -> unassigned (no session either)

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    names = [row['dentist_name'] for row in payload['dentist_breakdown']]
    assert names[-1] == 'Unassigned'
    unassigned = next(row for row in payload['dentist_breakdown'] if row['dentist_id'] is None)
    assert unassigned['revenue'] == 50


def test_summary_breakdown_shows_real_name_for_un_flagged_former_dentist(client):
    # Refinement found during planning: a dentist_id valid at creation time
    # must still show under their real name even if later un-flagged.
    pid = _patient()
    former = _dentist('former', 'Dr. Former')
    _followup(client, pid, former, price=100, payment=100)

    conn = dental_clinic.get_db_connection()
    conn.execute('UPDATE users SET is_dentist = 0 WHERE id = ?', (former,))
    conn.commit()
    conn.close()

    payload = client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[former]['dentist_name'] == 'Dr. Former'


import datetime


def _monday_of_this_week():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def test_weekly_breakdown_has_one_row_per_dentist(client):
    monday = _monday_of_this_week()
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    _billing(client, pid, amy, subtotal=200, paid_amount=200)  # created_at = now, falls in this week

    payload = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    assert breakdown[amy]['revenue'] == 200
    assert breakdown[amy]['gross_margin'] == 200


def test_weekly_breakdown_combines_followup_and_billing(client):
    monday = _monday_of_this_week()
    followup_date = monday + datetime.timedelta(days=2)
    pid = _patient()
    amy = _dentist('amy', 'Dr. Amy')
    _followup(client, pid, amy, price=300, discount=20, lab_expense=30, payment=250,
              date=followup_date.strftime('%d/%m/%Y'))
    _billing(client, pid, amy, subtotal=200, paid_amount=200)

    payload = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()
    breakdown = {row['dentist_id']: row for row in payload['dentist_breakdown']}
    # followup: 300-20=280, minus lab 30 -> margin 250. billing: 200, margin 200. combined revenue 480, margin 450.
    assert breakdown[amy]['revenue'] == 480
    assert breakdown[amy]['gross_margin'] == 450


def test_weekly_breakdown_unassigned_sorted_last(client):
    monday = _monday_of_this_week()
    followup_date = monday + datetime.timedelta(days=1)
    pid = _patient()
    zed = _dentist('zed', 'Dr. Zed')
    _followup(client, pid, zed, price=100, payment=100, date=followup_date.strftime('%d/%m/%Y'))
    _followup(client, pid, None, price=50, payment=50, date=followup_date.strftime('%d/%m/%Y'))

    payload = client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()
    names = [row['dentist_name'] for row in payload['dentist_breakdown']]
    assert names[-1] == 'Unassigned'
