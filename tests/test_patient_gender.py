"""Cover for the patient gender field on POST /api/patients.

The ``gender`` column already exists and is wired into the edit (PUT) and CSV
import paths, but the add-patient POST handler used to silently drop it. These
tests pin the create path so a male/female pick made in the Add Patient form is
actually persisted.
"""

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize('gender', ['male', 'female'])
def test_create_patient_persists_gender(client, gender):
    resp = client.post('/api/patients', json={
        'first_name': 'Sam', 'last_name': 'Stone', 'gender': gender,
    })
    assert resp.status_code == 200
    created = resp.get_json()
    assert created['gender'] == gender

    # And it survives a round-trip through the list endpoint.
    listed = client.get('/api/patients').get_json()
    assert listed[0]['gender'] == gender


def test_create_patient_without_gender_defaults_blank(client):
    resp = client.post('/api/patients', json={
        'first_name': 'No', 'last_name': 'Gender',
    })
    assert resp.status_code == 200
    # Omitted gender must not error and must come back falsy (blank), never null
    # crash anything downstream.
    assert not resp.get_json().get('gender')
