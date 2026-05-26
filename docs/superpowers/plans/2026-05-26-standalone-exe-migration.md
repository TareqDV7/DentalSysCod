# Standalone Windows .exe Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert DentaCare from a browser-served Flask app to a real Windows desktop application: NSSM-supervised background service running the existing Flask code + a pywebview window for the customer-facing UI + Inno Setup installer that wires it all up and provisions the Bluetooth COM port at install time.

**Architecture:** Three runtime components (headless Flask service, pywebview window launcher, installer) plus the existing `dental_clinic.py` codebase reused unmodified at the route/template/SQL level. Data files move from `<exe-folder>` to `C:\ProgramData\DentaCare\` when running as a packaged exe.

**Tech Stack:** Python 3.10+, Flask (existing), pywebview 5.x (Edge WebView2 engine), pystray 0.19 (tray icon), PyInstaller 6.x (existing build pipeline), NSSM 2.24 (service shim), Inno Setup 6.x (installer), Microsoft WebView2 Evergreen Bootstrapper.

**Spec:** `docs/superpowers/specs/2026-05-26-standalone-exe-migration-design.md`

---

## File Structure

**New files:**

| Path | Purpose |
|---|---|
| `dentacare_window.py` | pywebview window launcher (entry point for `DentaCare.exe`) |
| `window/__init__.py` | Empty marker |
| `window/data_dir.py` | `resolve_data_dir()` + tests target |
| `window/health_check.py` | `wait_for_service(url, timeout)` health-poll helper |
| `window/window_state.py` | Persist/load window size+position to `%LOCALAPPDATA%\DentaCare\window-state.json` |
| `window/single_instance.py` | Windows named-mutex single-instance guard |
| `window/assets/offline.html` | Offline page shown when service unreachable |
| `installer/DentaCare.iss` | Inno Setup script |
| `installer/provision_bt.ps1` | PowerShell — add Incoming SPP COM port if absent |
| `installer/nssm.exe` | NSSM 2.24 binary (bundled) |
| `installer/MicrosoftEdgeWebview2Setup.exe` | WebView2 Evergreen Bootstrapper (bundled) |
| `register-service.bat` | Manual service registration (Phase C smoke test) |
| `unregister-service.bat` | Manual service teardown |
| `tests/test_resolve_data_dir.py` | Unit tests for data-dir resolution |
| `tests/test_health_check.py` | Unit tests for health polling |
| `tests/test_window_state.py` | Unit tests for window state persistence |
| `tests/test_service_mode.py` | Subprocess integration test for service mode |

**Modified files:**

| Path | Change |
|---|---|
| `dental_clinic.py` | Extract `resolve_data_dir()` from inline code (lines 132-145); gate `open_browser()` thread on headless mode |
| `requirements.txt` | Add `pywebview==5.3`, `pystray==0.19.5`, `Pillow>=10.0` |
| `DentaCare.spec` | Two-binary build: `DentaCare.exe` (windowed) + `DentaCareService.exe` (console) |
| `rebuild.bat` | Build both binaries, copy NSSM + WebView2 bootstrapper to installer staging |
| `README.md` | Update install/run instructions (Phase D) |
| `.gitignore` | Track `installer/nssm.exe` + `installer/MicrosoftEdgeWebview2Setup.exe`? Decision: yes, commit them (vendor binaries with pinned versions reduce setup friction) |

---

# Phase A — Service-mode refactor + data-dir resolution

Goal: refactor data-dir logic into a unit-testable function. Add headless mode that skips browser auto-open. **No new behavior at this stage** — packaged exe still runs identically to today's `start.bat` flow when launched manually. Existing 170 tests stay green.

## Task A1: Extract `resolve_data_dir()` with unit tests

**Files:**
- Create: `window/__init__.py`
- Create: `window/data_dir.py`
- Create: `tests/test_resolve_data_dir.py`

- [ ] **Step 1: Create the empty `window` package marker**

Create `window/__init__.py` with content:

```python
"""Window-app helpers for the packaged DentaCare desktop exe.

This package is consumed by both `dentacare_window.py` (the windowed
launcher) and `dental_clinic.py` (the service). It must stay importable
without any GUI or pywebview deps so the service binary can use the
data-dir resolution without dragging webview code into the service."""
```

- [ ] **Step 2: Write failing test for `resolve_data_dir`**

Create `tests/test_resolve_data_dir.py`:

```python
"""Tests for window.data_dir.resolve_data_dir.

Three rules in priority order:
  1. CLINIC_DATA_DIR env var (used by Docker / cloud node)
  2. Frozen exe with no env var -> %ProgramData%\\DentaCare
  3. Running from source -> directory containing the .py file
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from window.data_dir import resolve_data_dir


def test_env_var_wins_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', str(tmp_path / 'override'))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'never_used.exe'))
    assert resolve_data_dir() == tmp_path / 'override'


def test_env_var_wins_even_with_whitespace(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', f'  {tmp_path / "override"}  ')
    assert resolve_data_dir() == tmp_path / 'override'


def test_env_var_empty_string_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINIC_DATA_DIR', '')
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    script_dir = Path(__file__).parent.parent
    assert resolve_data_dir() == script_dir


def test_frozen_no_env_uses_programdata(monkeypatch, tmp_path):
    monkeypatch.delenv('CLINIC_DATA_DIR', raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path))
    assert resolve_data_dir() == tmp_path / 'DentaCare'


def test_frozen_no_env_no_programdata_falls_back_to_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv('CLINIC_DATA_DIR', raising=False)
    monkeypatch.delenv('PROGRAMDATA', raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    # Fallback for unusual Windows installs where ProgramData isn't set.
    assert resolve_data_dir() == tmp_path / 'DentaCare'


def test_source_run_uses_script_directory(monkeypatch):
    monkeypatch.delenv('CLINIC_DATA_DIR', raising=False)
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    expected = Path(__file__).parent.parent  # the repo root
    assert resolve_data_dir() == expected
```

- [ ] **Step 3: Run the test and watch it fail**

```bash
rtk python -m pytest tests/test_resolve_data_dir.py -v
```

Expected: 6 failures with `ModuleNotFoundError: No module named 'window.data_dir'`.

- [ ] **Step 4: Implement `resolve_data_dir`**

Create `window/data_dir.py`:

```python
"""Data directory resolution.

Three rules in priority order:
  1. CLINIC_DATA_DIR env var (whitespace trimmed; empty string ignored)
  2. Frozen exe with no env var -> %ProgramData%\\DentaCare (Windows-standard
     machine-wide app-data location, writable by the service account)
  3. Running from source -> the script's own directory (today's behavior,
     preserved so dev workflow is unchanged)

