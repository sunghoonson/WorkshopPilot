@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   WorkshopPilot - Setup
echo ==========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] py.exe not found.
    echo Install Python 3.11+ first.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating .venv with Python 3.11...
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo [WARN] Python 3.11 not found. Trying default Python...
        py -m venv .venv
        if errorlevel 1 goto :error
    )
) else (
    echo [1/3] Existing .venv found.
)

echo [2/3] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [3/3] Installing requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [OK] Setup complete.
pause
exit /b 0

:error
echo.
echo [ERROR] Setup failed.
pause
exit /b 1
