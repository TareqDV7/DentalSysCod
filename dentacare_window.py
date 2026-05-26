"""DentaCare desktop window — the customer-facing launcher.

Boots the pywebview window pointed at the local Flask service. Handles:
  - single-instance enforcement (named mutex)
  - waiting for the service to be ready
  - showing an offline page if the service never responds
  - window state persistence (size, position)

This file is what `DentaCare.exe` runs when the customer clicks the
Start Menu icon. The service is a separate process (DentaCareService.exe)
supervised by NSSM.

Task B7 will add the tray icon + close-to-hide behavior on top of this."""

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
