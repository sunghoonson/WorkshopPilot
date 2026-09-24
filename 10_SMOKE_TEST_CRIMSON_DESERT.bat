@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo [ERROR] .venv not found. & pause & exit /b 1 )
".venv\Scripts\python.exe" dev_tools\smoke_crimson_desert.py
pause
