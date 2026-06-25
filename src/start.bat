@echo off

e:
cd E:\Users\takashi\Desktop\ClaudeCode\morokoshi\src

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause & exit /b 1
)
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg not found in PATH.
    echo   Download: https://ffmpeg.org/download.html
    echo.
)
echo Installing / updating libraries...
pip install numpy sounddevice soundfile librosa scipy pillow PyQt6 python-stretch -q
echo.
echo Starting Morokoshi Time...
python morokoshi.py %1
if errorlevel 1 (
    echo.
    echo [ERROR] App failed to start.
    pause
)
