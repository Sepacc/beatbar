@echo off
setlocal enabledelayedexpansion
title Web Beatbar Viewer (Mobile and Browser Streamer)

:: Determine project root directory (works if kept in Guide\ or copied to root)
if exist "%~dp0web\run_web.py" (
    cd /d "%~dp0"
) else if exist "%~dp0..\web\run_web.py" (
    cd /d "%~dp0.."
) else (
    echo [ERROR] Could not find the Beatbar project root directory!
    echo Ensure this script is located inside the Guide\ folder or the project root.
    pause
    exit /b 1
)

:: Find Python interpreter
set "PY_CMD="
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 set "PY_CMD=python"
if "%PY_CMD%"=="" (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 set "PY_CMD=py"
)

if "%PY_CMD%"=="" (
    echo.
    echo ===============================================================================
    echo [ERROR] Python was not found in your system PATH!
    echo Please run "Guide\install_dependencies.bat" to install dependencies,
    echo or download Python 3.10+ from https://www.python.org/
    echo ===============================================================================
    echo.
    pause
    exit /b 1
)

echo Starting Web Beatbar Viewer server...
echo Point your mobile browser to the displayed LAN IP or scan the QR code in the browser.
echo Press Ctrl+C in this console window to stop the server.
echo.
%PY_CMD% web\run_web.py --open %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Web Beatbar Viewer exited with error code %ERRORLEVEL%.
    pause
)
