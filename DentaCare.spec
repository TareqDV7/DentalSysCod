# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DentaCare.

Builds two binaries:
  - DentaCareService.exe  : headless Flask app (run by NSSM as a Windows service)
  - DentaCare.exe         : pywebview window launcher (user-facing)

Both share the same Python codebase but have different entry points
and different console/window flags. Build both with:
    pyinstaller DentaCare.spec --noconfirm --clean"""


# Hidden imports common to both binaries — needed by the Flask app at runtime.
COMMON_HIDDEN = [
    'flask',
    'flask_cors',
    'waitress',
    'waitress.server',
    'werkzeug',
    'werkzeug.serving',
    'werkzeug.security',
    'werkzeug.middleware.proxy_fix',
    'werkzeug.routing',
    'werkzeug.exceptions',
    'markupsafe',
    'jinja2',
    'jinja2.ext',
    'click',
    'serial',
    'serial.tools.list_ports',
    # Ed25519 vendor-serial verification (cloud license authority).
    'cryptography',
    'cryptography.exceptions',
    'cryptography.hazmat.primitives.asymmetric.ed25519',
    'cryptography.hazmat.backends.openssl',
    'sqlite3',
    'hmac',
    'hashlib',
    'secrets',
    'uuid',
    'email.mime.text',
    'email.mime.multipart',
    'threading',
    'webbrowser',
    'pathlib',
    'json',
    'datetime',
    're',
    'os',
    'sys',
]

# Data files bundled into both exes.
COMMON_DATAS = [
    ('DentaCare.PNG', '.'),
]

# The window launcher additionally bundles its HTML / tray icon assets.
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
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
service_pyz = PYZ(service_a.pure)
service_exe = EXE(
    service_pyz,
    service_a.scripts,
    service_a.binaries,
    service_a.datas,
    [],
    name='DentaCareService',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                       # service: console so NSSM can capture stdout/stderr
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='DentaCare.ico',
)

# --- The windowed launcher ---------------------------------------------------
window_a = Analysis(
    ['dentacare_window.py'],
    pathex=[],
    binaries=[],
    datas=WINDOW_DATAS,
    hiddenimports=COMMON_HIDDEN + [
        'webview',
        'webview.platforms.winforms',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL._tkinter_finder',
        'clr_loader',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
window_pyz = PYZ(window_a.pure)
window_exe = EXE(
    window_pyz,
    window_a.scripts,
    window_a.binaries,
    window_a.datas,
    [],
    name='DentaCare',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                      # launcher: windowed, no console flash on start
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='DentaCare.ico',
)
