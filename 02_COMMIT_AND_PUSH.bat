@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo   WorkshopPilot - Commit and Push
echo ==========================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] git.exe not found.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [ERROR] Not a Git repository.
    echo Run 01_GITHUB_CONNECT.bat first.
    pause
    exit /b 1
)

echo [STATUS]
git status --short
echo.

set /p MSG=Commit message: 
if "%MSG%"=="" set MSG=Update project

git add -A
if errorlevel 1 goto :error

git diff --cached --quiet
if not errorlevel 1 (
    echo [INFO] No staged changes.
) else (
    git commit -m "%MSG%"
    if errorlevel 1 goto :error
)

for /f "delims=" %%b in ('git branch --show-current') do set BRANCH=%%b
if "%BRANCH%"=="" set BRANCH=main

echo.
echo [INFO] Pushing %BRANCH%...
git push -u origin "%BRANCH%"
if errorlevel 1 goto :error

echo.
echo [OK] Commit and push complete.
pause
exit /b 0

:error
echo.
echo [ERROR] Commit/push failed.
pause
exit /b 1
