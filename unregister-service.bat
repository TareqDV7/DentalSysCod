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
