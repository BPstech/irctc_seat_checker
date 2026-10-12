@echo off
setlocal
title IRCTC Green Seat Finder - Local PC Mode

echo ==================================================================
echo   🚂 IRCTC Green Seat Finder — Local PC Mode
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

:: 3. Launch default browser after 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"

:: 4. Start local Flask server
echo.
echo ==================================================================
echo   🚀 Starting local web server at http://localhost:5000...
echo   🌐 Opening in your default browser...
echo   Press Ctrl+C or close this window to stop the server.
echo ==================================================================
echo.

set PORT=5000
python app.py

pause
