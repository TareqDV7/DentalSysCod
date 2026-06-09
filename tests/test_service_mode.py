"""End-to-end test that dental_clinic.py works as a 'service' — headless,
data-dir from env var, /healthz reachable. Doesn't test NSSM itself; that's
a manual smoke test in Phase C."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path



def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_healthy(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def test_service_mode_starts_headless_and_creates_db(tmp_path):
    """Spawn dental_clinic.py with CLINIC_HEADLESS=1, CLINIC_DATA_DIR=<tmp>,
    verify /healthz responds and the SQLite DB is created in the right place."""
    port = _free_port()
    env = {
        **os.environ,
        'CLINIC_HEADLESS': '1',
        'CLINIC_DATA_DIR': str(tmp_path),
        'CLINIC_HOST': '127.0.0.1',
        'CLINIC_PORT': str(port),
        'CLINIC_DEBUG': '0',
    }
    repo_root = Path(__file__).resolve().parent.parent
    # Pass all three std handles as DEVNULL so the subprocess module doesn't
    # try to inherit the (potentially invalid in some test harnesses) parent
    # handles. On Windows + Python 3.14, inheriting a sandboxed parent's
    # stdout/stderr can fail with WinError 6 inside _make_inheritable.
    devnull = open(os.devnull, 'rb')
    devnull_w = open(os.devnull, 'wb')
    try:
        proc = subprocess.Popen(
            [sys.executable, str(repo_root / 'dental_clinic.py')],
            env=env,
            cwd=str(repo_root),
            stdin=devnull,
            stdout=devnull_w,
            stderr=devnull_w,
            close_fds=False,
        )
    finally:
        devnull.close()
        devnull_w.close()
    try:
        assert _wait_healthy(port), 'service did not become healthy within 15s'
        # DB should now exist in the data dir we pointed it at.
        db_path = tmp_path / 'dental_clinic.db'
        assert db_path.exists(), f'DB not created at {db_path}'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
