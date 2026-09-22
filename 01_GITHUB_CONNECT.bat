@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo   WorkshopPilot - GitHub Connect
echo ==========================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] git.exe not found.
    echo Install Git for Windows first.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [INFO] Initializing local repository...
    git init
    if errorlevel 1 goto :error
)

git branch -M main
if errorlevel 1 goto :error

set /p REPO_URL=GitHub repository URL: 
if "%REPO_URL%"=="" (
    echo [ERROR] Empty repository URL.
    pause
    exit /b 1
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
    git remote add origin "%REPO_URL%"
    if errorlevel 1 goto :error
) else (
    echo.
    echo Current origin:
    git remote get-url origin
    echo.
    choice /C YN /M "Replace origin URL"
    if errorlevel 2 goto :show
    git remote set-url origin "%REPO_URL%"
    if errorlevel 1 goto :error
)

:show
echo.
git remote -v
echo.
echo [OK] GitHub remote configured.
echo Next: run 02_COMMIT_AND_PUSH.bat
pause
exit /b 0

:error
echo.
echo [ERROR] Git operation failed.
pause
exit /b 1
