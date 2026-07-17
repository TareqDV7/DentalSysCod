"""Task 13: dentist-scoped report aggregates on /api/reports/summary and
/api/reports/weekly.

Unlike the billing/followups list endpoints (Task 12), these use the RAW
dentist_scope() fragment with no OR-NULL widening: a dentist's financial
totals only include rows explicitly assigned to them (NULL-dentist rows are
excluded, not shown as "unassigned but visible"). visits and treatment_plans
have no dentist_id column in the schema and stay clinic-wide for every role.
General clinic expenses (expenses_paid/expenses_postponed/expenses and the
general-expense term in clinic_gross_profit) are zeroed out in the dentist
view -- overhead isn't any one dentist's cost (mirrors the per-dentist
breakdown design already used for gross_margin).
"""
import datetime

import dental_clinic
import permissions
import pytest


DATE_RANGE = ('2020-01-01', '2099-12-31')  # wide enough to include "now" at any test-run time


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'role_scope_reports_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def _patient():
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (first_name, last_name, phone) VALUES ('A', 'B', '1')")
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _user(username, role):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_dentist, role) '
        'VALUES (?, ?, ?, ?, ?)',
        (username, 'x', username, 1 if role == 'dentist' else 0, role))
    uid = cur.lastrowid
    permissions.grant_all(cur, uid)
    conn.commit()
    conn.close()
    return uid


def _login(client, uid, username):
    with client.session_transaction() as sess:
        sess['uid'] = uid
        sess['uname'] = username


def _logout(client):
    with client.session_transaction() as sess:
        sess.clear()


def _lab_procedure_id():
    # Mirrors tests/test_per_dentist_reporting.py: lab_expense is only
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


def _followup(client, pid, dentist_id, *, price, discount=0, lab_expense=0, payment=0, date='15/06/2026'):
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


def _billing(client, pid, dentist_id, *, subtotal, discount=0, paid_amount=0):
    payload = {'patient_id': pid, 'subtotal': subtotal, 'discount': discount, 'paid_amount': paid_amount}
    if dentist_id is not None:
        payload['dentist_id'] = dentist_id
    r = client.post('/api/billing', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)


def _appointment(pid, dentist_id, appointment_date):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO appointments (patient_id, appointment_date, dentist_id) VALUES (?, ?, ?)',
        (pid, appointment_date, dentist_id))
    conn.commit()
    conn.close()


def _visit(pid, visit_date):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO visits (patient_id, visit_date) VALUES (?, ?)', (pid, visit_date))
    conn.commit()
    conn.close()


def _treatment_plan(pid, start_date):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO treatment_plans (patient_id, plan_name, start_date) VALUES (?, 'Plan', ?)",
        (pid, start_date))
    conn.commit()
    conn.close()


def _expense(amount, payment_status, expense_date):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (category, amount, expense_date, payment_status) VALUES ('rent', ?, ?, ?)",
        (amount, expense_date, payment_status))
    conn.commit()
    conn.close()


def _monday_of_this_week():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _seed_world(client, admin, a, b, pid, followup_date, other_date):
    """Seed followup/billing rows for A, B, and NULL (via the real POST code
    path, logged in as admin so client-supplied dentist_id is trusted), plus
    clinic-wide appointments/visit/treatment_plan/expenses rows. Numbers are
    chosen so payment-collected revenue and charge-based gross_profit differ,
    to catch a field mix-up.
    """
    _login(client, admin, 'boss')
    _followup(client, pid, a, price=300, lab_expense=50, payment=300, date=followup_date)
    _followup(client, pid, b, price=200, payment=200, date=followup_date)
    _followup(client, pid, None, price=100, payment=100, date=followup_date)
    _billing(client, pid, a, subtotal=150, paid_amount=150)
    _billing(client, pid, b, subtotal=120, paid_amount=120)
    _billing(client, pid, None, subtotal=80, paid_amount=80)
    _logout(client)

    _appointment(pid, a, other_date)
    _appointment(pid, b, other_date)
    _appointment(pid, None, other_date)
    _visit(pid, other_date)
    _treatment_plan(pid, other_date)
    _expense(500, 'paid', other_date)
    _expense(200, 'postponed', other_date)


@pytest.fixture()
def summary_world(client):
    pid = _patient()
    a = _user('drA', 'dentist')
    b = _user('drB', 'dentist')
    admin = _user('boss', 'admin')
    _seed_world(client, admin, a, b, pid, '15/06/2026', '2026-06-15')
    return {'pid': pid, 'a': a, 'b': b, 'admin': admin}