The "frozen + no env + no PROGRAMDATA" branch falls back to %LOCALAPPDATA%
so the function never raises on unusual Windows installs.
"""

import os
import sys
from pathlib import Path


def resolve_data_dir() -> Path:
    """Return the directory the app should use for DB, uploads, backups, logs."""
    env_value = os.environ.get('CLINIC_DATA_DIR', '').strip()
    if env_value:
        return Path(env_value)

    if getattr(sys, 'frozen', False):
        program_data = os.environ.get('PROGRAMDATA', '').strip()
        if program_data:
            return Path(program_data) / 'DentaCare'
        local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
        if local_app_data:
            return Path(local_app_data) / 'DentaCare'
        # Last-ditch: home directory.
        return Path.home() / 'DentaCare'

    # Source / dev mode: directory containing dental_clinic.py (the repo root).
    # We resolve via the package's own __file__ since this module lives in
    # window/ — one level under the repo root.
    return Path(__file__).resolve().parent.parent
```

- [ ] **Step 5: Run the test and watch it pass**

```bash
rtk python -m pytest tests/test_resolve_data_dir.py -v
```

Expected: 6 passes.

- [ ] **Step 6: Commit**

```bash
rtk git add window/__init__.py window/data_dir.py tests/test_resolve_data_dir.py
rtk git commit -m "feat(window): extract resolve_data_dir() with unit tests

Pulls the inline data-dir logic from dental_clinic.py:132-145 into a
unit-testable function. Adds the 'frozen exe -> ProgramData\\DentaCare'
branch needed for the standalone-exe migration. Source/dev mode
behavior unchanged.

Refs: docs/superpowers/specs/2026-05-26-standalone-exe-migration-design.md
"
```

---

## Task A2: Refactor `dental_clinic.py` to use `resolve_data_dir()`

**Files:**
- Modify: `dental_clinic.py:132-145` (replace the inline data-dir block)

- [ ] **Step 1: Replace lines 132-145 in `dental_clinic.py`**

Find this block (currently lines 132-145):

```python
# Where the database / uploads / backups live.
#  - CLINIC_DATA_DIR overrides everything (used by the Docker / cloud deployment
#    to point at a mounted volume).
#  - frozen exe  -> next to the executable
#  - dev / source -> next to this script
_DATA_DIR_ENV = os.environ.get('CLINIC_DATA_DIR', '').strip()
if _DATA_DIR_ENV:
    _DATA_DIR = Path(_DATA_DIR_ENV)
elif getattr(sys, 'frozen', False):
    _DATA_DIR = Path(sys.executable).parent
else:
    _DATA_DIR = Path(__file__).parent
_BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
_DATA_DIR.mkdir(parents=True, exist_ok=True)
```

Replace with:

```python
# Where the database / uploads / backups live. See window/data_dir.py for the
# resolution rules (env var > frozen-exe ProgramData > source script dir).
from window.data_dir import resolve_data_dir
_DATA_DIR = resolve_data_dir()
_BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
_DATA_DIR.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Run the existing test suite to verify nothing broke**

```bash
rtk python -m pytest tests/ -v
```

Expected: 170 passes (existing suite) + 6 passes (new test from Task A1) = 176 passes.

- [ ] **Step 3: Commit**

```bash
rtk git add dental_clinic.py
rtk git commit -m "refactor(data-dir): use window.resolve_data_dir() instead of inline logic

Drop-in replacement; all existing call sites (DB_NAME, UPLOAD_FOLDER,
BACKUP_DIR, _clinic_db_path) continue to use _DATA_DIR unchanged.
Behavior preserved for source mode and CLINIC_DATA_DIR; frozen exe
default flips from <exe-dir> to %ProgramData%\\DentaCare per the
migration spec.
"
```

---

## Task A3: Add headless mode flag — skip browser auto-open

**Files:**
- Modify: `dental_clinic.py:12136` (the `threading.Thread(target=open_browser, ...)` line)

- [ ] **Step 1: Read context for the change**

Read `dental_clinic.py:12120-12150` to see the startup block. The browser is opened on line 12136 unconditionally. We want to skip it when running as a headless service.

- [ ] **Step 2: Replace the unconditional browser-open with a gated call**

Find:

```python
    threading.Thread(target=open_browser, kwargs={'port': port}, daemon=True).start()
```

Replace with:

```python
    # Skip browser auto-open for the headless service. The pywebview window
    # launcher (DentaCare.exe) is the customer-facing UI in packaged mode;
    # opening a browser tab too would be redundant. CLINIC_HEADLESS=1 is set
    # by NSSM in the service registration; CLOUD_MODE always implies headless.
    headless = (
        os.environ.get('CLINIC_HEADLESS', '0').strip().lower() in ('1', 'true', 'yes', 'on')
        or CLOUD_MODE
    )
    if not headless:
        threading.Thread(target=open_browser, kwargs={'port': port}, daemon=True).start()
```

- [ ] **Step 3: Run the existing suite to confirm nothing broke**

```bash
rtk python -m pytest tests/ -v
```

Expected: 176 passes (170 existing + 6 from A1).

- [ ] **Step 4: Manual smoke test of the headless gate**

```bash
rtk python -c "import os; os.environ['CLINIC_HEADLESS']='1'; os.environ['CLINIC_HOST']='127.0.0.1'; os.environ['CLINIC_PORT']='5555'; os.environ['CLINIC_DEBUG']='0'; exec(open('dental_clinic.py').read())"
```

Expected: server starts on `http://127.0.0.1:5555` but **no browser tab opens**. Ctrl-C to stop.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py
rtk git commit -m "feat(service): gate browser auto-open on CLINIC_HEADLESS

Adds the headless flag the NSSM service uses. With CLINIC_HEADLESS=1 the
Flask server starts without opening a browser tab; the customer reaches
the UI via the pywebview window app (DentaCare.exe) in packaged mode.
Cloud-mode runs already imply headless.
"
```

---

## Task A4: Subprocess integration test — service mode end-to-end

**Files:**
- Create: `tests/test_service_mode.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_service_mode.py`:

```python
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

import pytest


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
    proc = subprocess.Popen(
        [sys.executable, str(repo_root / 'dental_clinic.py')],
        env=env,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
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
```

- [ ] **Step 2: Run the test**

```bash
rtk python -m pytest tests/test_service_mode.py -v
```

Expected: 1 pass. The test boots the full Flask app in a subprocess, waits for `/healthz` to return 200, then checks the DB file landed in the right directory.

- [ ] **Step 3: Run the full suite to confirm nothing regressed**

```bash
rtk python -m pytest tests/ -v
```

Expected: 177 passes (176 from before + 1 new).

- [ ] **Step 4: Commit**

```bash
rtk git add tests/test_service_mode.py
rtk git commit -m "test(service): subprocess integration test for headless mode

Boots dental_clinic.py with CLINIC_HEADLESS=1 + CLINIC_DATA_DIR=<tmp>,
polls /healthz, asserts the SQLite DB lands in the configured data dir.
Doesn't test NSSM (manual smoke in Phase C) — only verifies the
Python-side service-mode contract.
"
```

---

## Phase A checkpoint

After Tasks A1-A4:
- `dental_clinic.py` runnable as a headless service (`CLINIC_HEADLESS=1`)
- Data dir resolution is unit-tested and predictable
- Existing 170 tests + 7 new tests all green
- No customer-visible change yet — packaged exe still behaves like today

**Verify before continuing to Phase B:**

```bash
rtk python -m pytest tests/ -v
```

Expected: 177 passes.

---

# Phase B — pywebview window app + single-instance + healthz polling

Goal: build `dentacare_window.py` and its helpers. Result: `python dentacare_window.py` opens a desktop window connected to a running service. **No packaging yet** — that's Phase C.

## Task B1: Add pywebview / pystray to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append to `requirements.txt`**

Replace the existing file (Read it first to see its current state):

```
Flask==3.0.0
Flask-CORS==4.0.0
pyserial>=3.5
waitress==3.0.0
pywebview==5.3
pystray==0.19.5
Pillow>=10.0
```

- [ ] **Step 2: Install the new deps**

```bash
rtk python -m pip install -r requirements.txt
```

Expected: pywebview, pystray, Pillow install cleanly. On Windows pywebview pulls in `pythonnet` and Edge WebView2 bindings automatically.

- [ ] **Step 3: Verify import works**

```bash
rtk python -c "import webview, pystray, PIL; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
rtk git add requirements.txt
rtk git commit -m "build: add pywebview, pystray, Pillow

Required by the standalone-exe migration's window app
(dentacare_window.py). pywebview wraps the existing Flask UI in a
windowed Edge WebView2 host; pystray drives the tray-icon menu;
Pillow loads the tray-icon image.
"
```

---

## Task B2: Health-poll helper with TDD

**Files:**
- Create: `window/health_check.py`
- Create: `tests/test_health_check.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_health_check.py`:

```python
"""Tests for window.health_check.wait_for_service.

The helper polls a healthz URL with retry-with-backoff until either it
gets a 200 response or the budget runs out. Returns True/False — never
raises."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from window.health_check import wait_for_service


def _start_server(handler_cls):
    """Spin up an HTTP server on a random port. Returns (port, stop_fn)."""
    srv = HTTPServer(('127.0.0.1', 0), handler_cls)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    def stop():
        srv.shutdown()
        srv.server_close()
    return port, stop


def test_returns_true_when_endpoint_is_healthy_immediately():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def log_message(self, *a, **kw):
            pass
    port, stop = _start_server(H)
    try:
        assert wait_for_service(f'http://127.0.0.1:{port}/healthz', timeout=2.0) is True
    finally:
        stop()


def test_returns_false_when_endpoint_never_responds():
    # Port that nothing is listening on. We pick a random high port and don't
    # bind it; the connection will be refused immediately on every attempt.
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    start = time.monotonic()
    result = wait_for_service(f'http://127.0.0.1:{port}/healthz', timeout=1.0)
    elapsed = time.monotonic() - start
    assert result is False
    assert 0.9 <= elapsed <= 1.5, f'should respect the timeout, took {elapsed}s'


def test_returns_true_when_endpoint_becomes_healthy_mid_poll():
    """First N requests return 503, subsequent ones return 200. Helper should
    keep polling and return True once 200 lands."""
    state = {'ok_after': time.monotonic() + 0.5}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if time.monotonic() < state['ok_after']:
                self.send_response(503)
            else:
                self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        def log_message(self, *a, **kw):
            pass

    port, stop = _start_server(H)
    try:
        assert wait_for_service(f'http://127.0.0.1:{port}/healthz', timeout=2.0) is True
    finally:
        stop()


def test_does_not_raise_on_invalid_url():
    assert wait_for_service('http://nonexistent-host-12345.invalid/x', timeout=0.5) is False
```

- [ ] **Step 2: Run the tests, expect failures**

```bash
rtk python -m pytest tests/test_health_check.py -v
```

Expected: 4 failures with `ModuleNotFoundError: No module named 'window.health_check'`.

- [ ] **Step 3: Implement `wait_for_service`**

Create `window/health_check.py`:

```python
"""Health polling for the DentaCare service from the window-app launcher.

The window app launches before the service is necessarily ready (especially
right after Windows boot when NSSM is still starting our process), so we
poll /healthz with a bounded retry-with-backoff loop and only open the
pywebview window once the service is reachable.
"""

import time
import urllib.error
import urllib.request


def wait_for_service(url: str, timeout: float = 10.0) -> bool:
    """Poll `url` until it returns HTTP 200 or `timeout` seconds elapse.

    Returns True if the service became healthy within the budget, False
    otherwise. Never raises — all transport errors are treated as 'not yet'.
    Uses exponential backoff capped at 1s between attempts."""
    deadline = time.monotonic() + timeout
    delay = 0.1
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError, TimeoutError):
            pass
        # Sleep, but not past the deadline.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(delay, remaining))
        delay = min(delay * 1.5, 1.0)
    return False
```

- [ ] **Step 4: Run the tests, expect passes**

```bash
rtk python -m pytest tests/test_health_check.py -v
```

Expected: 4 passes.

- [ ] **Step 5: Commit**

```bash
rtk git add window/health_check.py tests/test_health_check.py
rtk git commit -m "feat(window): wait_for_service health-poll helper

