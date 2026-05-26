@echo off
REM Stop and remove the DentaCare service. Self-elevates via UAC.
REM Leaves %PROGRAMDATA%\DentaCare untouched (the customer's clinic data).

REM Self-elevate if not already admin.
net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

setlocal

set SERVICE_NAME=DentaCare
set STAGING_DIR=%~dp0dist\staging

"%STAGING_DIR%\nssm.exe" stop %SERVICE_NAME%
"%STAGING_DIR%\nssm.exe" remove %SERVICE_NAME% confirm

echo.
echo Done. %PROGRAMDATA%\DentaCare left in place.
echo.
pause
endlocal
