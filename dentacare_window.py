"""DentaCare desktop window — the customer-facing launcher.

Boots the pywebview window pointed at the local Flask service. Handles:
  - single-instance enforcement (named mutex)
  - waiting for the service to be ready
  - showing an offline page if the service never responds
  - tray icon with Open / Restart engine / Open logs / Quit menu
  - close-to-hide (X button hides; Quit from tray actually exits)
  - window state persistence (size, position)

This file is what `DentaCare.exe` runs when the customer clicks the
Start Menu icon. The service is a separate process (DentaCareService.exe)
supervised by NSSM."""

import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import webview
from PIL import Image
import pystray

from window.data_dir import resolve_data_dir
from window.health_check import wait_for_service
from window.single_instance import SingleInstanceGuard
from window.window_state import (
    WindowState,
    is_hidden_geometry,
    load_window_state,
    save_window_state,
)


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
        try:
            subprocess.run(['sc', 'start', 'DentaCare'],
                           capture_output=True, check=False, timeout=10)
        except Exception:
            pass


def _resolve_initial_url() -> tuple[str, bool]:
    """Return (url, booted_on_offline). booted_on_offline=True means the
    caller should spawn a background poll to swap to SERVICE_URL once the
    service comes up."""
    if wait_for_service(HEALTHZ_URL, timeout=BOOT_GRACE_SECONDS):
        return SERVICE_URL, False
    return (ASSETS_DIR / 'offline.html').as_uri(), True


def _service_is_healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTHZ_URL, timeout=1.0) as r:
            return r.status == 200
    except (urllib.error.URLError, ConnectionError, OSError, TimeoutError):
        return False


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
            w = int(self.window.width or 0)
            h = int(self.window.height or 0)
            x = int(self.window.x) if self.window.x is not None else None
            y = int(self.window.y) if self.window.y is not None else None
            if is_hidden_geometry(x, y, w, h):
                return
            save_window_state(WindowState(width=w, height=h, x=x, y=y), WINDOW_STATE_PATH)
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

    def _recover_when_service_ready(self):
        # The offline page is loaded from file://, and modern WebView2 blocks
        # cross-scheme fetches from file:// to http://, so the in-page JS poll
        # can't reliably recover. Drive recovery from Python instead.
        while not self._quit_requested:
            if _service_is_healthy():
                try:
                    self.window.load_url(SERVICE_URL)
                except Exception:
                    pass
                return
            time.sleep(2.0)

    def run(self):
        initial_url, booted_on_offline = _resolve_initial_url()
        self.window = webview.create_window(
            title='DentaCare',
            url=initial_url,
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
        if booted_on_offline:
            threading.Thread(target=self._recover_when_service_ready, daemon=True).start()

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