Bounded retry-with-backoff against /healthz. Used by the pywebview window
app on launch to defer opening the browser surface until the NSSM-
supervised service is reachable. Never raises; transport errors are
treated as 'not yet healthy'.
"
```

---

## Task B3: Window state persistence with TDD

**Files:**
- Create: `window/window_state.py`
- Create: `tests/test_window_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_window_state.py`:

```python
"""Tests for window.window_state.{load,save}.

Persists the window's last x/y/width/height to a JSON file. Robust to
the file missing, being malformed, or containing partial data."""

import json
from pathlib import Path

import pytest

from window.window_state import load_window_state, save_window_state, WindowState


def test_save_then_load_roundtrip(tmp_path):
    state = WindowState(x=100, y=200, width=1280, height=800)
    save_window_state(state, tmp_path / 'state.json')
    loaded = load_window_state(tmp_path / 'state.json')
    assert loaded == state


def test_load_missing_file_returns_default():
    state = load_window_state(Path('/no/such/file.json'))
    assert state.width == 1280
    assert state.height == 800
    assert state.x is None
    assert state.y is None


def test_load_malformed_json_returns_default(tmp_path):
    p = tmp_path / 'state.json'
    p.write_text('not valid json {{{')
    state = load_window_state(p)
    assert state.width == 1280


def test_load_partial_data_fills_missing_keys_with_defaults(tmp_path):
    p = tmp_path / 'state.json'
    p.write_text(json.dumps({'width': 1600}))
    state = load_window_state(p)
    assert state.width == 1600
    assert state.height == 800   # default kicks in
    assert state.x is None       # default


def test_save_creates_parent_directory(tmp_path):
    target = tmp_path / 'sub' / 'dir' / 'state.json'
    save_window_state(WindowState(x=0, y=0, width=100, height=100), target)
    assert target.exists()


def test_save_does_not_raise_on_permission_error(tmp_path, monkeypatch):
    """Saving must be best-effort — if we can't write, we don't crash the
    window app. A future launch just gets defaults."""
    def bad_open(*a, **kw):
        raise PermissionError('nope')
    monkeypatch.setattr('builtins.open', bad_open)
    # Should not raise.
    save_window_state(WindowState(x=0, y=0, width=100, height=100), tmp_path / 'x.json')
```

- [ ] **Step 2: Run tests, expect failures**

```bash
rtk python -m pytest tests/test_window_state.py -v
```

Expected: 6 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement window-state persistence**

Create `window/window_state.py`:

```python
"""Persist window size/position across launches.

Writes a small JSON file at %LOCALAPPDATA%\\DentaCare\\window-state.json
(or wherever the caller picks). All operations are best-effort: load
errors return defaults, save errors are swallowed. The window app must
keep working even on a read-only or locked profile.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800


@dataclass(frozen=True)
class WindowState:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    x: Optional[int] = None  # None = let the WM choose (centered usually)
    y: Optional[int] = None


def load_window_state(path: Path) -> WindowState:
    """Read window state from `path`. Returns a default WindowState if the
    file is missing, malformed, or unreadable. Partial data merges over
    defaults (so a file with only {"width": 1600} returns width=1600 +
    defaults for everything else)."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return WindowState()

    if not isinstance(data, dict):
        return WindowState()

    return WindowState(
        width=int(data.get('width', DEFAULT_WIDTH)),
        height=int(data.get('height', DEFAULT_HEIGHT)),
        x=data.get('x'),
        y=data.get('y'),
    )


def save_window_state(state: WindowState, path: Path) -> None:
    """Write window state to `path`. Best-effort: parent dir is created if
    missing; any I/O failure is swallowed (caller doesn't need to handle)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(state), f)
    except (OSError, PermissionError):
        pass
```

- [ ] **Step 4: Run tests, expect passes**

```bash
rtk python -m pytest tests/test_window_state.py -v
```

Expected: 6 passes.

- [ ] **Step 5: Commit**

```bash
rtk git add window/window_state.py tests/test_window_state.py
rtk git commit -m "feat(window): persist window size/position across launches

Writes a small JSON file (default location %LOCALAPPDATA%\\DentaCare\\
window-state.json). Load returns defaults on missing/malformed/partial
files; save is best-effort and silently swallows I/O errors so a
read-only profile can't crash the window app.
"
```

---

## Task B4: Single-instance mutex (Windows)

**Files:**
- Create: `window/single_instance.py`

- [ ] **Step 1: Implement the named-mutex guard**

Create `window/single_instance.py`:

```python
"""Single-instance enforcement via a Windows named mutex.

Re-launching DentaCare.exe while a window is already open should not
spawn a second window — instead, the existing one should come to front.
This module provides the 'is another instance running?' check via a
named mutex. The 'bring existing window to front' part is handled in
dentacare_window.py via FindWindow/SetForegroundWindow.

On non-Windows platforms this becomes a no-op (always returns True for
'we are the first instance') since the use case is Windows-only.
"""

import sys
from typing import Optional


MUTEX_NAME = 'DentaCare-Window-Singleton-v1'


class SingleInstanceGuard:
    """Acquires a Windows named mutex on construction. Hold the instance
    for the lifetime of the process — releasing it via __exit__ (or
    process exit) lets the next launch take over."""

    def __init__(self):
        self._handle: Optional[int] = None
        self._is_first = True
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            from ctypes import wintypes
            CreateMutexW = ctypes.windll.kernel32.CreateMutexW
            CreateMutexW.restype = wintypes.HANDLE
            CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            GetLastError = ctypes.windll.kernel32.GetLastError
            ERROR_ALREADY_EXISTS = 183
            self._handle = CreateMutexW(None, True, MUTEX_NAME)
            if GetLastError() == ERROR_ALREADY_EXISTS:
                self._is_first = False
        except Exception:
            # If anything goes wrong with the Win32 plumbing, fail open
            # (assume we are the first instance). Worst case the user gets
            # two windows; better than crashing on launch.
            self._is_first = True

    @property
    def is_first_instance(self) -> bool:
        return self._is_first

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
        except Exception:
            pass
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
```

- [ ] **Step 2: Smoke-test manually on Windows**

(Skip on non-Windows hosts; this is a Windows-only feature.)

```bash
rtk python -c "from window.single_instance import SingleInstanceGuard; g=SingleInstanceGuard(); print('first:', g.is_first_instance); input('press enter to release...'); g.release()"
```

In a **second terminal**, while the first is paused at the prompt:

```bash
rtk python -c "from window.single_instance import SingleInstanceGuard; g=SingleInstanceGuard(); print('first:', g.is_first_instance)"
```

Expected: first terminal prints `first: True`, second terminal prints `first: False`.

- [ ] **Step 3: Commit**

```bash
rtk git add window/single_instance.py
rtk git commit -m "feat(window): single-instance guard via Windows named mutex

Prevents DentaCare.exe from opening a second window when one is already
running. Fails open on non-Windows or unexpected Win32 errors. Behavior
verified manually on Windows; no pytest because the test would need a
real Win32 mutex round-trip across processes.
"
```

---

## Task B5: Offline page

**Files:**
- Create: `window/assets/offline.html`

- [ ] **Step 1: Create the offline page**

Create `window/assets/offline.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>DentaCare</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%; }
  body {
    background: linear-gradient(135deg, #1e3a8a 0%, #312e81 100%);
    color: white; font-family: 'Segoe UI', system-ui, sans-serif;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center; padding: 2rem;
  }
  .spinner {
    border: 4px solid rgba(255,255,255,0.2); border-top: 4px solid white;
    border-radius: 50%; width: 48px; height: 48px;
    animation: spin 1s linear infinite; margin-bottom: 1.5rem;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  h1 { font-size: 1.8rem; font-weight: 600; margin: 0 0 0.5rem; }
  p  { font-size: 1.1rem; opacity: 0.85; margin: 0 0 2rem; max-width: 480px; }
  button {
    background: white; color: #1e3a8a; border: none; padding: 0.75rem 1.5rem;
    font-size: 1rem; font-weight: 600; border-radius: 0.5rem; cursor: pointer;
  }
  button:hover { background: #e0e7ff; }
  .small { font-size: 0.85rem; opacity: 0.6; margin-top: 2rem; }
</style>
</head>
<body>
  <div class="spinner" id="spinner"></div>
  <h1>DentaCare is starting…</h1>
  <p id="msg">The background engine isn't ready yet. This is normal right after starting Windows.</p>
  <button onclick="window.pywebview.api.restart_service()">Restart engine</button>
  <div class="small">Polling for engine every 2 seconds. Window will reload automatically when ready.</div>
<script>
  // The window-app side calls window.location.reload() once the service
  // responds 200, but as a backup we also poll from here so the user gets
  // feedback if pywebview is alive but the JS side wants to know.
  setInterval(() => {
    fetch('http://127.0.0.1:5000/healthz').then(r => {
      if (r.ok) window.location.href = 'http://127.0.0.1:5000/';
    }).catch(() => {});
  }, 2000);
</script>
</body>
</html>
```

- [ ] **Step 2: Verify the file is valid HTML**

Open the file directly in a browser to eyeball it:

```bash
rtk python -c "import os, webbrowser; webbrowser.open('file:///' + os.path.abspath('window/assets/offline.html').replace('\\\\','/'))"
```

Expected: a centered spinner + "DentaCare is starting…" message + "Restart engine" button. Just visual confirmation.

- [ ] **Step 3: Commit**

```bash
rtk git add window/assets/offline.html
rtk git commit -m "feat(window): offline page for when the service is unreachable

Shown by the pywebview launcher when /healthz never comes back within
the boot grace period. Auto-polls /healthz every 2s and reloads the
real UI on first 200. Restart-engine button calls back via the
pywebview JS bridge (wired up in dentacare_window.py).
"
```

---

## Task B6: `dentacare_window.py` — the main entry point

**Files:**
- Create: `dentacare_window.py`

- [ ] **Step 1: Create the launcher script**

Create `dentacare_window.py`:

```python
"""DentaCare desktop window — the customer-facing launcher.

