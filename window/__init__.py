"""Window-app helpers for the packaged DentaCare desktop exe.

This package is consumed by both `dentacare_window.py` (the windowed
launcher) and `dental_clinic.py` (the service). It must stay importable
without any GUI or pywebview deps so the service binary can use the
data-dir resolution without dragging webview code into the service."""
