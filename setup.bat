@echo off
title Aether Office - Setup
cd /d "%~dp0"

echo ===================================================
echo   Aether Office - One-Click Environment Setup
echo ===================================================
echo.

where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [*] Using uv with Python 3.11 for ultra-fast, stable setup...
    uv venv --python 3.11 --clear
    uv pip install -e ".[ui]" httpx httpx2 pytest pytest-cov pytest-asyncio
) else (
    echo [*] Setting up standard virtual environment...
    if not exist ".venv\Scripts\python.exe" (
        python -m venv .venv
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e ".[ui]" httpx httpx2 pytest pytest-cov pytest-asyncio
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
