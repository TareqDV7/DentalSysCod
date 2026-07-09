"""Tests for the duplicate-patient finder and merge (patient_dedupe.py) plus the
/api/data/duplicate-patients and /api/data/merge-patients routes."""
import sqlite3

import pytest

import dental_clinic
import patient_dedupe


# ── engine fixtures ──────────────────────────────────────────────────────────

def _new_db(path):
    prev = dental_clinic.DB_NAME
    dental_clinic.DB_NAME = str(path)
    try:
        dental_clinic.init_database()
    finally:
        dental_clinic.DB_NAME = prev
    conn = dental_clinic.get_db_connection(with_row_factory=True, db_path=str(path))
    return conn


def _add_patient(conn, first, last):
    cur = conn.execute(
        'INSERT INTO patients (first_name, last_name) VALUES (?, ?)', (first, last))
    return cur.lastrowid


def _give_records(conn, pid):
    """Attach one row to each of three patient-owned tables."""
    conn.execute('INSERT INTO appointments (patient_id, appointment_date) VALUES (?, ?)',
                 (pid, '2026-01-01'))
    conn.execute('INSERT INTO patient_followups (patient_id, followup_date) VALUES (?, ?)',
                 (pid, '2026-01-02'))
    conn.execute('INSERT INTO patient_tooth_chart (patient_id, tooth_no) VALUES (?, ?)',
                 (pid, '11'))


# ── normalize_name ───────────────────────────────────────────────────────────

def test_normalize_name_collapses_whitespace_and_lowercases():
    assert patient_dedupe.normalize_name('  Ahmed ', '  AL  Sayed ') == 'ahmed al sayed'


def test_normalize_name_blank_is_empty():
    assert patient_dedupe.normalize_name('', None) == ''


# ── find_duplicate_groups ────────────────────────────────────────────────────

def test_find_groups_returns_only_repeated_names(tmp_path):
    conn = _new_db(tmp_path / 'd.db')
    a1 = _add_patient(conn, 'Ahmed', 'Ali')
    a2 = _add_patient(conn, 'ahmed', '  ali ')      # same person, sloppy entry
    _add_patient(conn, 'Sara', 'Khan')              # unique → not a group
    conn.commit()

    groups = patient_dedupe.find_duplicate_groups(conn.cursor())
    assert len(groups) == 1
    g = groups[0]
    assert g['name_key'] == 'ahmed ali'
    assert {p['id'] for p in g['patients']} == {a1, a2}


def test_find_groups_orders_by_record_count_and_suggests_survivor(tmp_path):
    conn = _new_db(tmp_path / 'd.db')
    empty = _add_patient(conn, 'Mona', 'Nasser')
    real = _add_patient(conn, 'Mona', 'Nasser')
    _give_records(conn, real)
    conn.commit()

    g = patient_dedupe.find_duplicate_groups(conn.cursor())[0]
    assert g['suggested_survivor_id'] == real           # the one with data
    assert g['patients'][0]['id'] == real
    assert g['patients'][0]['record_count'] == 3
    assert g['patients'][1]['id'] == empty
    assert g['patients'][1]['record_count'] == 0


# ── merge_patients ───────────────────────────────────────────────────────────

def test_merge_reassigns_child_rows_and_deletes_shell(tmp_path):
    conn = _new_db(tmp_path / 'd.db')
    survivor = _add_patient(conn, 'Omar', 'Saleh')
    dup = _add_patient(conn, 'Omar', 'Saleh')
    _give_records(conn, dup)            # all data lives on the duplicate
    conn.commit()

    summary = patient_dedupe.merge_patients(conn.cursor(), survivor, [dup])
    conn.commit()

    # Duplicate's rows now belong to the survivor.
    for table in ('appointments', 'patient_followups', 'patient_tooth_chart'):
        assert conn.execute(
            f'SELECT COUNT(*) FROM {table} WHERE patient_id = ?', (survivor,)).fetchone()[0] == 1
        assert conn.execute(
            f'SELECT COUNT(*) FROM {table} WHERE patient_id = ?', (dup,)).fetchone()[0] == 0
    # The empty shell is gone.
    assert conn.execute('SELECT 1 FROM patients WHERE id = ?', (dup,)).fetchone() is None
    assert summary['survivor_id'] == survivor
    assert summary['merged_ids'] == [dup]
    assert summary['moved']['appointments'] == 1


