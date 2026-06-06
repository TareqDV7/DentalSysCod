@echo off
REM DentaCare local-server launcher.
REM Invokes python.exe directly so Explorer double-click doesn't go through
REM the .py file association — that handoff fails with 0xc0000022 on
REM machines with Defender Controlled Folder Access enabled on Desktop.
REM Also pins to the 3.14 install registered with the Python Launcher.

setlocal
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Run in production mode (waitress, no dev reloader). This also starts the
REM background workers that only run outside debug — most importantly the
REM always-on cloud-sync worker, which auto-links to the cloud using the
REM activation key and mirrors in the background. (The packaged exe already
REM runs production because it's frozen; this gives the source launcher parity.)
set CLINIC_DEBUG=0

REM Prefer the launcher (resolves the active 3.14 install). Fall back to a
REM direct python.exe path if the launcher isn't on PATH.
where py.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3.14 "%SCRIPT_DIR%dental_clinic.py" %*
) else (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" "%SCRIPT_DIR%dental_clinic.py" %*
)

REM Keep the window open if the server exits or crashes so the user can
REM read the error instead of the console vanishing.
if errorlevel 1 (
    echo.
    echo Server exited with errorlevel %ERRORLEVEL%.
    pause
)
endlocal
