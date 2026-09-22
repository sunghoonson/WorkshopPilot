@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"

echo ==========================================
echo   WorkshopPilot - Project Snapshot
echo ==========================================
echo.

"%PY%" dev_tools\collect_project_snapshot.py
if errorlevel 1 (
    echo.
    echo [ERROR] Snapshot failed.
    pause
    exit /b 1
)

echo.
echo [OK] Snapshot complete.
pause
