@echo off
setlocal enabledelayedexpansion
title Beatbar Suite - Dependency Installer

echo ===============================================================================
echo                Beatbar Suite - Automated Dependency Installer
echo ===============================================================================
echo.

:: 1. Detect Python command
set "PY_CMD="
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set "PY_CMD=py"
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python was not found in your system PATH!
    echo.
    echo Please install Python 3.10 or newer from:
    echo https://www.python.org/downloads/
    echo.
    echo NOTE: Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [OK] Detected Python interpreter:
%PY_CMD% --version
echo.

:: 2. Locate requirements.txt
set "REQ_FILE="
if exist "%~dp0..\requirements.txt" (
    set "REQ_FILE=%~dp0..\requirements.txt"
) else if exist "%~dp0requirements.txt" (
    set "REQ_FILE=%~dp0requirements.txt"
)

:: 3. Upgrade pip
echo [INFO] Upgrading pip package manager...
%PY_CMD% -m pip install --upgrade pip --quiet
echo.

:: 4. Install dependencies
echo [INFO] Installing required Python libraries...
if defined REQ_FILE (
    echo [INFO] Using requirements file: "%REQ_FILE%"
    %PY_CMD% -m pip install -r "%REQ_FILE%"
) else (
    echo [INFO] requirements.txt not found, installing packages directly...
    %PY_CMD% -m pip install PyQt6 opencv-python numpy scipy librosa Pillow Flask "qrcode[pil]" pyinstaller
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] One or more Python packages failed to install!
    echo Please inspect the error messages above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ===============================================================================
echo                      Verifying Installed Packages
echo ===============================================================================
%PY_CMD% -c "import sys; pkgs = [('PyQt6', 'PyQt6 GUI'), ('cv2', 'OpenCV (opencv-python)'), ('numpy', 'NumPy Math'), ('scipy', 'SciPy DSP'), ('librosa', 'Librosa Audio Analysis'), ('PIL', 'Pillow Imaging'), ('flask', 'Flask Web Server'), ('qrcode', 'QR Code Generator')]; errs = False; [print(f'  [OK] {desc} ({mod})') if not __import__(mod) else None for mod, desc in pkgs]; [print('  [OK] PyInstaller Compiler') if not __import__('PyInstaller') else None]; print('\n[SUCCESS] All core Python dependencies are installed and verified!')"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Some core Python packages could not be verified.
)

:: 5. Check FFmpeg
echo.
echo ===============================================================================
echo                      Checking FFmpeg System Utility
echo ===============================================================================
where ffmpeg >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] FFmpeg is available in system PATH.
    for /f "tokens=*" %%v in ('ffmpeg -version 2^>^&1 ^| findstr /i "ffmpeg version"') do (
        echo      %%v
    )
) else (
    echo [NOTICE] FFmpeg was not found in PATH.
    echo FFmpeg is recommended for extracting audio from video files and thumbnail generation.
    echo You can install it using one of these options:
    echo   - Winget: winget install Gyan.FFmpeg
    echo   - Scoop:  scoop install ffmpeg
    echo   - Direct: Download from https://ffmpeg.org/download.html and add to PATH.
)

echo.
echo ===============================================================================
echo Installation script finished. You can now launch any Beatbar application!
echo ===============================================================================
pause
exit /b 0
