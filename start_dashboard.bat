@echo off
title Aether Office - Game Dashboard
cd /d "%~dp0"

echo ===================================================
echo   Starting Aether Office Virtual Game Dashboard...
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cli.py dashboard %*
) else (
    python cli.py dashboard %*
)

pause
