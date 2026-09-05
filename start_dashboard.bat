@echo off
title Aether Office - Game Dashboard
cd /d "%~dp0"

echo ===================================================
echo   Starting Aether Office Virtual Game Dashboard...
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [*] First time launch detected! Setting up environment automatically...
    where uv >nul 2>nul
    if %errorlevel% equ 0 (
        uv venv --python 3.11 --clear
        uv pip install -e ".[ui]" httpx httpx2 pytest pytest-cov pytest-asyncio
    ) else (
        python -m venv .venv
        ".venv\Scripts\python.exe" -m pip install --upgrade pip
        ".venv\Scripts\python.exe" -m pip install -e ".[ui]" httpx httpx2 pytest pytest-cov pytest-asyncio
    )
    echo [*] Setup complete!
    echo.
)

echo [*] Launching dashboard server at http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" cli.py dashboard %*

pause
