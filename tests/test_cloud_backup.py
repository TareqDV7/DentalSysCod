"""Tests for the standalone cloud backup script (cloud/backup.py).

Two layers:
  * Pure retention logic (`select_dirs_to_prune`) — the meat of the rotation
    policy, exhaustively unit-tested with no filesystem.
  * A cheap round-trip: back up a tiny temp SQLite DB and reopen the snapshot
    (both plain and gzipped) to prove the online-backup API path works.

Stdlib + pytest only, mirroring the existing tests/ style (tmp_path fixtures,
small SQLite helpers).
"""
import gzip
import importlib.util
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

# cloud/ isn't a package on sys.path, so load backup.py by file path.
_BACKUP_PY = Path(__file__).resolve().parent.parent / "cloud" / "backup.py"
_spec = importlib.util.spec_from_file_location("cloud_backup", _BACKUP_PY)
backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backup)


def _stamp(dt: datetime) -> str:
    return dt.strftime(backup.TIMESTAMP_FMT)


def _make_sqlite_db(path: Path, value: str = "hello") -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE marker (note TEXT)")
        conn.execute("INSERT INTO marker VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(n: int) -> str:
    """A timestamp-dir name `n` days before NOW."""
    return _stamp(datetime.fromtimestamp(NOW.timestamp() - n * 86400, tz=timezone.utc))


# --------------------------------------------------------------------------- #
# select_dirs_to_prune — the pure retention policy
# --------------------------------------------------------------------------- #
def test_nothing_to_prune_when_all_within_retention():
    # Three dirs, all 1-3 days old, retention 14 days, min_keep 7 -> keep all.
    dirs = [_days_ago(1), _days_ago(2), _days_ago(3)]
    pruned = backup.select_dirs_to_prune(dirs, NOW, retention_days=14, min_keep=7)
    assert pruned == []


def test_prunes_only_dirs_older_than_retention():
    # min_keep small so age is the deciding factor. retention=14 days.
    recent = [_days_ago(1), _days_ago(5), _days_ago(10)]  # within retention
    old = [_days_ago(20), _days_ago(40)]                  # beyond retention
    pruned = backup.select_dirs_to_prune(
        recent + old, NOW, retention_days=14, min_keep=2
    )
    assert set(pruned) == set(old)
    # none of the recent ones got pruned
    for d in recent:
        assert d not in pruned


def test_never_prunes_below_min_keep_even_if_all_old():
    # Every dir is ancient (100+ days), but min_keep=7 must be honoured.
    dirs = [_days_ago(100 + i) for i in range(10)]  # 10 very old dirs
    pruned = backup.select_dirs_to_prune(dirs, NOW, retention_days=14, min_keep=7)
    # Exactly the 3 oldest are eligible (10 - 7 kept). Newest 7 protected.
    assert len(pruned) == 3
    remaining = set(dirs) - set(pruned)
    assert len(remaining) == 7
    # The pruned ones are the very oldest.
    oldest_three = sorted(dirs)[:3]
    assert set(pruned) == set(oldest_three)


def test_min_keep_zero_prunes_everything_old():
    dirs = [_days_ago(20), _days_ago(30), _days_ago(40)]
    pruned = backup.select_dirs_to_prune(dirs, NOW, retention_days=14, min_keep=0)
    assert set(pruned) == set(dirs)


def test_deterministic_oldest_first_ordering():
    dirs = [_days_ago(40), _days_ago(20), _days_ago(60), _days_ago(30)]
    pruned = backup.select_dirs_to_prune(dirs, NOW, retention_days=14, min_keep=0)
    # All are older than retention; result must be oldest-first regardless of
    # input order.
    assert pruned == [_days_ago(60), _days_ago(40), _days_ago(30), _days_ago(20)]


def test_ignores_unparseable_dir_names():
    # Foreign dirs (not in our timestamp format) are never pruned.
    dirs = ["not-a-timestamp", "latest", _days_ago(40)]
    pruned = backup.select_dirs_to_prune(dirs, NOW, retention_days=14, min_keep=0)
    assert pruned == [_days_ago(40)]


def test_exactly_at_retention_boundary_is_kept():
    # A dir exactly `retention_days` old is NOT older-than, so it stays.
    dirs = [_days_ago(14)]
    pruned = backup.select_dirs_to_prune(dirs, NOW, retention_days=14, min_keep=0)
    assert pruned == []


# --------------------------------------------------------------------------- #
# Round-trip: snapshot a real SQLite DB and reopen it
# --------------------------------------------------------------------------- #
def test_snapshot_roundtrip_plain(tmp_path):
    src = tmp_path / "clinic_1.db"
    _make_sqlite_db(src, "round-trip")
    dest = tmp_path / "snap" / "clinic_1.db"

    out = backup.snapshot_database(src, dest, use_gzip=False)
    assert out == dest
    assert out.exists()

    conn = sqlite3.connect(str(out))
    try:
        row = conn.execute("SELECT note FROM marker").fetchone()
    finally:
        conn.close()
    assert row[0] == "round-trip"


def test_snapshot_roundtrip_gzip(tmp_path):
    src = tmp_path / "cloud_master.db"
    _make_sqlite_db(src, "gzipped")
    dest = tmp_path / "snap" / "cloud_master.db"

    out = backup.snapshot_database(src, dest, use_gzip=True)
    assert out.name.endswith(".db.gz")
    assert out.exists()
    # The intermediate uncompressed file must be gone.
    assert not dest.exists()

    # Decompress and reopen.
    restored = tmp_path / "restored.db"
    with gzip.open(out, "rb") as f_in:
        restored.write_bytes(f_in.read())
    conn = sqlite3.connect(str(restored))
    try:
        row = conn.execute("SELECT note FROM marker").fetchone()
    finally:
        conn.close()
    assert row[0] == "gzipped"


def test_run_once_snapshots_all_dbs_and_writes_timestamped_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_sqlite_db(data_dir / "cloud_master.db", "master")
    _make_sqlite_db(data_dir / "clinic_1.db", "one")
    _make_sqlite_db(data_dir / "clinic_2.db", "two")
    backup_dir = tmp_path / "backups"

    written = backup.run_once(
        data_dir, backup_dir, use_gzip=False, retention_days=14, min_keep=7, now=NOW
    )
    assert len(written) == 3
    snap_dir = backup_dir / _stamp(NOW)
    assert snap_dir.is_dir()
    names = {p.name for p in snap_dir.glob("*.db")}
    assert names == {"cloud_master.db", "clinic_1.db", "clinic_2.db"}


def test_run_once_skips_corrupt_db_but_keeps_others(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_sqlite_db(data_dir / "cloud_master.db", "ok")
    (data_dir / "clinic_bad.db").write_bytes(b"not a sqlite database at all")
    backup_dir = tmp_path / "backups"

    written = backup.run_once(
        data_dir, backup_dir, use_gzip=False, retention_days=14, min_keep=7, now=NOW
    )
    # The good DB is snapshotted; the corrupt one is skipped (no stub left).
    out_names = {Path(p).name for p in written}
    assert "cloud_master.db" in out_names
    snap_dir = backup_dir / _stamp(NOW)
    assert not (snap_dir / "clinic_bad.db").exists()


def test_run_once_empty_data_dir_writes_nothing(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    backup_dir = tmp_path / "backups"
    written = backup.run_once(
        data_dir, backup_dir, use_gzip=False, retention_days=14, min_keep=7, now=NOW
    )
    assert written == []


def test_run_once_missing_data_dir_raises(tmp_path):
    with pytest.raises(RuntimeError):
        backup.run_once(
            tmp_path / "nope", tmp_path / "backups",
            use_gzip=False, retention_days=14, min_keep=7, now=NOW,
        )


def test_run_once_prunes_old_snapshot_dirs(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_sqlite_db(data_dir / "cloud_master.db", "ok")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    # Seed old snapshot dirs (all ancient) plus enough to exceed min_keep.
    for n in (100, 90, 80, 70, 60, 50, 40, 30):
        (backup_dir / _days_ago(n)).mkdir()

    backup.run_once(
        data_dir, backup_dir, use_gzip=False, retention_days=14, min_keep=3, now=NOW
    )
    remaining = sorted(p.name for p in backup_dir.iterdir() if p.is_dir())
    # Pruning runs AFTER the new snapshot is written, so `existing` is the fresh
    # NOW dir + 8 seeded ancient dirs = 9. min_keep=3 protects the newest 3
    # (NOW, day-30, day-40); the other 6 are all beyond retention -> pruned.
    assert _stamp(NOW) in remaining
    assert remaining == sorted([_stamp(NOW), _days_ago(30), _days_ago(40)])


# --------------------------------------------------------------------------- #
# _env_int / _env_bool
# --------------------------------------------------------------------------- #
def test_env_int_unset_blank_garbage(monkeypatch, capsys):
    monkeypatch.delenv("MY_INT", raising=False)
    assert backup._env_int("MY_INT", 5) == 5

    monkeypatch.setenv("MY_INT", "   ")
    assert backup._env_int("MY_INT", 5) == 5

    monkeypatch.setenv("MY_INT", "abc")
    assert backup._env_int("MY_INT", 5) == 5
    assert "not an integer" in capsys.readouterr().out

    monkeypatch.setenv("MY_INT", "42")
    assert backup._env_int("MY_INT", 5) == 42


def test_env_bool_variants(monkeypatch):
    monkeypatch.delenv("MY_BOOL", raising=False)
    assert backup._env_bool("MY_BOOL", default=True) is True
    assert backup._env_bool("MY_BOOL", default=False) is False

    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv("MY_BOOL", v)
        assert backup._env_bool("MY_BOOL") is True

    for v in ("0", "no", "garbage"):
        monkeypatch.setenv("MY_BOOL", v)
        assert backup._env_bool("MY_BOOL") is False


# --------------------------------------------------------------------------- #
# Failure branches
# --------------------------------------------------------------------------- #
def test_prune_logs_and_continues_on_oserror(tmp_path, monkeypatch, capsys):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    bad_name = _days_ago(40)
    good_name = _days_ago(50)
    (backup_dir / bad_name).mkdir()
    (backup_dir / good_name).mkdir()

    real_rmtree = backup.shutil.rmtree

    def _rmtree(path, *a, **kw):
        if Path(path).name == bad_name:
            raise OSError("locked")
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(backup.shutil, "rmtree", _rmtree)

    removed = backup.prune_old_snapshots(backup_dir, NOW, retention_days=14, min_keep=0)
    assert good_name in removed
    assert bad_name not in removed
    assert (backup_dir / bad_name).is_dir()
    assert not (backup_dir / good_name).exists()
    assert "could not prune" in capsys.readouterr().out


def test_snapshot_gzip_failure_removes_intermediate(tmp_path, monkeypatch):
    src = tmp_path / "clinic_1.db"
    _make_sqlite_db(src, "x")
    dest = tmp_path / "snap" / "clinic_1.db"

    def _raise(*a, **kw):
        raise OSError("boom")

    monkeypatch.setattr(backup.gzip, "open", _raise)
    with pytest.raises(OSError):
        backup.snapshot_database(src, dest, use_gzip=True)
    assert not dest.exists()


def test_run_once_all_dbs_fail_raises_and_removes_empty_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "clinic_bad.db").write_bytes(b"not a sqlite database at all")
    backup_dir = tmp_path / "backups"

    with pytest.raises(RuntimeError):
        backup.run_once(
            data_dir, backup_dir, use_gzip=False, retention_days=14, min_keep=7, now=NOW
        )
    snap_dir = backup_dir / _stamp(NOW)
    assert not snap_dir.exists()


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #
class _StopLoop(Exception):
    """Sentinel raised from a patched time.sleep to escape the --loop while-True."""


def test_main_one_shot_success(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_sqlite_db(data_dir / "cloud_master.db", "ok")
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("CLINIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    rc = backup.main([])
    assert rc == 0
    assert any(backup_dir.iterdir())


def test_main_one_shot_failure_returns_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLINIC_DATA_DIR", str(tmp_path / "nope"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))

    rc = backup.main([])
    assert rc == 1
    assert "one-shot backup failed" in capsys.readouterr().out


def test_main_loop_mode_runs_once_and_sleeps(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_sqlite_db(data_dir / "cloud_master.db", "ok")
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("CLINIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "0")  # invalid -> WARN + fallback

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    monkeypatch.setattr(backup.time, "sleep", _fake_sleep)

    with pytest.raises(_StopLoop):
        backup.main(["--loop"])

    assert sleep_calls == [backup.DEFAULT_INTERVAL_HOURS * 3600]
    assert any(backup_dir.iterdir())


def test_main_loop_swallows_run_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINIC_DATA_DIR", str(tmp_path / "nope"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))

    def _fake_sleep(seconds):
        raise _StopLoop()

    monkeypatch.setattr(backup.time, "sleep", _fake_sleep)

    with pytest.raises(_StopLoop):
        backup.main(["--loop"])
