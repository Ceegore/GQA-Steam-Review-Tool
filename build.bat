@echo off
REM One-click Windows build script for Steam Review Analyzer.
REM
REM Usage (from a Developer PowerShell or cmd):
REM     build.bat
REM
REM Produces dist\SteamReviewAnalyzer.exe (single-file, windowed).

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Creating virtualenv...
    python -m venv .venv || goto :error
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto :error

echo Installing dependencies...
python -m pip install --upgrade pip || goto :error
pip install -r requirements-dev.txt || goto :error

echo Building .exe via PyInstaller...
pyinstaller --clean --noconfirm build.spec || goto :error

echo.
echo ==================================================
echo   Build OK: dist\SteamReviewAnalyzer.exe
echo ==================================================
exit /b 0

:error
echo.
echo *** BUILD FAILED ***
exit /b 1