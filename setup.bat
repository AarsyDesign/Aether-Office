@echo off
title Aether Office - Setup
cd /d "%~dp0"

echo ===================================================
echo   Aether Office - One-Click Environment Setup
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv. Ensure Python 3.10+ is installed and in PATH.
        pause
        exit /b 1
    )
)

echo [*] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [*] Installing dependencies and UI extensions...
".venv\Scripts\python.exe" -m pip install -e ".[ui]"
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   [SUCCESS] Aether Office is ready!
echo   To launch the visual dashboard, run:
echo     start_dashboard.bat
echo   or:
echo     npm start
echo ===================================================
echo.
pause
