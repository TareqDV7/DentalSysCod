#!/usr/bin/env python3
"""Standalone backup routine for the DentaCare cloud node's tenant databases.

Runs as its own container (the `backup` service in cloud/docker-compose.yml),
separate from the Flask `app`. It snapshots every ``*.db`` under
``CLINIC_DATA_DIR`` (the registry ``cloud_master.db`` plus each ``clinic_<id>.db``)
into a timestamped directory under ``BACKUP_DIR``, optionally gzips each
snapshot, then prunes old snapshot directories on a retention policy.

Why a dedicated script (the Flask app already has an in-process backup thread):
this process mounts the data volume **read-only** and writes to a *separate*
``dentacare-backups`` volume, so a single mistake or a droplet-volume problem on
the live data path can't take the backups down with it, and the snapshots live
on their own volume that's trivial to pull off the droplet.

Consistency: snapshots use SQLite's online backup API
(``sqlite3.connect(src).backup(dst)``), never a raw file copy — that avoids torn
writes / WAL-mode inconsistencies on a live database.

Stdlib only. No third-party dependencies (the image already ships sqlite3, gzip,
os, datetime).

Config (all via environment):
  CLINIC_DATA_DIR         source dir holding the *.db files   (default /data)
  BACKUP_DIR              where snapshot dirs are written       (default /backups)
  BACKUP_RETENTION_DAYS   prune snapshot dirs older than this   (default 14)
  BACKUP_MIN_KEEP         always keep at least this many newest (default 7)
  BACKUP_INTERVAL_HOURS   sleep between runs in --loop mode     (default 24)
  BACKUP_GZIP            "1"/"true"/"yes" to gzip each snapshot (default off)

Modes:
  (default)   one-shot: run a single backup+prune, then exit.
  --loop      run forever: backup+prune, sleep BACKUP_INTERVAL_HOURS, repeat.

Exit code is non-zero on a hard failure (e.g. the data dir is missing, or a
one-shot run couldn't snapshot a single database). Per-database errors inside a
run are logged and skipped so one bad tenant never aborts the others.
"""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Snapshot dir names look like "2026-06-03T12-30-00Z" — sortable and filesystem
# safe (no colons, which Windows/`docker cp` dislike).
TIMESTAMP_FMT = "%Y-%m-%dT%H-%M-%SZ"

