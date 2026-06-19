@echo off
REM Rebuild DentaCare from scratch.
REM Produces dist\DentaCareService.exe (headless Flask service),
REM dist\DentaCare.exe (pywebview window launcher), and a ready-to-package
REM staging folder at dist\staging\ that the Inno Setup installer consumes.

setlocal

cd /d "%~dp0"

echo === Cleaning previous build ===
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

echo === Installing PyInstaller ===
python -m pip install --upgrade pyinstaller --quiet

echo === Verifying source compiles ===
python -m py_compile dental_clinic.py dentacare_window.py
if errorlevel 1 (
    echo ERROR: source failed py_compile
    exit /b 1
)

echo === Building both binaries ===
python -m PyInstaller DentaCare.spec --noconfirm --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)

if not exist dist\DentaCare.exe (
    echo ERROR: dist\DentaCare.exe missing after build.
    exit /b 1
)
if not exist dist\DentaCareService.exe (
    echo ERROR: dist\DentaCareService.exe missing after build.
    exit /b 1
)

echo === Code-signing (optional) ===
REM Gated: signing only runs when DENTACARE_SIGN is set, so unsigned dev builds
REM keep working unchanged. DENTACARE_SIGNTOOL_ARGS holds your CA-specific args
REM (everything after "signtool sign", excluding the file). See docs/SIGNING.md.
if not defined DENTACARE_SIGN (
    echo   Skipping: DENTACARE_SIGN not set. Binaries will be UNSIGNED.
    goto :after_sign
)
if not defined DENTACARE_SIGNTOOL_ARGS (
    echo ERROR: DENTACARE_SIGN is set but DENTACARE_SIGNTOOL_ARGS is empty.
    echo   Example: set DENTACARE_SIGNTOOL_ARGS=/fd sha256 /a /tr http://timestamp.example /td sha256
    exit /b 1
)
set "SIGNTOOL="
where signtool.exe >nul 2>&1 && set "SIGNTOOL=signtool.exe"
if not defined SIGNTOOL (
    for /f "delims=" %%I in ('dir /b /s "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" 2^>nul') do set "SIGNTOOL=%%I"
)
if not defined SIGNTOOL (
    echo ERROR: signtool.exe not found. Install the Windows SDK "Signing Tools for Desktop Apps".
    exit /b 1
)
echo   Using signtool: %SIGNTOOL%
"%SIGNTOOL%" sign %DENTACARE_SIGNTOOL_ARGS% "dist\DentaCare.exe" || (echo ERROR: signing DentaCare.exe failed & exit /b 1)
"%SIGNTOOL%" sign %DENTACARE_SIGNTOOL_ARGS% "dist\DentaCareService.exe" || (echo ERROR: signing DentaCareService.exe failed & exit /b 1)
"%SIGNTOOL%" verify /pa "dist\DentaCare.exe" || (echo ERROR: signature verify failed & exit /b 1)
echo   Signed + verified dist\DentaCare.exe and dist\DentaCareService.exe
:after_sign

echo === Staging installer payload ===
mkdir dist\staging
copy /y dist\DentaCare.exe          dist\staging\
copy /y dist\DentaCareService.exe   dist\staging\
copy /y DentaCare.PNG               dist\staging\
copy /y installer\nssm.exe          dist\staging\
if exist installer\provision_bt.ps1 (
    copy /y installer\provision_bt.ps1 dist\staging\
)
if exist installer\MicrosoftEdgeWebview2Setup.exe (
    copy /y installer\MicrosoftEdgeWebview2Setup.exe dist\staging\
)

echo === Copying to deployment ===
if not exist deployment mkdir deployment
copy /y dist\DentaCare.exe          deployment\
copy /y dist\DentaCareService.exe   deployment\

echo.
echo Build complete:
echo   dist\DentaCare.exe          (window launcher)
echo   dist\DentaCareService.exe   (headless service)
echo   dist\staging\               (installer payload for Inno Setup)
echo.
endlocal