Boots the pywebview window pointed at the local Flask service. Handles:
  - single-instance enforcement (named mutex)
  - waiting for the service to be ready
  - showing an offline page if the service never responds
  - tray icon with Open / Restart engine / Open logs / Quit menu
  - window state persistence (size, position)

This file is what `DentaCare.exe` runs when the customer clicks the
Start Menu icon. The service is a separate process (DentaCareService.exe)
supervised by NSSM."""

import os
import subprocess
import sys
import threading
from pathlib import Path

import webview

from window.data_dir import resolve_data_dir
from window.health_check import wait_for_service
from window.single_instance import SingleInstanceGuard
from window.window_state import WindowState, load_window_state, save_window_state


SERVICE_URL = 'http://127.0.0.1:5000'
HEALTHZ_URL = f'{SERVICE_URL}/healthz'
BOOT_GRACE_SECONDS = 10.0
ASSETS_DIR = Path(__file__).resolve().parent / 'window' / 'assets'
WINDOW_STATE_PATH = (
    Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    / 'DentaCare'
    / 'window-state.json'
)


class WindowApi:
    """Exposed to the offline.html page via pywebview's JS bridge."""

    def restart_service(self):
        """Try to start the service; surface errors via the window itself."""
        try:
            subprocess.run(
                ['sc', 'start', 'DentaCare'],
                capture_output=True, check=False, timeout=10,
            )
        except Exception:
            pass


def _bring_existing_window_to_front():
    """Best-effort: find the existing DentaCare window and bring it forward.
    Called when SingleInstanceGuard reports we're not the first instance."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        from ctypes import wintypes
        FindWindowW = ctypes.windll.user32.FindWindowW
        FindWindowW.restype = wintypes.HWND
        SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
        ShowWindow = ctypes.windll.user32.ShowWindow
        SW_RESTORE = 9
        hwnd = FindWindowW(None, 'DentaCare')
        if hwnd:
            ShowWindow(hwnd, SW_RESTORE)
            SetForegroundWindow(hwnd)
    except Exception:
        pass


def _resolve_initial_url() -> str:
    """If the service is healthy, point at the real UI. Otherwise show the
    offline page (and the in-page JS will redirect to the real UI when
    /healthz comes back)."""
    if wait_for_service(HEALTHZ_URL, timeout=BOOT_GRACE_SECONDS):
        return SERVICE_URL
    offline_path = ASSETS_DIR / 'offline.html'
    return offline_path.as_uri()


def main():
    guard = SingleInstanceGuard()
    if not guard.is_first_instance:
        _bring_existing_window_to_front()
        return 0

    state = load_window_state(WINDOW_STATE_PATH)
    api = WindowApi()
    initial_url = _resolve_initial_url()

    window = webview.create_window(
        title='DentaCare',
        url=initial_url,
        width=state.width,
        height=state.height,
        x=state.x,
        y=state.y,
        resizable=True,
        min_size=(900, 600),
        js_api=api,
    )

    def on_closing():
        # Save window size/position on close. pywebview gives us the latest
        # values via window.x/y/width/height at the moment the user clicks X.
        try:
            save_window_state(
                WindowState(
                    width=int(window.width or state.width),
                    height=int(window.height or state.height),
                    x=int(window.x) if window.x is not None else None,
                    y=int(window.y) if window.y is not None else None,
                ),
                WINDOW_STATE_PATH,
            )
        except Exception:
            pass

    window.events.closing += on_closing
    webview.start()
    guard.release()
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: Manual smoke test**

In **terminal 1**, start the service:

```bash
rtk python dental_clinic.py
```

Wait for it to print "System ready!". In **terminal 2**:

```bash
rtk python dentacare_window.py
```

Expected: a desktop window opens with the DentaCare sign-in page rendered inside (no browser, no URL bar). Window can be resized; closing the window terminates the launcher (service keeps running).

- [ ] **Step 3: Manual smoke test of the offline path**

Stop the service (Ctrl-C in terminal 1) before launching the window:

```bash
rtk python dentacare_window.py
```

Expected: window opens to the offline page with the spinner. Restart the service in terminal 1; within ~2s the window auto-loads the real UI.

- [ ] **Step 4: Manual smoke test of single-instance**

Start the service. Open the window. While the window is open, in a second terminal:

```bash
rtk python dentacare_window.py
```

Expected: the second invocation exits immediately; the first window is brought to the front. Only one window is visible.

- [ ] **Step 5: Commit**

```bash
rtk git add dentacare_window.py
rtk git commit -m "feat(window): pywebview launcher (dentacare_window.py)

Opens a desktop window pointed at the local Flask service. Waits up to
10s for /healthz on launch; shows an offline page (window/assets/
offline.html) if the service isn't reachable, auto-reloading once it
is. Persists window size/position across launches. Single-instance
enforced via the named-mutex guard.

Manual smoke tests pass: window opens with UI, offline path works,
double-launch brings existing window to front.
"
```

---

## Task B7: Tray icon + close-to-hide

**Files:**
- Modify: `dentacare_window.py`
- Create: `window/assets/icon.png` (16x16 or 32x32 PNG, can use DentaCare.PNG resized)

- [ ] **Step 1: Generate the tray icon from DentaCare.PNG**

```bash
rtk python -c "from PIL import Image; img = Image.open('DentaCare.PNG'); img.thumbnail((32, 32)); img.save('window/assets/icon.png')"
```

Expected: `window/assets/icon.png` exists, 32x32 or smaller.

- [ ] **Step 2: Add tray icon + close-to-hide to `dentacare_window.py`**

Replace the contents of `dentacare_window.py` with the version below (this incorporates the tray icon and close-to-hide behavior):

```python
"""DentaCare desktop window — the customer-facing launcher.

(See Task B6 docstring for the high-level shape.) This revision adds:
  - tray icon with Open / Restart engine / Open logs / Quit menu
  - close-to-hide (X button hides; Quit from tray actually exits)
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

import webview
from PIL import Image
import pystray

from window.data_dir import resolve_data_dir
from window.health_check import wait_for_service
from window.single_instance import SingleInstanceGuard
from window.window_state import WindowState, load_window_state, save_window_state


SERVICE_URL = 'http://127.0.0.1:5000'
HEALTHZ_URL = f'{SERVICE_URL}/healthz'
BOOT_GRACE_SECONDS = 10.0
ASSETS_DIR = Path(__file__).resolve().parent / 'window' / 'assets'
WINDOW_STATE_PATH = (
    Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    / 'DentaCare'
    / 'window-state.json'
)


class WindowApi:
    def restart_service(self):
        try:
            subprocess.run(['sc', 'start', 'DentaCare'],
                           capture_output=True, check=False, timeout=10)
        except Exception:
            pass


def _resolve_initial_url() -> str:
    if wait_for_service(HEALTHZ_URL, timeout=BOOT_GRACE_SECONDS):
        return SERVICE_URL
    return (ASSETS_DIR / 'offline.html').as_uri()


def _open_log_folder():
    logs = resolve_data_dir() / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(logs))
    except (AttributeError, OSError):
        pass


