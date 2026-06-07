"""POST /api/patients must echo the created patient row.

The mobile app creates a patient locally (temp id), POSTs it, then reconciles
its local row to the server-assigned id. The endpoint historically returned
only ``{'success': True}`` with no id/fields, so the app rebuilt the patient
from that bare response — producing a blank-named row that overwrote the one
the user just typed and then white-screened the list on render. The contract
below keeps the endpoint echoing the created row so that reconciliation works.
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


def test_create_patient_echoes_created_row(client):
    response = client.post(
        '/api/patients',
        json={'first_name': 'Wasfy', 'last_name': 'Barzaq', 'phone': '0599000000'},
    )

    assert response.status_code == 200
    payload = response.get_json()

    # Backward-compatible: the web portal only checks resp.ok, so success stays.
    assert payload.get('success') is True
    # New: a real, positive integer id the mobile app can adopt.
    pid = payload.get('id')
    assert isinstance(pid, int) and pid > 0
    # New: the names round-trip so the client never has to guess them.
    assert payload.get('first_name') == 'Wasfy'
    assert payload.get('last_name') == 'Barzaq'

    # The echoed id must reference a row that actually exists.
    listing = client.get('/api/patients').get_json()
    assert any(p['id'] == pid and p['first_name'] == 'Wasfy' for p in listing)


def test_create_patient_still_rejects_missing_names(client):
    response = client.post('/api/patients', json={'first_name': 'OnlyFirst'})
    assert response.status_code == 400
    assert 'error' in (response.get_json() or {})
