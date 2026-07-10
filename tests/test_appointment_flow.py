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


def _insert_patient(first_name='John', last_name='Doe'):
    conn = dental_clinic.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO patients (first_name, last_name, phone)
        VALUES (?, ?, ?)
        ''',
        (first_name, last_name, '0500000000'),
    )
    patient_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return patient_id


def test_create_appointment_returns_normalized_non_null_payload(client):
    patient_id = _insert_patient('Jane', 'Smith')

    response = client.post(
        '/api/appointments',
        json={
            'patient_id': patient_id,
            'appointment_date': '2026-05-11T09:30',
            'duration': 45,
            'treatment_type': 'Cleaning',
            'notes': 'Initial visit',
        },
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload['id']
    assert payload['patient_id'] == patient_id
    assert payload['patient_name'] == 'Jane Smith'
    assert payload['appointment_date'] == '2026-05-11 09:30:00'
    assert payload['appointment_datetime'] == '2026-05-11 09:30:00'
    assert payload['duration'] == 45
    assert payload['duration_minutes'] == 45


def test_create_appointment_rejects_missing_required_fields(client):
    response_missing_patient = client.post(
        '/api/appointments',
        json={'appointment_date': '2026-05-11T09:30'},
    )
    assert response_missing_patient.status_code == 400
    assert 'patient' in response_missing_patient.get_json()['error'].lower()

    patient_id = _insert_patient('No', 'Date')

    response_missing_date = client.post(
        '/api/appointments',
        json={'patient_id': patient_id},
    )
    assert response_missing_date.status_code == 400
    assert response_missing_date.get_json()['error'] == 'Appointment date is required'

    response_missing_time = client.post(
        '/api/appointments',
        json={
            'patient_id': patient_id,
            'appointment_date': '2026-05-11',
        },
    )
    assert response_missing_time.status_code == 400
    assert response_missing_time.get_json()['error'] == 'Appointment time is required'


def test_appointments_list_never_returns_null_display_fields(client):
    patient_id = _insert_patient('Legacy', 'Patient')

    conn = dental_clinic.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO appointments (patient_id, appointment_date, duration, treatment_type, notes)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (patient_id, '2026-05-12 10:00:00', 30, None, None),
    )
    conn.commit()
    conn.close()

    response = client.get('/api/appointments')
    assert response.status_code == 200

    rows = response.get_json()
    assert rows

    row = rows[0]
    assert row['patient_name'] not in (None, 'null', 'undefined', '')
    assert row['appointment_date'] not in (None, 'null', 'undefined', '')
    assert row['appointment_datetime'] not in (None, 'null', 'undefined', '')
    assert row['treatment_type'] is not None
    assert row['notes'] is not None
