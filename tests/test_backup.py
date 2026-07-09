"""Database-backup tests.

Single-tenant: keeps the historic flat layout `backups/dental_clinic_<ts>.db`
and prunes to BACKUP_RETENTION.

Cloud mode: snapshots `cloud_master.db` + every `clinic_<id>.db` into a
per-tenant subfolder under `backups/`, prunes each subfolder independently, and
one tenant's failure doesn't abort the others.
"""

import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def single_tenant(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db_path = data_dir / 'dental_clinic.db'
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    monkeypatch.setattr(dental_clinic, 'BACKUP_RETENTION', 3)
    dental_clinic.init_database()
    return data_dir


@pytest.fixture()
def cloud_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / 'clouddata'
    data_dir.mkdir()
    master = data_dir / 'cloud_master.db'
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', True)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'MASTER_DB_PATH', str(master))
    monkeypatch.setattr(dental_clinic, 'DB_NAME', dental_clinic._DbPathProxy(str(master)))
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', data_dir / 'backups')
    monkeypatch.setattr(dental_clinic, 'BACKUP_RETENTION', 3)
    dental_clinic._set_request_db_path(None)
    dental_clinic.init_database()
    yield data_dir
    dental_clinic._set_request_db_path(None)


def _seed_clinic_db(path, clinic_id):
    """Write a minimal SQLite file at `path` so the backup loop has something
    real to snapshot. Content isn't important — only that the file exists and is
    a valid SQLite DB."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE marker (clinic_id INTEGER, note TEXT)")
    conn.execute("INSERT INTO marker VALUES (?, ?)", (clinic_id, 'hello'))
    conn.commit()
    conn.close()


def test_single_tenant_flat_layout(single_tenant):
    from pathlib import Path
    written = dental_clinic.run_database_backup()
    assert len(written) == 1
    p = Path(written[0])
    # historic layout: directly under backups/, named dental_clinic_<ts>.db (no subfolder)
    assert p.parent == (single_tenant / 'backups')
    assert p.name.startswith('dental_clinic_') and p.suffix == '.db'
    files = sorted((single_tenant / 'backups').glob('dental_clinic_*.db'))
    assert len(files) == 1


def test_automatic_backup_stays_encrypted(single_tenant):
    # Default (decrypt_primary=False, used by the periodic _backup_loop) must
    # keep writing SQLCipher-encrypted snapshots -- at-rest protection should
    # cover backup files sitting on disk too, not just the live DB. Only the
    # explicit, user-initiated "Download Backup" routes opt into plaintext
    # (see tests/test_data_tools_api.py's backup_file/backup_get tests).
    written = dental_clinic.run_database_backup()
    assert len(written) == 1
    assert not dental_clinic._is_plaintext_sqlite(written[0])


def test_decrypt_primary_writes_plaintext_restorable_backup(single_tenant):
    written = dental_clinic.run_database_backup(decrypt_primary=True)
    assert len(written) == 1
    assert dental_clinic._is_plaintext_sqlite(written[0])
    conn = sqlite3.connect(written[0])
    conn.execute('SELECT * FROM patients').fetchall()  # vanilla sqlite3 can open it
    conn.close()


def test_cloud_backs_up_master_and_each_clinic(cloud_dir):
    _seed_clinic_db(cloud_dir / 'clinic_1.db', 1)
    _seed_clinic_db(cloud_dir / 'clinic_2.db', 2)

    written = dental_clinic.run_database_backup()
    # one for master + one per clinic db
    assert len(written) == 3

    backups = cloud_dir / 'backups'
    assert (backups / 'master').is_dir()
    assert (backups / 'clinic_1').is_dir()
    assert (backups / 'clinic_2').is_dir()

    master_files = list((backups / 'master').glob('master_*.db'))
    c1_files = list((backups / 'clinic_1').glob('clinic_1_*.db'))
    c2_files = list((backups / 'clinic_2').glob('clinic_2_*.db'))
    assert len(master_files) == 1
    assert len(c1_files) == 1
    assert len(c2_files) == 1


def test_cloud_no_clinics_yet_still_backs_up_master(cloud_dir):
    written = dental_clinic.run_database_backup()
    assert len(written) == 1
    assert (cloud_dir / 'backups' / 'master').is_dir()
    assert list((cloud_dir / 'backups' / 'master').glob('master_*.db'))


def test_cloud_retention_is_per_label(cloud_dir, monkeypatch):
    # Pretend BACKUP_RETENTION = 3 (set in the fixture). Drop 5 dummy files
    # into clinic_1's subdir and confirm a backup run prunes them down.
    _seed_clinic_db(cloud_dir / 'clinic_1.db', 1)
    sub = cloud_dir / 'backups' / 'clinic_1'
    sub.mkdir(parents=True)
    for stamp in ('20200101_000000', '20200102_000000', '20200103_000000',
                  '20200104_000000', '20200105_000000'):
        (sub / f'clinic_1_{stamp}.db').write_bytes(b'old')

    dental_clinic.run_database_backup()
    # retention = 3 -> only the 3 most-recent should remain (the new real one
    # plus the two most-recent dummies)
    remaining = sorted((sub).glob('clinic_1_*.db'))
    assert len(remaining) == 3
    # the oldest dummies (20200101, 20200102) must be gone
    names = {p.name for p in remaining}
    assert 'clinic_1_20200101_000000.db' not in names
    assert 'clinic_1_20200102_000000.db' not in names


def test_one_corrupt_clinic_does_not_abort_others(cloud_dir):
    _seed_clinic_db(cloud_dir / 'clinic_1.db', 1)
    # clinic_2.db is not a valid SQLite file — backup should fail for it but
    # the master + clinic_1 backups must still succeed.
    (cloud_dir / 'clinic_2.db').write_bytes(b'not a sqlite database')

    written = dental_clinic.run_database_backup()
    backups = cloud_dir / 'backups'
    master_files = list((backups / 'master').glob('master_*.db'))
    c1_files = list((backups / 'clinic_1').glob('clinic_1_*.db'))
    assert len(master_files) == 1
    assert len(c1_files) == 1
    # clinic_2 either has no subdir or no completed snapshot in it
    c2_dir = backups / 'clinic_2'
    if c2_dir.exists():
        assert list(c2_dir.glob('clinic_2_*.db')) == []
    # at minimum master + clinic_1 were written
    assert len(written) >= 2
