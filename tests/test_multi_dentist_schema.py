"""users.is_dentist + dentist_id on appointments/patient_followups/billing,
and the GET /api/dentists lookup that feeds both the desktop dropdowns and
mobile's picker (mobile has no session, so this endpoint stays unauthenticated
like /api/patients already is)."""
import dental_clinic
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / 'multi_dentist_schema_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as test_client:
        yield test_client


def _make_user(is_dentist=1, is_active=1, username='drtest', display_name='Dr. Test'):
    conn = dental_clinic.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO users (username, password_hash, display_name, is_active, is_dentist) '
        'VALUES (?, ?, ?, ?, ?)',
        (username, 'x', display_name, is_active, is_dentist),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def test_schema_has_dentist_id_columns(client):
    conn = dental_clinic.get_db_connection()
    for table in ('appointments', 'patient_followups', 'billing'):
        cols = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        assert 'dentist_id' in cols, table
    user_cols = {row[1] for row in conn.execute('PRAGMA table_info(users)')}
    assert 'is_dentist' in user_cols
    conn.close()


def test_get_dentists_lists_only_active_dentists(client):
    d1 = _make_user(is_dentist=1, is_active=1, username='d1', display_name='Dr. Amy')
    _make_user(is_dentist=0, is_active=1, username='front_desk', display_name='Front Desk')
    _make_user(is_dentist=1, is_active=0, username='d_inactive', display_name='Dr. Gone')

    resp = client.get('/api/dentists')
    assert resp.status_code == 200
    rows = resp.get_json()
    assert [r['id'] for r in rows] == [d1]
    assert rows[0]['display_name'] == 'Dr. Amy'


def test_get_dentists_ordered_by_display_name(client):
    _make_user(username='d2', display_name='Dr. Zed')
    _make_user(username='d3', display_name='Dr. Amy')

    resp = client.get('/api/dentists')
    names = [r['display_name'] for r in resp.get_json()]
    assert names == sorted(names)


def test_get_dentists_requires_no_session(client):
    # Mobile has no session at all -- this must be reachable without login,
    # matching /api/patients' existing open posture.
    resp = client.get('/api/dentists')
    assert resp.status_code == 200
