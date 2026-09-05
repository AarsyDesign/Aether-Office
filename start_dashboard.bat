@echo off
title Aether Office - Game Dashboard
cd /d "%~dp0"

echo ===================================================
echo   Starting Aether Office Virtual Game Dashboard...
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [*] First time launch detected! Setting up environment automatically...
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e ".[ui]"
    echo [*] Environment setup complete!
    echo.
)

echo [*] Launching dashboard server...
".venv\Scripts\python.exe" cli.py dashboard %*

pause
