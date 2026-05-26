@echo off
title Rebuilding DentaCare...
echo.
echo ============================================
echo  DentaCare - Clean Rebuild
echo ============================================
echo.

cd /d "%~dp0"

echo Source file: %~dp0dental_clinic.py
echo Spec file:   %~dp0DentaCare.spec
echo.

echo [1/5] Removing old build cache...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "__pycache__" rmdir /s /q "__pycache__"
echo Done.
echo.

echo [2/5] Installing PyInstaller...
python -m pip install pyinstaller --quiet
echo Done.
echo.

echo [3/5] Verifying source file has latest changes...
findstr /c:"stat-card-teal" "%~dp0dental_clinic.py" >nul
if errorlevel 1 (
    echo ERROR: dental_clinic.py does not have the latest UI changes.
    echo Make sure you are running this from C:\Users\MSI\Desktop\clinic\
    pause
    exit /b 1
)
echo Source file verified OK.
echo.

echo [4/5] Building executable...
python -m PyInstaller "%~dp0DentaCare.spec" --noconfirm
echo.

if not exist "%~dp0dist\DentaCare.exe" (
    echo ERROR: Build failed. See output above.
    pause
    exit /b 1
)

echo [5/5] Copying to deployment folder...
copy /Y "%~dp0dist\DentaCare.exe" "%~dp0deployment\DentaCare.exe"
echo Build timestamp:
dir "%~dp0deployment\DentaCare.exe" | findstr "DentaCare"
echo.
echo ============================================
echo  Build complete!
echo  Open deployment\DentaCare.exe to test
echo ============================================
echo.
pause
