@echo off
setlocal
cd /d "%~dp0.."

:: Check if pythonw is available in PATH (spawns GUI without console window)
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw launcher\launcher.py %*
    exit /b 0
)

:: Try pyw (Python Launcher without console window)
where pyw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pyw launcher\launcher.py %*
    exit /b 0
)

:: Fallback to python.exe
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" python launcher\launcher.py %*
    exit /b 0
)

:: Error handling if Python was not found
echo.
echo ============================================================
echo [ERROR] Python was not found in your PATH!
echo Please ensure Python 3 is installed and added to PATH.
echo ============================================================
echo.
pause
exit /b 1