class App:
    """Holds the pywebview window + tray icon and the wiring between them."""

    def __init__(self):
        self.window = None
        self.tray_icon = None
        self._quit_requested = False
        self._state = load_window_state(WINDOW_STATE_PATH)

    def _save_state(self):
        try:
            save_window_state(
                WindowState(
                    width=int(self.window.width or self._state.width),
                    height=int(self.window.height or self._state.height),
                    x=int(self.window.x) if self.window.x is not None else None,
                    y=int(self.window.y) if self.window.y is not None else None,
                ),
                WINDOW_STATE_PATH,
            )
        except Exception:
            pass

    def _on_window_closing(self):
        """Intercept the X button: hide instead of close, unless Quit was chosen."""
        self._save_state()
        if not self._quit_requested:
            self.window.hide()
            return False  # cancel the close
        return True

    def _tray_open(self, icon, item):
        self.window.show()

    def _tray_restart(self, icon, item):
        WindowApi().restart_service()

    def _tray_open_logs(self, icon, item):
        _open_log_folder()

    def _tray_quit(self, icon, item):
        self._quit_requested = True
        icon.stop()
        try:
            self.window.destroy()
        except Exception:
            pass

    def _build_tray_menu(self):
        return pystray.Menu(
            pystray.MenuItem('Open', self._tray_open, default=True),
            pystray.MenuItem('Restart engine', self._tray_restart),
            pystray.MenuItem('Open log folder', self._tray_open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit completely', self._tray_quit),
        )

    def _run_tray(self):
        image = Image.open(ASSETS_DIR / 'icon.png')
        self.tray_icon = pystray.Icon('DentaCare', image, 'DentaCare', self._build_tray_menu())
        self.tray_icon.run()

    def run(self):
        self.window = webview.create_window(
            title='DentaCare',
            url=_resolve_initial_url(),
            width=self._state.width,
            height=self._state.height,
            x=self._state.x,
            y=self._state.y,
            resizable=True,
            min_size=(900, 600),
            js_api=WindowApi(),
        )
        self.window.events.closing += self._on_window_closing

        # Tray must run on a background thread so it doesn't block pywebview.
        threading.Thread(target=self._run_tray, daemon=True).start()

        webview.start()


def _bring_existing_window_to_front():
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        from ctypes import wintypes
        FindWindowW = ctypes.windll.user32.FindWindowW
        FindWindowW.restype = wintypes.HWND
        SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
        ShowWindow = ctypes.windll.user32.ShowWindow
        SW_RESTORE = 9
        hwnd = FindWindowW(None, 'DentaCare')
        if hwnd:
            ShowWindow(hwnd, SW_RESTORE)
            SetForegroundWindow(hwnd)
    except Exception:
        pass


def main():
    guard = SingleInstanceGuard()
    if not guard.is_first_instance:
        _bring_existing_window_to_front()
        return 0
    try:
        App().run()
    finally:
        guard.release()
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 3: Manual smoke test of close-to-hide**

Start the service. Run `rtk python dentacare_window.py`. Expected:
- Window opens, DentaCare tray icon appears in the notification area.
- Click X → window hides, tray icon remains.
- Right-click tray icon → see *Open*, *Restart engine*, *Open log folder*, *Quit completely*.
- Click *Open* → window re-appears.
- Click *Quit completely* → tray icon disappears, window destroyed, process exits.

- [ ] **Step 4: Commit**

```bash
rtk git add dentacare_window.py window/assets/icon.png
rtk git commit -m "feat(window): tray icon + close-to-hide

X button hides the window (tray icon stays). Right-click tray gives
Open / Restart engine / Open log folder / Quit completely. Quitting
from the tray exits the launcher; the background service keeps
running so mobile sync stays alive.
"
```

---

## Phase B checkpoint

After Tasks B1-B7:
- `python dentacare_window.py` opens a real desktop window over the running service
- Service down → offline page → auto-recovers when service returns
- X button hides, tray icon stays, Quit exits cleanly
- Single-instance enforced
- Window size/position persists

**Verify before continuing to Phase C:**

```bash
rtk python -m pytest tests/ -v
```

Expected: 187 passes (177 from Phase A + 10 new from B2 + B3).

Plus the manual smoke tests in B6 and B7 must have passed.

---

# Phase C — Two-binary PyInstaller spec + NSSM service registration

Goal: build `DentaCare.exe` (windowed launcher) and `DentaCareService.exe` (headless Flask) from a single PyInstaller spec; register the service via NSSM with a batch script. End state: a developer can manually install + run DentaCare on a clean Windows machine without the Inno Setup wrapper.

## Task C1: Vendor NSSM into the repo

**Files:**
- Create: `installer/nssm.exe` (NSSM 2.24, 64-bit)

- [ ] **Step 1: Download NSSM 2.24**

Visit `https://nssm.cc/release/nssm-2.24.zip`, download, extract. From the zip, copy `nssm-2.24/win64/nssm.exe` to `installer/nssm.exe`.

Pinned version: NSSM 2.24, MIT licensed. SHA256 of the 64-bit binary: see `nssm.cc` for the official hash.

- [ ] **Step 2: Verify the binary works**

```bash
rtk ./installer/nssm.exe version
```

Expected: prints `NSSM, the Non-Sucking Service Manager` and version info.

- [ ] **Step 3: Commit**

```bash
rtk git add installer/nssm.exe
rtk git commit -m "build: vendor NSSM 2.24 (win64) for service registration

Pinned binary used by both the manual register-service.bat and the
Inno Setup installer. NSSM is MIT-licensed; the unmodified upstream
release from https://nssm.cc/release/nssm-2.24.zip.
"
```

---

## Task C2: Update `DentaCare.spec` to build two binaries

**Files:**
- Modify: `DentaCare.spec` (replace with two-Analysis spec)

- [ ] **Step 1: Read the existing spec**

```bash
rtk read DentaCare.spec
```

You'll see a single-Analysis spec producing one `.exe`. We need two: one console (the service) and one windowed (the launcher).

- [ ] **Step 2: Replace `DentaCare.spec` with a two-binary spec**

Write `DentaCare.spec` with the following content (preserve `hiddenimports` and `datas` patterns from the existing spec where relevant — Read the file first to see the current set, then copy them into the service Analysis below):

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DentaCare.

Builds two binaries:
  - DentaCareService.exe  : headless Flask app (run by NSSM)
  - DentaCare.exe         : pywebview window launcher (user-facing)

Both share the same Python codebase but have different entry points
and different console/window flags."""

block_cipher = None

# Hidden imports — keep in sync with the previous single-binary spec.
COMMON_HIDDEN = [
    'waitress',
    'markupsafe',
    'werkzeug.security',
    'serial',
    'serial.tools.list_ports',
]

# Data files bundled into both exes.
COMMON_DATAS = [
    ('DentaCare.PNG', '.'),
]

WINDOW_DATAS = COMMON_DATAS + [
    ('window/assets/offline.html', 'window/assets'),
    ('window/assets/icon.png', 'window/assets'),
]

# --- The headless service ----------------------------------------------------
service_a = Analysis(
    ['dental_clinic.py'],
    pathex=[],
    binaries=[],
    datas=COMMON_DATAS,
    hiddenimports=COMMON_HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
service_pyz = PYZ(service_a.pure, service_a.zipped_data, cipher=block_cipher)
service_exe = EXE(
    service_pyz,
    service_a.scripts,
    service_a.binaries,
    service_a.zipfiles,
    service_a.datas,
    [],
    name='DentaCareService',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,       # service: keep console so NSSM can capture stdout/stderr
    icon='DentaCare.PNG',
)

# --- The windowed launcher ---------------------------------------------------
window_a = Analysis(
    ['dentacare_window.py'],
    pathex=[],
    binaries=[],
    datas=WINDOW_DATAS,
    hiddenimports=COMMON_HIDDEN + ['pystray._win32', 'PIL._tkinter_finder'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
window_pyz = PYZ(window_a.pure, window_a.zipped_data, cipher=block_cipher)
window_exe = EXE(
    window_pyz,
    window_a.scripts,
    window_a.binaries,
    window_a.zipfiles,
    window_a.datas,
    [],
    name='DentaCare',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,      # launcher: windowed, no console flash on start
    icon='DentaCare.PNG',
)
```

- [ ] **Step 3: Verify the spec syntax by running PyInstaller against it**

```bash
rtk pyinstaller DentaCare.spec --noconfirm --clean
```

Expected: build runs to completion, producing `dist/DentaCareService.exe` AND `dist/DentaCare.exe`. Takes a few minutes.

- [ ] **Step 4: Verify both binaries launch**

In one terminal:

```bash
rtk ./dist/DentaCareService.exe
```

Expected: Flask starts on `http://0.0.0.0:5000` (or the configured host). Console shows the usual startup messages. Ctrl-C to stop.

Then with the service running again (separate terminal):

```bash
rtk ./dist/DentaCare.exe
```

Expected: window opens with the DentaCare UI. No console flash on start (because of `console=False`).

- [ ] **Step 5: Commit**

```bash
rtk git add DentaCare.spec
rtk git commit -m "build: two-binary PyInstaller spec (service + window)

DentaCareService.exe runs the headless Flask app; DentaCare.exe runs
the pywebview launcher. Single spec, single 'pyinstaller' invocation
produces both. Manual launch of both verified end-to-end on dev
machine.
"
```

---

## Task C3: Update `rebuild.bat` to handle both binaries + bundling

**Files:**
- Modify: `rebuild.bat`

- [ ] **Step 1: Read the current `rebuild.bat`**

```bash
rtk read rebuild.bat
```

You'll see a script that wipes build/dist, runs PyInstaller, copies the result to `deployment/`. Update it to copy both binaries and bundle NSSM + the WebView2 bootstrapper into a staging folder.

- [ ] **Step 2: Replace `rebuild.bat`**

Write `rebuild.bat`:

```batch
@echo off
REM Rebuild DentaCare from scratch.
REM Produces dist/DentaCareService.exe, dist/DentaCare.exe, and a
REM ready-to-package staging folder at dist/staging/.

setlocal

echo === Cleaning previous build ===
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

echo === Installing PyInstaller ===
python -m pip install --upgrade pyinstaller >nul

echo === Verifying source compiles ===
python -m py_compile dental_clinic.py dentacare_window.py
if errorlevel 1 (
    echo ERROR: source failed py_compile
    exit /b 1
)

echo === Building both binaries ===
pyinstaller DentaCare.spec --noconfirm --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)

echo === Staging installer payload ===
mkdir dist\staging
copy /y dist\DentaCare.exe          dist\staging\
copy /y dist\DentaCareService.exe   dist\staging\
copy /y DentaCare.PNG               dist\staging\
copy /y installer\nssm.exe          dist\staging\
copy /y installer\provision_bt.ps1  dist\staging\  2>nul
if exist installer\MicrosoftEdgeWebview2Setup.exe (
    copy /y installer\MicrosoftEdgeWebview2Setup.exe dist\staging\
)

echo === Copying to deployment ===
if not exist deployment mkdir deployment
copy /y dist\DentaCare.exe          deployment\
copy /y dist\DentaCareService.exe   deployment\

echo.
echo Build complete:
echo   dist\DentaCare.exe          (window launcher)
echo   dist\DentaCareService.exe   (headless service)
echo   dist\staging\               (installer payload)
echo.
endlocal
```

- [ ] **Step 3: Run the rebuild**

```bash
rtk rebuild.bat
```

Expected: clean build, both exes produced, `dist/staging/` populated with the launcher, the service, the icon, NSSM, and (if present) the WebView2 bootstrapper.

- [ ] **Step 4: Commit**

```bash
rtk git add rebuild.bat
rtk git commit -m "build(rebuild): two-binary build + installer staging

Produces both DentaCare.exe and DentaCareService.exe; stages the
installer payload (binaries + NSSM + icon + provision_bt.ps1 +
WebView2 bootstrapper if present) under dist/staging/ ready for Inno
Setup to package in Phase D.
"
```

---

## Task C4: Manual service registration scripts

**Files:**
- Create: `register-service.bat`
- Create: `unregister-service.bat`

- [ ] **Step 1: Create `register-service.bat`**

```batch
@echo off
REM Register DentaCare as a Windows service via NSSM. Must be run as admin.
REM Assumes the staging folder from rebuild.bat lives at dist\staging\.
REM Used in Phase C smoke tests before the Inno Setup installer exists.

setlocal

set SERVICE_NAME=DentaCare
set STAGING_DIR=%~dp0dist\staging
set DATA_DIR=%PROGRAMDATA%\DentaCare

if not exist "%STAGING_DIR%\DentaCareService.exe" (
    echo ERROR: %STAGING_DIR%\DentaCareService.exe not found.
    echo Run rebuild.bat first.
    exit /b 1
)

REM Check for admin privileges via a write to System32.
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: must run from an elevated command prompt.
    exit /b 1
)

echo === Creating data dir at %DATA_DIR% ===
if not exist "%DATA_DIR%"         mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\uploads" mkdir "%DATA_DIR%\uploads"
if not exist "%DATA_DIR%\backups" mkdir "%DATA_DIR%\backups"
if not exist "%DATA_DIR%\logs"    mkdir "%DATA_DIR%\logs"

REM Grant SYSTEM full control (it's already there by default for ProgramData,
REM but be explicit so the install is predictable).
icacls "%DATA_DIR%" /grant *S-1-5-18:(OI)(CI)F /T >nul

echo === Stopping any existing service ===
"%STAGING_DIR%\nssm.exe" stop %SERVICE_NAME% >nul 2>&1
"%STAGING_DIR%\nssm.exe" remove %SERVICE_NAME% confirm >nul 2>&1

echo === Registering service ===
"%STAGING_DIR%\nssm.exe" install %SERVICE_NAME% "%STAGING_DIR%\DentaCareService.exe"
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% AppDirectory   "%DATA_DIR%"
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% AppStdout      "%DATA_DIR%\logs\service.stdout.log"
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% AppStderr      "%DATA_DIR%\logs\service.stderr.log"
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% AppRotateFiles 1
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% AppRotateBytes 10485760
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% AppEnvironmentExtra "CLINIC_HEADLESS=1" "CLINIC_HOST=0.0.0.0" "CLINIC_PORT=5000" "CLINIC_DATA_DIR=%DATA_DIR%"
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%STAGING_DIR%\nssm.exe" set %SERVICE_NAME% ObjectName LocalSystem

echo === Starting service ===
"%STAGING_DIR%\nssm.exe" start %SERVICE_NAME%

echo.
echo Done. Verify at: http://127.0.0.1:5000/healthz
echo Logs:           %DATA_DIR%\logs\
endlocal
```

- [ ] **Step 2: Create `unregister-service.bat`**

```batch
@echo off
REM Stop and remove the DentaCare service. Leaves %PROGRAMDATA%\DentaCare
REM untouched (the customer's clinic data).

setlocal

set SERVICE_NAME=DentaCare
set STAGING_DIR=%~dp0dist\staging

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: must run from an elevated command prompt.
    exit /b 1
)

"%STAGING_DIR%\nssm.exe" stop %SERVICE_NAME%
"%STAGING_DIR%\nssm.exe" remove %SERVICE_NAME% confirm

echo Done. %PROGRAMDATA%\DentaCare left in place.
endlocal
```

- [ ] **Step 3: Manual smoke test (Windows, elevated cmd)**

From an **admin command prompt**:

```cmd
cd C:\Users\MSI\Desktop\clinic
rebuild.bat
register-service.bat
```

Expected output: service registers, starts. Then visit `http://127.0.0.1:5000/healthz` in any browser — should return JSON `{"status":"ok", ...}`. Check `services.msc` — DentaCare is listed, status "Running".

Then verify the launcher works against the running service:

```cmd
dist\DentaCare.exe
```

Expected: window opens to DentaCare sign-in page (admin/admin). Same look-and-feel as the dev browser.

Clean up:

```cmd
unregister-service.bat
```

Expected: service stops + removes. `services.msc` no longer shows DentaCare.

- [ ] **Step 4: Commit**

```bash
rtk git add register-service.bat unregister-service.bat
rtk git commit -m "tools: manual NSSM service registration scripts

register-service.bat / unregister-service.bat — admin-only batch
scripts that mirror what the Inno Setup installer will do in Phase D.
Used to smoke-test the service shape end-to-end without the installer
in the loop yet.
"
```

---

## Phase C checkpoint

After Tasks C1-C4:
- `rebuild.bat` produces both `.exe`s + a staging folder
- `register-service.bat` registers DentaCare with NSSM, starts it, and the launcher window connects
- All 187 tests still pass

**Verify before continuing to Phase D:**

```bash
rtk python -m pytest tests/ -v
```

Expected: 187 passes.

Plus: clean install via `register-service.bat` works on a Windows VM (or your machine), and `unregister-service.bat` cleans it up.

---

# Phase D — Inno Setup installer + BT provisioning

Goal: customer-shippable `DentaCare-Setup.exe`. Welcome → License → Components → Install → Done. Provisions COM port, registers service, lays out file structure, adds shortcuts, migrates legacy DB.

## Task D1: Bundle WebView2 Evergreen Bootstrapper

**Files:**
- Create: `installer/MicrosoftEdgeWebview2Setup.exe`

- [ ] **Step 1: Download the bootstrapper**

Visit `https://go.microsoft.com/fwlink/p/?LinkId=2124703` (Microsoft's official Evergreen Bootstrapper). Save the resulting `MicrosoftEdgeWebview2Setup.exe` (~1-3 MB) into `installer/`.

- [ ] **Step 2: Verify it's executable**

```bash
rtk ./installer/MicrosoftEdgeWebview2Setup.exe /?
```

Expected: shows the bootstrapper's command-line help (or runs silently for a few seconds, then exits). Don't run it without `/?` here — that would install WebView2 on your dev machine, which probably already has it.

- [ ] **Step 3: Commit**

```bash
rtk git add installer/MicrosoftEdgeWebview2Setup.exe
rtk git commit -m "build: vendor Microsoft WebView2 Evergreen Bootstrapper

Inno Setup runs this at install time if WebView2 isn't present.
Unmodified upstream binary from
https://go.microsoft.com/fwlink/p/?LinkId=2124703 — Microsoft permits
redistribution per their Distribution Terms.
"
```

---

## Task D2: PowerShell — `provision_bt.ps1`

**Files:**
- Create: `installer/provision_bt.ps1`

- [ ] **Step 1: Write the provisioning script**

Create `installer/provision_bt.ps1`:

```powershell
# Provision an Incoming SPP (Serial Port Profile) COM port on Windows so the
# Bluetooth-SPP sync path works without the customer touching Windows BT
# settings. Idempotent: if any Incoming SPP port already exists, exits 0
# without changes.
#
# Run by the Inno Setup installer with elevated privileges. Exit code 0 on
# success, non-zero on failure (logged to the installer log).

$ErrorActionPreference = 'Stop'

function Write-Log($msg) {
    $line = "[$([DateTime]::UtcNow.ToString('o'))] $msg"
    Write-Host $line
}

try {
    # Detect existing Incoming SPP COM ports. The bthport registry holds
    # device-bound bindings; the Windows-managed "Incoming" generic SPP port
    # is registered under a fixed registry path that lists Bluetooth COM ports.
    $regPath = 'HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM'
    $ports = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    $btIncomingExists = $false
    if ($ports) {
        foreach ($name in $ports.PSObject.Properties.Name) {
            $val = $ports.$name
            # An incoming-SPP COM is named like \Device\BthModem<N> in SERIALCOMM,
            # whereas outgoing ports are bound to a specific BT device path.
            if ($name -like '*BthModem*' -or $val -like 'COM*') {
                # We can't tell direction from SERIALCOMM alone; cross-check
                # against the bluetooth bound-device registry.
                # Simpler heuristic: any COM in SERIALCOMM with the BthModem
                # device path is an incoming-side endpoint.
                if ($name -like '*BthModem*') {
                    $btIncomingExists = $true
                    Write-Log "Found existing Incoming SPP entry: $name -> $val"
                }
            }
        }
    }

    if ($btIncomingExists) {
        Write-Log 'Incoming SPP COM port already provisioned. Nothing to do.'
        exit 0
    }

    # No incoming SPP port found. Create one via the documented Windows BT
    # registry path. This mirrors what the Control Panel "Add Incoming Port"
    # dialog does internally.
    #
    # Windows allocates incoming SPP ports via the BTHPORT service's PnP
    # enumerator. The reliable way to trigger it from script is to create a
    # registry entry under SerialAttachedSetupNotify and let the BT stack
    # pick it up on next service restart. For maximum reliability we instead
    # use the documented WMI/PnP route via pnputil to install the BT modem
    # device class if not present.
    #
    # In practice, on Windows 10+ the simplest reliable method is to invoke
    # the legacy Bluetooth control panel's incoming-port add via rundll32:
    Write-Log 'No Incoming SPP found. Opening Bluetooth COM Ports dialog so'
    Write-Log 'the installer can guide the user through Add -> Incoming.'

    # We cannot fully create the port programmatically without third-party
    # drivers; the most portable approach is to open the dialog for the user
    # to confirm. Inno Setup follows up with a message box explaining.
    # rundll32.exe bthprops.cpl shows the BT props page on Windows 10/11.
    Start-Process -FilePath 'rundll32.exe' -ArgumentList 'bthprops.cpl' -WindowStyle Normal
    exit 2  # 2 = user-action-required; installer surfaces a message
}
catch {
    Write-Log "FATAL: $($_.Exception.Message)"
    exit 1
}
```

> **Implementation note for the engineer:** the *reliable* programmatic creation of a Windows Incoming SPP COM port without third-party drivers is genuinely difficult — the surface that worked on Windows 7 (`DEVPROP_Bluetooth_Service`) is no longer documented for Windows 10/11. The script above is conservative: it detects an existing incoming port (idempotent), and if none exists it opens the Bluetooth COM Ports dialog so the user can click Add → Incoming with one click. The installer will explain this in a follow-up dialog. **If during smoke testing you discover a reliable scripted creation path** (a vendor BT stack tool, or a WMI method that works) **update the script and remove the user-prompt fallback.** Worst case: the customer does one click during install instead of finding the dialog themselves later, still a massive improvement over today.

- [ ] **Step 2: Smoke test on the dev machine**

(Your machine already has an Incoming SPP port from the debug session.)

```bash
rtk powershell -ExecutionPolicy Bypass -File installer/provision_bt.ps1
```

Expected output:

```
[<timestamp>] Found existing Incoming SPP entry: \Device\BthModem0 -> COM5
[<timestamp>] Incoming SPP COM port already provisioned. Nothing to do.
```

Exit code: 0.

- [ ] **Step 3: Commit**

```bash
rtk git add installer/provision_bt.ps1
rtk git commit -m "installer: PowerShell COM-port provisioning script

Idempotent: detects existing Incoming SPP COM port and no-ops if
present. If absent, opens the Windows Bluetooth COM Ports dialog so
the customer can click Add -> Incoming with one click (purely
programmatic creation isn't supported on Windows 10/11 without
third-party drivers). Smoke-tested on operator's dev machine which
has an existing Incoming SPP port — exits 0, no changes.
"
```

---

## Task D3: Base Inno Setup script

**Files:**
- Create: `installer/DentaCare.iss`

- [ ] **Step 1: Write the base installer script**

Create `installer/DentaCare.iss`:

```pascal
; DentaCare Inno Setup installer.
;
; Build with: ISCC.exe installer\DentaCare.iss
; Produces:   installer\Output\DentaCare-Setup.exe
;
; Requires:   dist\staging\ populated by rebuild.bat first.

#define MyAppName        "DentaCare"
#define MyAppVersion     "1.1.0"
#define MyAppPublisher   "DentaCare"
#define MyAppExeName     "DentaCare.exe"
#define MyServiceExeName "DentaCareService.exe"
#define StagingDir       "..\dist\staging"

[Setup]
AppId={{B8F4D1A2-7B62-4E3D-9F8C-DentaCare00001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=DentaCare-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=..\DentaCare.PNG
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create a desktop shortcut";       GroupDescription: "Shortcuts:";  Flags: unchecked
Name: "autostart";    Description: "Launch DentaCare window at logon"; GroupDescription: "Startup:";    Flags:

[Files]
Source: "{#StagingDir}\{#MyAppExeName}";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\{#MyServiceExeName}";    DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\nssm.exe";               DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\DentaCare.PNG";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\installer\provision_bt.ps1";        DestDir: "{app}\installer"; Flags: ignoreversion
Source: "..\installer\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall ignoreversion

[Dirs]
Name: "{commonappdata}\DentaCare";          Permissions: system-full
Name: "{commonappdata}\DentaCare\uploads";  Permissions: system-full
Name: "{commonappdata}\DentaCare\backups";  Permissions: system-full
Name: "{commonappdata}\DentaCare\logs";     Permissions: system-full

[Icons]
Name: "{group}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "DentaCare"; ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 1. Install WebView2 if missing (the bootstrapper no-ops if already present).
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; \
    Parameters: "/silent /install"; \
    StatusMsg: "Installing Microsoft Edge WebView2 runtime..."; \
    Check: NeedsWebView2

; 2. Provision the Bluetooth Incoming SPP COM port.
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\provision_bt.ps1"""; \
    StatusMsg: "Configuring Bluetooth sync..."; \
    Flags: runhidden

; 3. Register and start the NSSM service.
Filename: "{app}\nssm.exe"; Parameters: "install DentaCare ""{app}\{#MyServiceExeName}"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppDirectory ""{commonappdata}\DentaCare"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppStdout ""{commonappdata}\DentaCare\logs\service.stdout.log"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppStderr ""{commonappdata}\DentaCare\logs\service.stderr.log"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppRotateFiles 1"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppRotateBytes 10485760"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppEnvironmentExtra CLINIC_HEADLESS=1 CLINIC_HOST=0.0.0.0 CLINIC_PORT=5000 CLINIC_DATA_DIR={commonappdata}\DentaCare"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare Start SERVICE_AUTO_START"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare ObjectName LocalSystem"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "start DentaCare"; Flags: runhidden

; 4. Launch the window on install completion.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch DentaCare"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\nssm.exe"; Parameters: "stop DentaCare";           Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "remove DentaCare confirm"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function NeedsWebView2: Boolean;
var
  Version: string;
begin
  // WebView2 runtime registers under HKLM if present. Two possible paths
  // depending on machine-wide or per-user install.
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
    or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
  );
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then begin
    Response := MsgBox(
      'Remove DentaCare clinic data?' + #13#10 + #13#10 +
      'This will permanently delete all patient records, appointments, and backups in:' + #13#10 +
      ExpandConstant('{commonappdata}\DentaCare') + #13#10 + #13#10 +
      'Click NO to keep the data (recommended).',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
    if Response = IDYES then begin
      DelTree(ExpandConstant('{commonappdata}\DentaCare'), True, True, True);
    end;
  end;
end;
```

- [ ] **Step 2: Install Inno Setup**

If you don't have it: download from `https://jrsoftware.org/isdl.php`, install Inno Setup 6.x.

- [ ] **Step 3: Compile the installer**

```bash
rtk "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DentaCare.iss
```

Expected: compilation succeeds, `installer\Output\DentaCare-Setup.exe` produced.

- [ ] **Step 4: Smoke test on a clean Windows VM (or with caution on your dev machine)**

**Recommended path:** use a Windows 11 VM snapshot for this. If testing on your dev machine, first run `unregister-service.bat` (Phase C) and back up `%PROGRAMDATA%\DentaCare\` if it exists.

Double-click `installer\Output\DentaCare-Setup.exe`. Walk through:
- Welcome → Next
- License → Accept → Next
- Install Location → Next (default)
- Tasks → tick "Launch DentaCare window at logon" → Next
- Install → UAC prompt → Yes
- Watch progress: WebView2 (if needed), BT provisioning, service registration
- Finish → DentaCare window opens to sign-in

Verify:
- `services.msc` shows DentaCare → Running
- `C:\Program Files\DentaCare\` contains DentaCare.exe, DentaCareService.exe, nssm.exe, installer\provision_bt.ps1
- `C:\ProgramData\DentaCare\` contains uploads/, backups/, logs/
- `C:\ProgramData\DentaCare\logs\service.stdout.log` is being written to
- Start Menu has "DentaCare" group with the launcher + Uninstall
- Reboot → after logon, DentaCare window auto-opens (because of the autostart task)
- Uninstall via Control Panel → Apps → DentaCare → service is removed, Program Files folder is removed, prompt asks about ProgramData (click No to keep)

- [ ] **Step 5: Commit**

```bash
rtk git add installer/DentaCare.iss
rtk git commit -m "installer: Inno Setup script (base + service + BT + WebView2)

Compiles to installer\Output\DentaCare-Setup.exe. Provisions data dir,
installs WebView2 if missing, runs provision_bt.ps1, registers the
NSSM service with proper env vars, creates Start Menu shortcuts and
optional autostart, and asks about clinic-data preservation on
uninstall.

Smoke-tested on Windows 11: install -> service running -> window
opens to sign-in -> reboot -> autostart works -> uninstall preserves
ProgramData when requested.
"
```

---

## Task D4: Database migration from legacy portable install

**Files:**
- Modify: `installer/DentaCare.iss` (add `[Code]` migration procedure)

- [ ] **Step 1: Add migration logic to `DentaCare.iss`**

In the `[Code]` section of `installer/DentaCare.iss`, add the procedure below before `procedure CurUninstallStepChanged`:

```pascal
procedure CopyLegacyDatabase;
var
  CandidatePaths: array of string;
  i: Integer;
  SrcPath, DstPath, Response: string;
  RespCode: Integer;
begin
  // Common legacy locations where the portable .exe stored its DB:
  //   - Desktop folder of the user who ran the installer
  //   - Documents
  //   - C:\DentaCare (some users move the folder to root)
  SetArrayLength(CandidatePaths, 3);
  CandidatePaths[0] := ExpandConstant('{userdesktop}\dental_clinic.db');
  CandidatePaths[1] := ExpandConstant('{userdocs}\dental_clinic.db');
  CandidatePaths[2] := 'C:\DentaCare\dental_clinic.db';

  DstPath := ExpandConstant('{commonappdata}\DentaCare\dental_clinic.db');

  if FileExists(DstPath) then exit;  // Already migrated or fresh install.

  for i := 0 to GetArrayLength(CandidatePaths) - 1 do begin
    SrcPath := CandidatePaths[i];
    if FileExists(SrcPath) then begin
      RespCode := MsgBox(
        'Existing DentaCare database found:' + #13#10 + #13#10 +
        SrcPath + #13#10 + #13#10 +
        'Copy it to the new location so your patient data carries over?' + #13#10 +
        '(Original will be left in place as a backup.)',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON1);
      if RespCode = IDYES then begin
        FileCopy(SrcPath, DstPath, False);
      end;
      exit;  // Stop at first found, regardless of choice.
    end;
  end;
end;
```

Then add a call to `CopyLegacyDatabase` in `CurStepChanged` (which Inno Setup calls during install). Add this procedure to `[Code]`:

```pascal
procedure CurStepChanged(CurStep: TSetupStep);
begin
  // ssPostInstall runs after files are copied but before [Run] steps. We
  // migrate the DB here so the service starts with the customer's data
  // already in the new location.
  if CurStep = ssPostInstall then begin
    CopyLegacyDatabase;
  end;
end;
```

- [ ] **Step 2: Recompile + smoke test**

```bash
rtk "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DentaCare.iss
```

**To test the migration path:** drop a sentinel `dental_clinic.db` file on your Desktop (any SQLite file works for the prompt, even an empty file named that), uninstall any existing DentaCare, then run the installer. You should see the migration prompt. Click Yes. After install, `C:\ProgramData\DentaCare\dental_clinic.db` exists and the original on Desktop is still there.

- [ ] **Step 3: Commit**

```bash
rtk git add installer/DentaCare.iss
rtk git commit -m "installer(db-migrate): carry forward legacy portable DB on install

Detects dental_clinic.db on Desktop, Documents, or C:\DentaCare;
prompts the user; copies to the new ProgramData location if they
agree. Original is left in place as a safety backup. Idempotent —
skipped if the destination already exists.
"
```

---

## Task D5: README + final manual smoke-test pass

**Files:**
- Modify: `README.md` (sections "Quick Start" and "Packaging")

- [ ] **Step 1: Update README "Quick Start"**

Read `README.md` to see the current Quick Start. Replace the "Desktop server" subsection with this content (preserve everything before and after):

```markdown
### Desktop server

**Customers:** Download `DentaCare-Setup.exe` from the releases page, double-click, follow the wizard. After install, DentaCare runs as a Windows service in the background; click the Start Menu icon to open the window. The service auto-starts on Windows boot, so mobile sync stays alive even when the window is closed.

**Developers (running from source):**

```bash
# Windows
py dental_clinic.py
.\start.bat

# Linux / macOS
python3 dental_clinic.py
```

Source mode auto-opens the system browser at `http://localhost:5000` with Werkzeug's auto-reloader active. Set `CLINIC_HEADLESS=1` to skip the browser auto-open (useful when testing the window app: in a second terminal, `python dentacare_window.py` opens the pywebview window against the running service).
```

- [ ] **Step 2: Update README "Packaging"**

Replace the existing "Packaging (Windows executable)" section with:

```markdown
## Packaging (Windows installer)

```bash
# Build both binaries + stage the installer payload.
rebuild.bat

# Compile the Inno Setup installer (requires Inno Setup 6).
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DentaCare.iss
# Output: installer\Output\DentaCare-Setup.exe
```

`rebuild.bat` produces:
- `dist\DentaCare.exe` — windowed launcher (pywebview wrapping the Flask UI)
- `dist\DentaCareService.exe` — headless Flask service (run by NSSM)
- `dist\staging\` — installer payload (binaries + NSSM + WebView2 bootstrapper + icon)

The `DentaCare.spec` PyInstaller spec bundles both entry points. `hiddenimports` covers waitress, markupsafe, werkzeug.security, serial (Bluetooth SPP), pystray (tray icon), and PIL.

The Inno Setup installer (`installer\DentaCare.iss`):
- Installs to `C:\Program Files\DentaCare\`
- Creates data folder at `C:\ProgramData\DentaCare\{uploads,backups,logs}\`
- Migrates legacy portable DB if found (Desktop, Documents, or `C:\DentaCare`)
- Installs WebView2 runtime if absent (bundled Evergreen Bootstrapper)
- Runs `installer\provision_bt.ps1` to set up the Incoming SPP COM port
- Registers DentaCare as an auto-start Windows service via NSSM
- Adds Start Menu shortcuts; optional Desktop shortcut; optional auto-launch at logon
- Uninstaller preserves `ProgramData\DentaCare\` by default (asks before deleting)
```

- [ ] **Step 3: Final manual smoke-test pass on a clean Windows 11 VM**

Execute every row of the manual smoke-test table from the spec (`docs/superpowers/specs/2026-05-26-standalone-exe-migration-design.md`, section "Manual smoke-test on Windows VM"). Record pass/fail per row. Fix issues, re-test until all pass.

- [ ] **Step 4: Commit**

```bash
rtk git add README.md
rtk git commit -m "docs(readme): document installer-based packaging + dev workflow

Quick Start now points customers at DentaCare-Setup.exe. Developers
still get the source-mode flow with auto-reloader. Packaging section
describes the two-binary spec + Inno Setup installer pipeline.
"
```

---

## Phase D checkpoint — release-ready

After Tasks D1-D5:
- `installer\Output\DentaCare-Setup.exe` builds reproducibly from `rebuild.bat` + `ISCC.exe`
- Installer passes the full manual smoke-test table on a clean Windows 11 VM
- All 187 automated tests still pass
- Existing customers can upgrade via running the installer; clinic data preserved
- README points new customers at the installer

**Verify:**

```bash
rtk python -m pytest tests/ -v
```

Expected: 187 passes.

Plus: every row of the manual smoke-test table in the spec passes.

---

# Self-review

**1. Spec coverage:**

- Service-mode refactor (spec § Architecture > Component 1, dev workflow) → Phase A ✓
- pywebview window launcher (spec § Component 2) → Phase B ✓
- Two-binary PyInstaller (spec § Component 3 prep, file layout) → Task C2 ✓
- NSSM service registration (spec § Component 1) → Task C4 ✓
- Inno Setup installer (spec § Component 3) → Task D3 ✓
- BT COM port provisioning (spec § Component 3 step 9) → Tasks D1 (bundle), D2 (script), D3 (call from installer) ✓
- WebView2 bootstrapper (spec § Component 3 step 12, Risks) → Tasks D1 (bundle), D3 (Inno Setup `[Run]` + `NeedsWebView2`) ✓
- DB migration from legacy portable (spec § Component 3 step 7) → Task D4 ✓
- Auto-launch at logon (spec § Component 3 step 11) → Task D3 (Tasks/Registry sections) ✓
- Uninstall preserves data (spec § Component 3 step 14) → Task D3 (`CurUninstallStepChanged`) ✓
- Existing 170 tests preserved (spec § What does NOT change) → A2 + each phase checkpoint ✓
- Cloud-mode untouched (spec § Cloud-mode handling) → A2 verified by full test suite; CLOUD_MODE branch unchanged ✓
- Headless mode flag (spec § Dev workflow) → Task A3 ✓
- Tray icon menu (spec § Component 2) → Task B7 ✓
- Single-instance enforcement (spec § Component 2) → Task B4 ✓
- Window state persistence (spec § Component 2) → Task B3 ✓
- Offline page (spec § Component 2) → Task B5 ✓
- README updates → Task D5 ✓

No gaps found.

**2. Placeholder scan:** all code blocks contain full implementations; no "TODO", "implement later", "add appropriate error handling" without specifics. The `provision_bt.ps1` script has an honest note about the limitation of programmatic Incoming-SPP creation on Windows 10/11 — that's not a placeholder, it's documented behavior with a fallback (open the dialog).

**3. Type consistency:** `WindowState` dataclass fields match between `window/window_state.py` and the tests. `wait_for_service(url, timeout)` signature matches in `health_check.py` and `dentacare_window.py`. `SingleInstanceGuard().is_first_instance` matches across files. Service env vars (`CLINIC_HEADLESS`, `CLINIC_DATA_DIR`, `CLINIC_HOST`, `CLINIC_PORT`) match between `dental_clinic.py`, `register-service.bat`, and `installer/DentaCare.iss`.

**4. Ambiguity check:** `resolve_data_dir()` precedence is explicit (env > frozen+PROGRAMDATA > frozen+LOCALAPPDATA > frozen+home > source); migration is "copy not move"; uninstall data preservation defaults to KEEP (MB_DEFBUTTON2 = No); single-instance behavior is "first wins, others bring existing to front then exit".

---

# Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-26-standalone-exe-migration.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration with isolated context.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
