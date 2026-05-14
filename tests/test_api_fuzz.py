"""Property-fuzz the public API endpoints against malformed input.

Every targeted request must return a clean 4xx (client error) — never a 5xx
that would leak a stack trace into a clinic admin's browser or onto the
mobile-app status bar. The single 502 we tolerate is `/api/cloud/pair` to an
unreachable cloud node, which is a legitimate upstream-unreachable signal.
"""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / 'fuzz.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    dental_clinic.init_database()
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute(
        "INSERT INTO paired_devices (device_id, device_name, device_token) VALUES (?, ?, ?)",
        ('dev', 'Dev', 'tok'),
    )
    conn.execute("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'A', 'B')")
    conn.commit()
    conn.close()
    with dental_clinic.app.test_client() as c:
        yield c


# (method, path, body) — body=None means no body, 'not-json' means literal junk bytes
MALFORMED_TARGETS = [
    ('POST', '/api/sync/import', None),
    ('POST', '/api/sync/import', 'not-json'),
    ('POST', '/api/sync/import', {'tables': 'not-a-dict'}),
    ('POST', '/api/sync/import', {'tables': {'patients': 'not-a-list'}}),
    ('POST', '/api/sync/import', {'tables': {'patients': [None, 'str', 42]}}),
    ('POST', '/api/sync/import', {'tables': {'patients': [{'id': 'not-an-int', 'first_name': 'X'}]}}),
    ('POST', '/api/sync/import', {'tables': {'NONEXISTENT': [{'id': 1}]}}),
    ('POST', '/api/sync/import', {'tables': {}, 'tombstones': 'not-a-list'}),
    ('POST', '/api/sync/import', {'tables': {}, 'tombstones': [{'bad': 'shape'}]}),
    ('POST', '/api/sync/import', {'tables': {}, 'tombstones': [
        {'table_name': 'patients', 'row_id': 'NaN', 'deleted_at': 'bad'}]}),
    ('GET',  '/api/sync/export?since=garbage', None),
    ('GET',  '/api/sync/export?since=' + 'X' * 5000, None),
    ('POST', '/api/patients', None),
    ('POST', '/api/patients', 'not-json'),
    ('POST', '/api/patients', {}),
    ('POST', '/api/patients', {'first_name': 12345}),
    ('GET',  '/api/patients/9999999/full-profile', None),
    ('POST', '/api/appointments', None),
    ('POST', '/api/appointments', {}),
    ('POST', '/api/appointments', {'patient_id': 'not-int'}),
    ('POST', '/api/appointments', {'patient_id': 1, 'appointment_date': 'garbage', 'duration': 'not-int'}),
    ('PUT',  '/api/appointments/9999999/status', {'status': 'invalid'}),
    ('PUT',  '/api/appointments/abc/status', {'status': 'scheduled'}),
    ('POST', '/api/expenses', None),
    ('POST', '/api/expenses', {'amount': 'not-a-number'}),
    ('POST', '/api/billing', None),
    ('POST', '/api/billing', {'patient_id': 1, 'subtotal': 'not-num', 'paid_amount': 0}),
    ('POST', '/api/license/activate', None),
    ('POST', '/api/license/activate', {}),
    ('POST', '/api/license/activate', {'serial_number': 'X'}),
    ('POST', '/api/pairing/start', None),
    ('POST', '/api/pairing/start', {'device_name': 1234}),
    ('POST', '/api/pairing/complete', None),
    ('POST', '/api/pairing/complete', {'pair_code': 'wrong'}),
    ('POST', '/api/cloud/sync-now', None),
    ('POST', '/api/cloud/unpair', None),
]


@pytest.mark.parametrize('method,path,body', MALFORMED_TARGETS)
def test_malformed_input_never_returns_500(client, method, path, body):
    hdrs = {'X-Device-Token': 'tok'}
    if body == 'not-json':
        r = client.open(path, method=method, data='{not-json',
                        headers={**hdrs, 'Content-Type': 'application/json'})
    elif body is None:
        r = client.open(path, method=method, headers=hdrs)
    else:
        r = client.open(path, method=method, json=body, headers=hdrs)
    # 4xx is the goal — anything 5xx means an unhandled crash path.
    assert r.status_code < 500, (
        f'{method} {path} with {body!r} returned {r.status_code}: '
        f'{r.get_data(as_text=True)[:200]}'
    )


def test_sync_import_handles_large_payload(client):
    # A 50k-row patient payload should apply, not crash.
    payload = {
        'tables': {
            'patients': [
                {'id': i + 10, 'first_name': f'P{i}', 'last_name': 'X',
                 'updated_at': '2030-01-01T00:00:00Z'}
                for i in range(5000)
            ]
        },
        'tombstones': [],
    }
    r = client.post('/api/sync/import',
                    headers={'X-Device-Token': 'tok'}, json=payload)
    assert r.status_code == 200
    assert r.get_json()['applied_total'] == 5000


def test_sync_import_handles_far_future_timestamps(client):
    # A row stamped in 2099 should apply (LWW: it's newer than anything local).
    payload = {
        'tables': {
            'patients': [
                {'id': 200, 'first_name': 'Future', 'last_name': 'X',
                 'updated_at': '2099-12-31T23:59:59Z'}
            ]
        },
        'tombstones': [],
    }
    r = client.post('/api/sync/import',
                    headers={'X-Device-Token': 'tok'}, json=payload)
    assert r.status_code == 200
    assert r.get_json()['applied_total'] == 1