DEFAULT_DATA_DIR = "/data"
DEFAULT_BACKUP_DIR = "/backups"
DEFAULT_RETENTION_DAYS = 14
DEFAULT_MIN_KEEP = 7
DEFAULT_INTERVAL_HOURS = 24


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to `default` on unset/blank/garbage."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log("WARN", f"{name}={raw!r} is not an integer; using default {default}")
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def log(level: str, message: str) -> None:
    """Structured, line-oriented logging to stdout (captured by `docker logs`)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} [{level}] backup: {message}", flush=True)


# --------------------------------------------------------------------------- #
# Retention (pure, unit-tested)
# --------------------------------------------------------------------------- #
def select_dirs_to_prune(
    existing: list[str],
    now: datetime,
    retention_days: int,
    min_keep: int,
) -> list[str]:
    """Decide which timestamped snapshot directories to delete.

    `existing` is a list of directory *names* in TIMESTAMP_FMT form
    (e.g. "2026-06-03T12-30-00Z"). Returns the subset to prune, oldest-first.

    Rules:
      * Keep at least `min_keep` of the most-recent dirs, regardless of age.
      * Beyond those, prune any dir whose timestamp is older than
        `retention_days` before `now`.
      * Names that don't parse as a timestamp are ignored (never pruned) — we
        only ever delete dirs we ourselves created and can date.

    Pure function: no filesystem access, deterministic ordering.
    """
    if min_keep < 0:
        min_keep = 0

    # Parse names -> (name, datetime); skip anything that isn't ours.
    dated: list[tuple[str, datetime]] = []
    for name in existing:
        try:
            dt = datetime.strptime(name, TIMESTAMP_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        dated.append((name, dt))

    # Newest first; tie-break on name for deterministic ordering.
    dated.sort(key=lambda item: (item[1], item[0]), reverse=True)

    # The first `min_keep` are protected no matter how old they are.
    protected = dated[:min_keep]
    candidates = dated[min_keep:]

    cutoff_seconds = retention_days * 86400
    to_prune: list[str] = []
    for name, dt in candidates:
        age_seconds = (now - dt).total_seconds()
        if age_seconds > cutoff_seconds:
            to_prune.append(name)

    # Return oldest-first so deletion logs read chronologically.
    to_prune.sort(key=lambda name: datetime.strptime(name, TIMESTAMP_FMT))
    _ = protected  # documented intent; protected dirs are simply never pruned
    return to_prune


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def snapshot_database(src: Path, dest: Path, *, use_gzip: bool) -> Path:
    """Copy `src` (a live SQLite DB) to `dest` using the online backup API.

    With `use_gzip`, the consistent snapshot is taken to a temp .db first, then
    gzipped to `dest` + ".gz" and the temp removed. Returns the final path.

    Raises on failure (caller decides whether to skip or abort).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Online backup -> a plain .db first. Open the source read-only so we never
    # mutate live data, and so a stale -wal/-shm doesn't get created next to it.
    src_uri = f"file:{src}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True)
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    if not use_gzip:
        return dest

    gz_dest = dest.with_name(dest.name + ".gz")
    try:
        with open(dest, "rb") as f_in, gzip.open(gz_dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    finally:
        # Remove the intermediate uncompressed snapshot whether or not gzip threw.
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
    return gz_dest


def discover_databases(data_dir: Path) -> list[Path]:
    """Every *.db file directly under `data_dir`, sorted for stable output.

    This naturally picks up cloud_master.db plus each clinic_<id>.db. Sidecar
    -wal / -shm files don't match "*.db" so they're ignored (the online backup
    API handles WAL state for us)."""
    return sorted(p for p in data_dir.glob("*.db") if p.is_file())


def prune_old_snapshots(
    backup_dir: Path,
    now: datetime,
    retention_days: int,
    min_keep: int,
) -> list[str]:
    """Delete snapshot dirs selected by `select_dirs_to_prune`. Returns names removed."""
    if not backup_dir.is_dir():
        return []
    existing = [p.name for p in backup_dir.iterdir() if p.is_dir()]
    to_prune = select_dirs_to_prune(existing, now, retention_days, min_keep)
    removed: list[str] = []
    for name in to_prune:
        target = backup_dir / name
        try:
            shutil.rmtree(target)
            removed.append(name)
            log("INFO", f"pruned old snapshot {name}")
        except OSError as exc:
            log("WARN", f"could not prune {name}: {exc}")
    return removed


# --------------------------------------------------------------------------- #
# One backup run
# --------------------------------------------------------------------------- #
def run_once(
    data_dir: Path,
    backup_dir: Path,
    *,
    use_gzip: bool,
    retention_days: int,
    min_keep: int,
    now: datetime | None = None,
) -> list[Path]:
    """Snapshot every DB once, prune, and return the list of files written.

    Raises RuntimeError if the data dir is missing or if databases exist but
    none could be snapshotted (a hard failure worth a non-zero exit). An empty
    data dir (no *.db yet) is *not* an error — it just writes nothing.
    """
    now = now or datetime.now(timezone.utc)
    if not data_dir.is_dir():
        raise RuntimeError(f"data dir does not exist: {data_dir}")

    databases = discover_databases(data_dir)
    if not databases:
        log("INFO", f"no *.db files under {data_dir}; nothing to back up")
        # Still prune in case retention shrank.
        prune_old_snapshots(backup_dir, now, retention_days, min_keep)
        return []

    stamp = now.strftime(TIMESTAMP_FMT)
    snapshot_root = backup_dir / stamp
    log("INFO", f"starting snapshot {stamp}: {len(databases)} database(s)")

    written: list[Path] = []
    failures = 0
    for src in databases:
        dest = snapshot_root / src.name
        try:
            out = snapshot_database(src, dest, use_gzip=use_gzip)
            written.append(out)
            log("INFO", f"snapshotted {src.name} -> {out.name}")
        except (sqlite3.Error, OSError) as exc:
            failures += 1
            log("ERROR", f"failed to snapshot {src.name}: {exc}")
            # Best-effort cleanup of a partial/empty destination.
            for stub in (dest, dest.with_name(dest.name + ".gz")):
                try:
                    stub.unlink()
                except FileNotFoundError:
                    pass

    if not written:
        # Every database failed — that's a hard failure. Drop the empty dir.
        try:
            snapshot_root.rmdir()
        except OSError:
            pass
        raise RuntimeError(
            f"snapshot {stamp} produced no files ({failures} failure(s))"
        )

    log("INFO", f"snapshot {stamp} complete: {len(written)} written, {failures} failed")
    prune_old_snapshots(backup_dir, now, retention_days, min_keep)
    return written


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    loop = "--loop" in argv

    data_dir = Path(os.environ.get("CLINIC_DATA_DIR", DEFAULT_DATA_DIR).strip() or DEFAULT_DATA_DIR)
    backup_dir = Path(os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR).strip() or DEFAULT_BACKUP_DIR)
    retention_days = _env_int("BACKUP_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
    min_keep = _env_int("BACKUP_MIN_KEEP", DEFAULT_MIN_KEEP)
    interval_hours = _env_int("BACKUP_INTERVAL_HOURS", DEFAULT_INTERVAL_HOURS)
    use_gzip = _env_bool("BACKUP_GZIP", default=False)

    log(
        "INFO",
        f"config: data_dir={data_dir} backup_dir={backup_dir} "
        f"retention_days={retention_days} min_keep={min_keep} "
        f"interval_hours={interval_hours} gzip={use_gzip} loop={loop}",
    )

    if not loop:
        try:
            run_once(
                data_dir,
                backup_dir,
                use_gzip=use_gzip,
                retention_days=retention_days,
                min_keep=min_keep,
            )
        except (RuntimeError, OSError) as exc:
            log("ERROR", f"one-shot backup failed: {exc}")
            return 1
        return 0

    # Loop mode: a single run failing must not kill the long-running service —
    # log it and try again next interval. Interval <= 0 falls back to default.
    if interval_hours <= 0:
        log("WARN", f"BACKUP_INTERVAL_HOURS={interval_hours} invalid; using {DEFAULT_INTERVAL_HOURS}")
        interval_hours = DEFAULT_INTERVAL_HOURS
    interval_seconds = interval_hours * 3600

    while True:
        try:
            run_once(
                data_dir,
                backup_dir,
                use_gzip=use_gzip,
                retention_days=retention_days,
                min_keep=min_keep,
            )
        except (RuntimeError, OSError) as exc:
            log("ERROR", f"backup run failed (will retry next interval): {exc}")
        log("INFO", f"sleeping {interval_hours}h until next run")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
