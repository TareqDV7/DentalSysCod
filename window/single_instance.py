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