def test_merge_empty_duplicate_just_removes_it(tmp_path):
    conn = _new_db(tmp_path / 'd.db')
    survivor = _add_patient(conn, 'Lina', 'Adel')
    dup = _add_patient(conn, 'Lina', 'Adel')        # no records at all
    conn.commit()

    summary = patient_dedupe.merge_patients(conn.cursor(), survivor, [dup])
    conn.commit()
    assert conn.execute('SELECT 1 FROM patients WHERE id = ?', (dup,)).fetchone() is None
    assert summary['moved'] == {}


def test_merge_multiple_duplicates(tmp_path):
    conn = _new_db(tmp_path / 'd.db')
    survivor = _add_patient(conn, 'Sami', 'Tah')
    d1 = _add_patient(conn, 'Sami', 'Tah')
    d2 = _add_patient(conn, 'Sami', 'Tah')
    _give_records(conn, d1)
    _give_records(conn, d2)
    conn.commit()

    patient_dedupe.merge_patients(conn.cursor(), survivor, [d1, d2])
    conn.commit()
    assert conn.execute(
        'SELECT COUNT(*) FROM appointments WHERE patient_id = ?', (survivor,)).fetchone()[0] == 2
    assert conn.execute('SELECT COUNT(*) FROM patients').fetchone()[0] == 1


@pytest.mark.parametrize('survivor,dups,msg', [
    (1, [], 'no duplicate_ids'),
    (1, [1], 'cannot also be a duplicate'),
    (1, [2, 2], 'repeats'),
    (999, [1], 'not found'),
])
def test_merge_rejects_bad_input(tmp_path, survivor, dups, msg):
    conn = _new_db(tmp_path / 'd.db')
    _add_patient(conn, 'A', 'B')   # id 1
    _add_patient(conn, 'C', 'D')   # id 2
    conn.commit()
    with pytest.raises(ValueError, match=msg):
        patient_dedupe.merge_patients(conn.cursor(), survivor, dups)


# ── routes ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db = data_dir / 'dental_clinic.db'
    uploads = data_dir / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', uploads)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def _seed_dupes(client):
    conn = dental_clinic.get_db_connection()
    s = conn.execute("INSERT INTO patients (first_name, last_name) VALUES ('Nour', 'Hadi')").lastrowid
    d = conn.execute("INSERT INTO patients (first_name, last_name) VALUES ('nour', ' hadi ')").lastrowid
    conn.execute('INSERT INTO appointments (patient_id, appointment_date) VALUES (?, ?)', (d, '2026-01-01'))
    conn.commit()
    conn.close()
    return s, d


def test_duplicate_patients_requires_login(client):
    assert client.get('/api/data/duplicate-patients').status_code == 401


def test_duplicate_patients_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert client.get('/api/data/duplicate-patients').status_code == 404


def test_duplicate_patients_lists_groups(client):
    _login(client)
    s, d = _seed_dupes(client)
    body = client.get('/api/data/duplicate-patients').get_json()
    assert body['count'] == 1
    assert {p['id'] for p in body['groups'][0]['patients']} == {s, d}


def test_merge_patients_route_requires_login(client):
    assert client.post('/api/data/merge-patients', json={'survivor_id': 1, 'duplicate_ids': [2]}).status_code == 401


def test_merge_patients_route_disabled_on_cloud(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    assert client.post('/api/data/merge-patients', json={'survivor_id': 1, 'duplicate_ids': [2]}).status_code == 404


def test_merge_patients_route_merges(client):
    _login(client)
    s, d = _seed_dupes(client)
    resp = client.post('/api/data/merge-patients', json={'survivor_id': s, 'duplicate_ids': [d]})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    conn = dental_clinic.get_db_connection()
    assert conn.execute('SELECT COUNT(*) FROM patients').fetchone()[0] == 1
    assert conn.execute('SELECT patient_id FROM appointments').fetchone()[0] == s
    conn.close()


def test_merge_patients_route_bad_input_is_400(client):
    _login(client)
    s, _ = _seed_dupes(client)
    assert client.post('/api/data/merge-patients', json={'survivor_id': s, 'duplicate_ids': []}).status_code == 400
