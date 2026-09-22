@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found.
    echo Run SETUP_VENV.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] WorkshopPilot exited with an error.
    pause
)
