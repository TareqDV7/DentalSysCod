"""Local ⇄ cloud background sync tests (Phase 2 of the cloud sync work).

The clinic's local server periodically pulls then pushes a delta against the
cloud node's /api/sync/* endpoints. Here the "cloud" is a small in-memory shim
backed by a second SQLite file, driven through the *same* shared helpers
(`_collect_sync_export` / `_apply_sync_import`) the real endpoints use — so this
exercises the worker's pull→push cycle, `since` tracking, and deletion
propagation end to end without standing up a second HTTP server.
"""

import sqlite3
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

import pytest

import dental_clinic


def _make_cloud_shim(cloud_db):
    """A fake _cloud_http_request that serves the sync (and register) endpoints
    directly against `cloud_db`."""
    def shim(method, url, headers=None, body=None, timeout=15):
        path = urlsplit(url).path
        query = urlsplit(url).query
        cc = sqlite3.connect(cloud_db)
        cc.row_factory = sqlite3.Row
        cur = cc.cursor()
        try:
            if path == '/api/clinics/register':
                return 200, {'success': True, 'already_registered': False,
                             'clinic_id': 1, 'clinic_name': (body or {}).get('clinic_name'),
                             'clinic_token': 'cloud-clinic-token'}
            if path == '/api/sync/export':
                since = parse_qs(query).get('since', [None])[0]
                since_dt = dental_clinic.parse_timestamp_for_sync(since) if since else None
                tables, tombstones, total = dental_clinic._collect_sync_export(cur, since_dt)
                cc.commit()
                return 200, {'success': True, 'generated_at': dental_clinic.utc_now_iso(),
                             'incremental': since_dt is not None, 'record_count': total,
                             'tables': tables, 'tombstones': tombstones}
            if path == '/api/sync/import':
                a, s, t, bt = dental_clinic._apply_sync_import(cur, body or {})
                cc.commit()
                return 200, {'success': True, 'applied_total': a, 'skipped_total': s,
                             'tombstones_applied': t, 'by_table': bt}
            return 404, {'error': 'not found'}
        finally:
            cc.close()
    return shim


@pytest.fixture()
def env(tmp_path, monkeypatch):
    local_db = str(tmp_path / 'local.db')
    cloud_db = str(tmp_path / 'cloud_clinic.db')
    monkeypatch.setattr(dental_clinic, 'DB_NAME', local_db)
    dental_clinic.init_database()
    monkeypatch.setattr(dental_clinic, 'DB_NAME', cloud_db)
    dental_clinic.init_database()
    monkeypatch.setattr(dental_clinic, 'DB_NAME', local_db)  # the app runs as the local server
    return SimpleNamespace(local_db=local_db, cloud_db=cloud_db, http=_make_cloud_shim(cloud_db))


# --- helpers that talk straight to a DB file --------------------------------
# (explicit ids keep the two sides from colliding — the id-keyed sync would
#  otherwise treat "local patient 1" and "cloud patient 1" as the same row;
#  explicit timestamps sidestep CURRENT_TIMESTAMP's 1-second granularity in
#  sub-second-fast tests.)

def _add_patient(db, first_name, pid, created_at=None, last_name='X', phone='000'):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    if created_at:
        cur.execute('INSERT INTO patients (id, first_name, last_name, phone, created_at) VALUES (?, ?, ?, ?, ?)',
                    (pid, first_name, last_name, phone, created_at))
    else:
        cur.execute('INSERT INTO patients (id, first_name, last_name, phone) VALUES (?, ?, ?, ?)',
                    (pid, first_name, last_name, phone))
    conn.commit()
    conn.close()
    return pid


def _patient_names(db):
    conn = sqlite3.connect(db)
    rows = conn.execute('SELECT first_name FROM patients ORDER BY first_name').fetchall()
    conn.close()
    return [r[0] for r in rows]


def _delete_patient_with_tombstone(db, pid, deleted_at='2099-01-01 00:00:00'):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('DELETE FROM patients WHERE id = ?', (pid,))
    dental_clinic.record_tombstone(cur, 'patients', pid, deleted_at)
    conn.commit()
    conn.close()


def _setting(db, key):
    conn = sqlite3.connect(db)
    row = conn.execute('SELECT value FROM app_settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row[0] if row else None


# --- tests ------------------------------------------------------------------

def test_push_then_pull_round_trip(env):
    _add_patient(env.local_db, 'LocalAlice', pid=1)
    _add_patient(env.cloud_db, 'CloudBob', pid=1001)

    result = dental_clinic._run_cloud_sync_once('http://cloud', 'tok', http=env.http)
    assert result['ok'] is True, result

    # local pushed up, and pulled cloud's down
    assert 'LocalAlice' in _patient_names(env.cloud_db)
    assert 'CloudBob' in _patient_names(env.local_db)
    # bookkeeping recorded
    assert _setting(env.local_db, 'cloud_last_sync_result') == 'ok'
    assert _setting(env.local_db, 'cloud_last_pull_at')
    assert _setting(env.local_db, 'cloud_last_push_at')


def test_incremental_pull_after_first_sync(env):
    dental_clinic._run_cloud_sync_once('http://cloud', 'tok', http=env.http)   # first sync (full)
    _add_patient(env.cloud_db, 'LateArrival', pid=1001, created_at='2099-01-01 00:00:00')
    result = dental_clinic._run_cloud_sync_once('http://cloud', 'tok', http=env.http)
    assert result['ok'] is True
    assert result['pulled'] == 1                       # only the one new row, thanks to ?since=
    assert 'LateArrival' in _patient_names(env.local_db)


def test_deletion_propagates_local_to_cloud(env):
    pid = _add_patient(env.local_db, 'WillBeDeleted', pid=1)
    dental_clinic._run_cloud_sync_once('http://cloud', 'tok', http=env.http)
    assert 'WillBeDeleted' in _patient_names(env.cloud_db)

    _delete_patient_with_tombstone(env.local_db, pid)
    dental_clinic._run_cloud_sync_once('http://cloud', 'tok', http=env.http)
    assert 'WillBeDeleted' not in _patient_names(env.cloud_db)


def test_offline_is_recorded_not_raised(env):
    def broken_http(*a, **k):
        raise OSError('connection refused')
    result = dental_clinic._run_cloud_sync_once('http://cloud', 'tok', http=broken_http)
    assert result['ok'] is False
    assert 'error' in result
    assert (_setting(env.local_db, 'cloud_last_sync_result') or '').startswith('error')


def test_pair_and_status_endpoints(env, monkeypatch):
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', env.http)  # /api/cloud/pair uses this internally
    with dental_clinic.app.test_client() as client:
        before = client.get('/api/cloud/status').get_json()
        assert before['cloud_mode'] is False
        assert before['configured'] is False

        r = client.post('/api/cloud/pair', json={'cloud_url': 'http://cloud', 'serial_number': 'PAIRTEST-0001'})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body['success'] is True
        assert body['first_sync']['ok'] is True

        after = client.get('/api/cloud/status').get_json()
        assert after['configured'] is True
        assert after['cloud_url'] == 'http://cloud'
        assert after['last_sync_result'] == 'ok'

        # sync-now works once paired
        assert client.post('/api/cloud/sync-now').status_code == 200
        # unpair clears it
        assert client.post('/api/cloud/unpair').status_code == 200
        assert client.get('/api/cloud/status').get_json()['configured'] is False


def test_sync_now_requires_pairing(env):
    with dental_clinic.app.test_client() as client:
        r = client.post('/api/cloud/sync-now')
        assert r.status_code == 400
