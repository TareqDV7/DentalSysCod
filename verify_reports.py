import os
import sqlite3
from datetime import date

import dental_clinic as dc

TMP_DB = 'test_reports_temp.db'


def must(condition, message):
    if not condition:
        raise AssertionError(message)


def setup_test_data():
    if os.path.exists(TMP_DB):
        os.remove(TMP_DB)

    dc.DB_NAME = TMP_DB
    dc.init_database()

    conn = sqlite3.connect(TMP_DB)
    cur = conn.cursor()

    # Patients
    cur.execute("""
        INSERT INTO patients (first_name, last_name, phone)
        VALUES ('Test', 'Patient', '0500000000')
    """)
    patient_id = cur.lastrowid

    # Appointments: one in target week, one outside
    cur.execute("""
        INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, status)
        VALUES (?, '2026-04-14 10:00:00', 30, 'Checkup', 'scheduled')
    """, (patient_id,))
    cur.execute("""
        INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, status)
        VALUES (?, '2026-04-25 09:00:00', 30, 'Cleaning', 'scheduled')
    """, (patient_id,))

    # Visits: one in target week, one outside
    cur.execute("""
        INSERT INTO visits (patient_id, visit_date, status)
        VALUES (?, '2026-04-16 11:00:00', 'open')
    """, (patient_id,))
    cur.execute("""
        INSERT INTO visits (patient_id, visit_date, status)
        VALUES (?, '2026-04-26 11:00:00', 'open')
    """, (patient_id,))

    # Followups/payments
    cur.execute("""
        INSERT INTO patient_followups (patient_id, followup_date, price, payment, remaining_amount)
        VALUES (?, '2026-04-15', 200, 120, 80)
    """, (patient_id,))
    cur.execute("""
        INSERT INTO patient_followups (patient_id, followup_date, price, payment, remaining_amount)
        VALUES (?, '2026-04-27', 150, 150, 0)
    """, (patient_id,))

    # Expenses
    cur.execute("""
        INSERT INTO expenses (category, amount, expense_date, payment_status)
        VALUES ('Supplies', 30, '2026-04-17', 'paid')
    """)
    cur.execute("""
        INSERT INTO expenses (category, amount, expense_date, payment_status)
        VALUES ('Rent', 70, '2026-04-29', 'paid')
    """)

    # Treatment plans
    cur.execute("""
        INSERT INTO treatment_plans (patient_id, plan_name, start_date)
        VALUES (?, 'Plan A', '2026-04-13')
    """, (patient_id,))
    cur.execute("""
        INSERT INTO treatment_plans (patient_id, plan_name, start_date)
        VALUES (?, 'Plan B', '2026-04-28')
    """, (patient_id,))

    conn.commit()
    conn.close()


def run_api_tests():
    client = dc.app.test_client()

    # Weekly report: week starting Monday 2026-04-13
    r = client.get('/api/reports/weekly?week_start=2026-04-13')
    must(r.status_code == 200, f'weekly status expected 200, got {r.status_code}')
    data = r.get_json()
    must(data['week_start'] == '2026-04-13', 'week_start mismatch')
    must(data['week_end'] == '2026-04-19', 'week_end mismatch')
    must(data['appointments'] == 1, f"appointments expected 1, got {data['appointments']}")
    must(data['visits'] == 1, f"visits expected 1, got {data['visits']}")
    must(abs(data['revenue'] - 120.0) < 1e-9, f"revenue expected 120.0, got {data['revenue']}")
    must(abs(data['expenses'] - 30.0) < 1e-9, f"expenses expected 30.0, got {data['expenses']}")
    must(abs(data['profit'] - 90.0) < 1e-9, f"profit expected 90.0, got {data['profit']}")
    must(data['treatment_plans'] == 1, f"treatment_plans expected 1, got {data['treatment_plans']}")

    # Weekly invalid input
    r = client.get('/api/reports/weekly?week_start=bad-date')
    must(r.status_code == 400, f'invalid weekly date expected 400, got {r.status_code}')

    # Summary with full range
    r = client.get('/api/reports/summary?start_date=2026-04-13&end_date=2026-04-19')
    must(r.status_code == 200, f'summary status expected 200, got {r.status_code}')
    data = r.get_json()
    must(data['appointments'] == 1, f"summary appointments expected 1, got {data['appointments']}")
    must(data['visits'] == 1, f"summary visits expected 1, got {data['visits']}")
    must(abs(data['revenue'] - 120.0) < 1e-9, f"summary revenue expected 120.0, got {data['revenue']}")
    must(abs(data['expenses'] - 30.0) < 1e-9, f"summary expenses expected 30.0, got {data['expenses']}")
    must(abs(data['profit'] - 90.0) < 1e-9, f"summary profit expected 90.0, got {data['profit']}")
    must(data['treatment_plans'] == 1, f"summary treatment_plans expected 1, got {data['treatment_plans']}")

    # Summary start-only filter (after we expanded date_clause)
    r = client.get('/api/reports/summary?start_date=2026-04-20')
    must(r.status_code == 200, f'summary start-only expected 200, got {r.status_code}')
    data = r.get_json()
    must(data['appointments'] == 1, f"start-only appointments expected 1, got {data['appointments']}")
    must(data['visits'] == 1, f"start-only visits expected 1, got {data['visits']}")
    must(abs(data['revenue'] - 150.0) < 1e-9, f"start-only revenue expected 150.0, got {data['revenue']}")
    must(abs(data['expenses'] - 70.0) < 1e-9, f"start-only expenses expected 70.0, got {data['expenses']}")
    must(abs(data['profit'] - 80.0) < 1e-9, f"start-only profit expected 80.0, got {data['profit']}")
    must(data['treatment_plans'] == 1, f"start-only treatment_plans expected 1, got {data['treatment_plans']}")


def run_ui_string_tests():
    html = dc.HTML_TEMPLATE
    must('₪ 0' in html, 'ILS placeholders missing in template')
    must('loadWeeklyReport()' in html, 'Weekly report button/function hook missing')
    must("/api/reports/weekly" in html, 'Weekly report API call missing in JS')


if __name__ == '__main__':
    setup_test_data()
    run_api_tests()
    run_ui_string_tests()
    print('ALL TESTS PASSED')
    if os.path.exists(TMP_DB):
        os.remove(TMP_DB)
