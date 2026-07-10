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


def test_create_appointment_valid(client):
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

    assert payload.get('id')
    assert payload.get('patient_id') == patient_id
    assert payload.get('patient_name') == 'Jane Smith'
    assert payload.get('appointment_date') == '2026-05-11 09:30:00'
    assert payload.get('appointment_datetime') == '2026-05-11 09:30:00'
    assert payload.get('duration') == 45


def test_reject_missing_patient(client):
    response = client.post('/api/appointments', json={'appointment_date': '2026-05-11T09:30'})
    assert response.status_code == 400
    assert 'patient' in (response.get_json() or {}).get('error', '').lower()


def test_reject_missing_date(client):
    patient_id = _insert_patient('No', 'Date')

    response = client.post('/api/appointments', json={'patient_id': patient_id})
    assert response.status_code == 400


def test_reject_missing_time(client):
    patient_id = _insert_patient('No', 'Time')

    response = client.post(
        '/api/appointments',
        json={
            'patient_id': patient_id,
            'appointment_date': '2026-05-11',
        },
    )
    assert response.status_code == 400


def test_calendar_api_returns_non_null_fields(client):
    # insert patient and an appointment with some nullable fields
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
    assert rows and len(rows) > 0

    row = rows[0]
    # these fields should not be null/empty when returned by the API
    assert row.get('patient_name') not in (None, '', 'null', 'undefined')
    assert row.get('appointment_date') not in (None, '', 'null', 'undefined')
    assert row.get('appointment_datetime') not in (None, '', 'null', 'undefined')
    assert 'treatment_type' in row
    assert 'notes' in row


def test_update_appointment_status_with_put(client):
    patient_id = _insert_patient('Status', 'Patient')

    create_response = client.post(
        '/api/appointments',
        json={
            'patient_id': patient_id,
            'appointment_date': '2026-05-12T11:00',
            'duration': 30,
        },
    )
    assert create_response.status_code == 200
    appointment_id = create_response.get_json()['id']

    update_response = client.put(
        f'/api/appointments/{appointment_id}/status',
        json={'status': 'completed'},
    )
    assert update_response.status_code == 200
    assert update_response.get_json().get('success') is True

    conn = dental_clinic.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM appointments WHERE id = ?', (appointment_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 'completed'


def test_delete_appointment_endpoint(client):
    patient_id = _insert_patient('Delete', 'Patient')

    create_response = client.post(
        '/api/appointments',
        json={
            'patient_id': patient_id,
            'appointment_date': '2026-05-13T14:00',
            'duration': 30,
        },
    )
    assert create_response.status_code == 200
    appointment_id = create_response.get_json()['id']

    delete_response = client.delete(f'/api/appointments/{appointment_id}')
    assert delete_response.status_code == 200
    assert delete_response.get_json().get('success') is True

    conn = dental_clinic.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM appointments WHERE id = ?', (appointment_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is None
