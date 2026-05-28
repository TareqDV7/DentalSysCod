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
