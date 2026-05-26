@echo off
REM Register DentaCare as a Windows service via NSSM. Self-elevates via UAC,
REM so a double-click works.
REM Assumes the staging folder from rebuild.bat lives at dist\staging\.
REM Used in Phase C smoke tests before the Inno Setup installer exists.

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
set DATA_DIR=%PROGRAMDATA%\DentaCare

if not exist "%STAGING_DIR%\DentaCareService.exe" (
    echo ERROR: %STAGING_DIR%\DentaCareService.exe not found.
    echo Run rebuild.bat first.
    pause
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
echo.
pause
endlocal