@pytest.fixture()
def weekly_world(client):
    monday = _monday_of_this_week()
    day = monday + datetime.timedelta(days=1)
    pid = _patient()
    a = _user('drA', 'dentist')
    b = _user('drB', 'dentist')
    admin = _user('boss', 'admin')
    _seed_world(client, admin, a, b, pid, day.strftime('%d/%m/%Y'), day.isoformat())
    return {'pid': pid, 'a': a, 'b': b, 'admin': admin, 'monday': monday}


def _summary(client):
    return client.get(f'/api/reports/summary?start_date={DATE_RANGE[0]}&end_date={DATE_RANGE[1]}').get_json()


def _weekly(client, monday):
    return client.get(f'/api/reports/weekly?week_start={monday.isoformat()}').get_json()


# --- /api/reports/summary -----------------------------------------------------

def test_summary_dentist_view_scoped_to_own_rows(client, summary_world):
    _login(client, summary_world['a'], 'drA')
    payload = _summary(client)
    assert payload['revenue'] == 450       # 300 (own followup payment) + 150 (own billing paid)
    assert payload['lab_expenses'] == 50
    assert payload['clinic_gross_profit'] == 400  # 300 + 150 - 50 lab - 0 general
    assert payload['appointments'] == 1
    assert len(payload['dentist_breakdown']) == 1
    assert payload['dentist_breakdown'][0]['dentist_id'] == summary_world['a']


def test_summary_dentist_view_zeroes_general_expenses(client, summary_world):
    _login(client, summary_world['a'], 'drA')
    payload = _summary(client)
    assert payload['expenses_paid'] == 0
    assert payload['expenses_postponed'] == 0
    assert payload['expenses'] == 0


def test_summary_dentist_view_visits_and_plans_stay_clinic_wide(client, summary_world):
    _login(client, summary_world['a'], 'drA')
    payload = _summary(client)
    assert payload['visits'] == 1
    assert payload['treatment_plans'] == 1


def test_summary_admin_view_sees_everything(client, summary_world):
    _login(client, summary_world['admin'], 'boss')
    payload = _summary(client)
    assert payload['revenue'] == 950       # (300+200+100) followups + (150+120+80) billing
    assert payload['appointments'] == 3
    assert len(payload['dentist_breakdown']) == 3
    assert payload['expenses_paid'] == 500
    # 200 seeded directly + 50 auto-mirrored from A's lab-requiring followup
    # (source_type='followup', unpaid by default -- see the followups POST route).
    assert payload['expenses_postponed'] == 250
    assert payload['expenses'] == 750


def test_summary_dentist_with_no_rows_gets_empty_breakdown(client, summary_world):
    c = _user('drC', 'dentist')
    _login(client, c, 'drC')
    payload = _summary(client)
    assert payload['dentist_breakdown'] == []
    assert payload['revenue'] == 0
    assert payload['appointments'] == 0


# --- /api/reports/weekly ------------------------------------------------------

def test_weekly_dentist_view_scoped_to_own_rows(client, weekly_world):
    _login(client, weekly_world['a'], 'drA')
    payload = _weekly(client, weekly_world['monday'])
    assert payload['revenue'] == 450
    assert payload['lab_expenses'] == 50
    assert payload['clinic_gross_profit'] == 400
    assert payload['appointments'] == 1
    assert len(payload['dentist_breakdown']) == 1
    assert payload['dentist_breakdown'][0]['dentist_id'] == weekly_world['a']


def test_weekly_dentist_view_zeroes_general_expenses(client, weekly_world):
    _login(client, weekly_world['a'], 'drA')
    payload = _weekly(client, weekly_world['monday'])
    assert payload['expenses_paid'] == 0
    assert payload['expenses_postponed'] == 0
    assert payload['expenses'] == 0


def test_weekly_dentist_view_visits_and_plans_stay_clinic_wide(client, weekly_world):
    _login(client, weekly_world['a'], 'drA')
    payload = _weekly(client, weekly_world['monday'])
    assert payload['visits'] == 1
    assert payload['treatment_plans'] == 1


def test_weekly_admin_view_sees_everything(client, weekly_world):
    _login(client, weekly_world['admin'], 'boss')
    payload = _weekly(client, weekly_world['monday'])
    assert payload['revenue'] == 950
    assert payload['appointments'] == 3
    assert len(payload['dentist_breakdown']) == 3
    assert payload['expenses_paid'] == 500
    # 200 seeded directly + 50 auto-mirrored from A's lab-requiring followup.
    assert payload['expenses_postponed'] == 250
    assert payload['expenses'] == 750


def test_weekly_dentist_with_no_rows_gets_empty_breakdown(client, weekly_world):
    c = _user('drC', 'dentist')
    _login(client, c, 'drC')
    payload = _weekly(client, weekly_world['monday'])
    assert payload['dentist_breakdown'] == []
    assert payload['revenue'] == 0
    assert payload['appointments'] == 0
