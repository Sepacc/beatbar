@echo off
setlocal enabledelayedexpansion
title Beatbar Viewer (Video and Beatbar Player)

:: Determine project root directory (works if kept in Guide\ or copied to root)
if exist "%~dp0viewer\main.py" (
    cd /d "%~dp0"
) else if exist "%~dp0..\viewer\main.py" (
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

echo Starting Beatbar Viewer...
%PY_CMD% -m viewer %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Beatbar Viewer exited with error code %ERRORLEVEL%.
    pause
)
