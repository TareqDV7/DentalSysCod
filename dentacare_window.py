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
from window.service_port import service_url as _published_service_url
from window.single_instance import SingleInstanceGuard
from window.window_state import (
    WindowState,
    clamp_to_screen,
    is_hidden_geometry,
    load_window_state,
    save_window_state,
)


def _service_url() -> str:
    """Base URL of the local service, re-read from the published port file on
    each call so the window follows the service even when it had to bind a
    non-default port (e.g. 5000 was already taken by another local app)."""
    return _published_service_url()


def _healthz_url() -> str:
    return f'{_service_url()}/healthz'


BOOT_GRACE_SECONDS = 10.0
ASSETS_DIR = Path(__file__).resolve().parent / 'window' / 'assets'
WINDOW_STATE_PATH = (
    Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    / 'DentaCare'
    / 'window-state.json'
)


def _screen_work_area():
    """(width, height) of the primary monitor's work area (taskbar excluded) on
    Windows, or (0, 0) when it can't be determined. Callers treat (0, 0) as
    'unknown' and skip clamping. Used so a window saved on a big monitor doesn't
    open with its edges off a smaller screen."""
    if sys.platform != 'win32':
        return (0, 0)
    try:
        import ctypes
        from ctypes import wintypes
        SPI_GETWORKAREA = 0x0030
        # Match the per-monitor DPI awareness pywebview sets, so the work area
        # we read is in the same pixel space as the window geometry.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        rect = wintypes.RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        if not ok:
            return (0, 0)
        return (rect.right - rect.left, rect.bottom - rect.top)
    except Exception:
        return (0, 0)


class WindowApi:
    """Exposed to the web UI via pywebview's JS bridge."""

    def restart_service(self):
        try:
            subprocess.run(['sc', 'start', 'DentaCare'],
                           capture_output=True, check=False, timeout=10)
        except Exception:
            pass

    def open_path(self, path):
        """Reveal an exported file (or its folder) in the OS file manager.

        The portal calls this after a desktop export, because the embedded
        WebView can't surface a browser download — the server writes the bundle
        to disk and the shell opens it here. Returns True on a best-effort launch."""
        try:
            target = os.path.normpath(str(path or ''))
            if not target:
                return False
            if sys.platform == 'win32':
                # '/select,' opens Explorer with the file highlighted.
                subprocess.run(['explorer', '/select,', target], check=False)
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R', target], check=False)
            else:
                subprocess.run(['xdg-open', os.path.dirname(target) or '.'], check=False)
            return True
        except Exception:
            return False


def _resolve_initial_url() -> tuple[str, bool]:
    """Return (url, booted_on_offline). booted_on_offline=True means the
    caller should spawn a background poll to swap to the service once it comes
    up. The port is re-read each attempt so a service that publishes its port a
    moment after the window starts is still picked up within the grace window."""
    deadline = time.monotonic() + BOOT_GRACE_SECONDS
    while time.monotonic() < deadline:
        if _service_is_healthy():
            return _service_url(), False
        time.sleep(0.25)
    return (ASSETS_DIR / 'offline.html').as_uri(), True


def _service_is_healthy() -> bool:
    try:
        with urllib.request.urlopen(_healthz_url(), timeout=1.0) as r:
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
                    self.window.load_url(_service_url())
                except Exception:
                    pass
                return
            time.sleep(2.0)

    def run(self):
        initial_url, booted_on_offline = _resolve_initial_url()
        # Shrink/reposition a geometry saved on a larger monitor so it fits this
        # screen — otherwise the bottom edge and buttons can land off-screen.
        screen_w, screen_h = _screen_work_area()
        state = clamp_to_screen(self._state, screen_w, screen_h)
        self.window = webview.create_window(
            title='DentaCare',
            url=initial_url,
            width=state.width,
            height=state.height,
            x=state.x,
            y=state.y,
            resizable=True,
            min_size=(min(900, state.width), min(600, state.height)),
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
