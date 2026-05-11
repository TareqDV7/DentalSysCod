"""Sync tombstone + incremental-export tests (Phase 0 of the cloud sync work).

These cover the gap the plain row-merge sync had: a delete on one device used to be
undone the next time another device pushed the (stale) row back. Deletions are now
recorded in ``sync_tombstones`` and propagated, with last-write-wins by timestamp.
"""

import sqlite3

import pytest

import dental_clinic


AUTH = {'X-Device-Token': 'test-token'}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'clinic_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()

    # A paired device so the /api/sync/* endpoints accept our requests.
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO paired_devices (device_id, device_name, device_token) VALUES (?, ?, ?)',
        ('dev-test', 'Test Device', 'test-token'),
    )
    conn.commit()
    conn.close()

    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _insert_patient(first_name='John', last_name='Doe', phone='0500000000'):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO patients (first_name, last_name, phone) VALUES (?, ?, ?)',
        (first_name, last_name, phone),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def _set_patient_timestamps(pid, ts):
    # The AFTER-UPDATE trigger would otherwise reset updated_at to CURRENT_TIMESTAMP,
    # so drop it for the write and put it back exactly as the app defines it.
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('DROP TRIGGER IF EXISTS trg_patients_updated_at')
    cur.execute('UPDATE patients SET updated_at = ?, created_at = ? WHERE id = ?', (ts, ts, pid))
    dental_clinic.ensure_updated_at_trigger(cur, 'patients')
    conn.commit()
    conn.close()


def _patient_exists(pid):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT id FROM patients WHERE id = ?', (pid,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def _tombstone(table_name, row_id):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    cur = conn.cursor()
    cur.execute(
        'SELECT deleted_at FROM sync_tombstones WHERE table_name = ? AND row_id = ?',
        (table_name, row_id),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def test_delete_patient_records_tombstone(client):
    pid = _insert_patient()
    resp = client.delete(f'/api/patients/{pid}')
    assert resp.status_code == 200
    assert not _patient_exists(pid)
    assert _tombstone('patients', pid)


def test_delete_appointment_and_billing_record_tombstones(client):
    pid = _insert_patient('Has', 'Records')
    appt = client.post('/api/appointments', json={
        'patient_id': pid, 'appointment_date': '2026-06-01T10:00', 'duration': 30,
    })
    appt_id = appt.get_json()['id']
    assert client.delete(f'/api/appointments/{appt_id}').status_code == 200
    assert _tombstone('appointments', appt_id)


def test_export_includes_tombstones(client):
    pid = _insert_patient()
    client.delete(f'/api/patients/{pid}')

    resp = client.get('/api/sync/export', headers=AUTH)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['incremental'] is False
    matching = [t for t in data['tombstones'] if t['table_name'] == 'patients' and t['row_id'] == pid]
    assert len(matching) == 1


def test_import_tombstone_deletes_older_local_row(client):
    pid = _insert_patient('Imported', 'Patient')
    _set_patient_timestamps(pid, '2000-01-01 00:00:00')

    resp = client.post('/api/sync/import', headers=AUTH, json={
        'tables': {},
        'tombstones': [{'table_name': 'patients', 'row_id': pid, 'deleted_at': '2030-01-01 00:00:00'}],
    })
    assert resp.status_code == 200
    assert resp.get_json()['tombstones_applied'] == 1
    assert not _patient_exists(pid)
    assert _tombstone('patients', pid)


def test_import_tombstone_keeps_newer_local_row(client):
    pid = _insert_patient('Edited', 'Locally')
    _set_patient_timestamps(pid, '2099-01-01 00:00:00')

    resp = client.post('/api/sync/import', headers=AUTH, json={
        'tables': {},
        'tombstones': [{'table_name': 'patients', 'row_id': pid, 'deleted_at': '2030-01-01 00:00:00'}],
    })
    assert resp.status_code == 200
    assert resp.get_json()['tombstones_applied'] == 0
    assert _patient_exists(pid)


def test_import_does_not_resurrect_deleted_row(client):
    pid = _insert_patient('Ghost', 'Patient')
    client.delete(f'/api/patients/{pid}')  # records a tombstone dated "now"

    resp = client.post('/api/sync/import', headers=AUTH, json={
        'tables': {
            'patients': [{
                'id': pid, 'first_name': 'Ghost', 'last_name': 'Patient', 'phone': '0500000000',
                'updated_at': '2000-01-01 00:00:00', 'created_at': '2000-01-01 00:00:00',
            }]
        }
    })
    assert resp.status_code == 200
    assert not _patient_exists(pid)


def test_import_newer_row_overrides_tombstone(client):
    pid = _insert_patient('Reborn', 'Patient')
    client.delete(f'/api/patients/{pid}')

    resp = client.post('/api/sync/import', headers=AUTH, json={
        'tables': {
            'patients': [{
                'id': pid, 'first_name': 'Reborn', 'last_name': 'Patient', 'phone': '0500000001',
                'updated_at': '2099-01-01 00:00:00', 'created_at': '2099-01-01 00:00:00',
            }]
        }
    })
    assert resp.status_code == 200
    assert resp.get_json()['applied_total'] == 1
    assert _patient_exists(pid)
    assert _tombstone('patients', pid) is None  # stale tombstone cleared


def test_incremental_export_since_filters_unchanged_rows(client):
    p_old = _insert_patient('Old', 'One', phone='0500000010')
    p_new = _insert_patient('New', 'Two', phone='0500000011')
    _set_patient_timestamps(p_old, '2000-01-01 00:00:00')
    _set_patient_timestamps(p_new, '2099-01-01 00:00:00')

    resp = client.get(
        '/api/sync/export', headers=AUTH, query_string={'since': '2050-01-01 00:00:00'}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['incremental'] is True
    ids = [r['id'] for r in data['tables']['patients']]
    assert p_new in ids
    assert p_old not in ids


def test_incremental_export_since_filters_old_tombstones(client):
    pid = _insert_patient()
    client.delete(f'/api/patients/{pid}')  # tombstone dated "now"
    # A 'since' far in the future should exclude that tombstone.
    resp = client.get(
        '/api/sync/export', headers=AUTH, query_string={'since': '2099-01-01 00:00:00'}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(t['row_id'] != pid for t in data['tombstones'])
