@echo off
setlocal enabledelayedexpansion
title Beatbar Suite - Release Packager

:: Determine project root directory
if exist "%~dp0..\launcher\launcher.py" (
    cd /d "%~dp0.."
) else (
    cd /d "%~dp0"
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
    echo [ERROR] Python was not found in your system PATH!
    pause
    exit /b 1
)

%PY_CMD% Guide\package_release.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Packaging failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

pause
exit /b 0
