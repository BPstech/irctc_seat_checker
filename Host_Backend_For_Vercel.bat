@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title IRCTC Backend - Live Cloud Tunnel for Vercel

echo ==================================================================
echo   [IRCTC] Green Seat Finder -- PC Backend for Vercel
echo ==================================================================
echo.

:: 1. Check Python installation
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

:: 2. Ensure dependencies are installed
echo [*] Checking Python libraries...
python -c "import flask, selenium, flask_cors, requests" >nul 2>&1
if errorlevel 1 (
    echo Installing missing Python packages from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install packages. Check your internet connection.
        pause
        exit /b 1
    )
)

:: 3. Run the automated tunnel and backend manager
python host_tunnel.py

if errorlevel 1 (
    echo.
    echo [!] Process stopped with an error.
    pause
)
