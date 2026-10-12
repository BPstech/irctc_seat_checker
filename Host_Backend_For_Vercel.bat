@echo off
setlocal EnableDelayedExpansion
title IRCTC Backend - Live Cloud Tunnel for Vercel

echo ==================================================================
echo   🚂 IRCTC Green Seat Finder — PC Backend for Vercel
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
echo [1/4] Checking Python libraries...
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
echo [✓] Python libraries verified.

:: 3. Check for Cloudflare Tunnel tool (cloudflared.exe)
if not exist "cloudflared.exe" (
    echo [2/4] Downloading lightweight Cloudflare Tunnel tool (one-time setup, ~30MB)...
    curl.exe -L -s -o cloudflared.exe "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if errorlevel 1 (
        echo [ERROR] Failed to download cloudflared.exe. Please check your internet connection.
        pause
        exit /b 1
    )
    echo [✓] Cloudflare Tunnel tool ready.
) else (
    echo [2/4] Cloudflare Tunnel tool ready.
)

:: 4. Clean up any previous log or tunnel instance
taskkill /F /IM cloudflared.exe >nul 2>&1
if exist "cloudflared.log" del /f /q "cloudflared.log"

:: 5. Start Cloudflare Tunnel in background
echo [3/4] Establishing secure HTTPS public tunnel...
start "" /B cloudflared.exe tunnel --url http://127.0.0.1:5000 > cloudflared.log 2>&1

:: Wait up to 15 seconds to grab the generated trycloudflare.com URL
set "TUNNEL_URL="
for /L %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    if exist "cloudflared.log" (
        for /f "tokens=*" %%a in ('powershell -Command "Get-Content cloudflared.log -ErrorAction SilentlyContinue | Select-String -Pattern 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' | ForEach-Object { $_.Matches.Value } | Select-Object -First 1"') do (
            set "TUNNEL_URL=%%a"
        )
        if defined TUNNEL_URL goto TUNNEL_FOUND
    )
)

:TUNNEL_FOUND
if not defined TUNNEL_URL (
    echo.
    echo [-] Tunnel is taking longer than expected to connect.
    echo Inspect cloudflared.log for details.
    pause
    exit /b 1
)

:: Copy tunnel URL to Windows clipboard automatically
powershell -Command "Set-Clipboard -Value '!TUNNEL_URL!'" >nul 2>&1

cls
echo ==================================================================
echo   🎉 YOUR PC BACKEND IS ONLINE & CONNECTED TO THE CLOUD!
echo ==================================================================
echo.
echo   🔗 Public Tunnel URL:
echo      !TUNNEL_URL!
echo.
echo   📋 (The URL has been copied to your Windows clipboard!)
echo.
echo ==================================================================
echo   📱 HOW TO USE WITH YOUR VERCEL WEBSITE (PHONE OR ANY DEVICE):
echo ==================================================================
echo.
echo   👉 Option 1 (Instant 1-Click Link - Easiest):
echo      Open your Vercel website with ?backend= appended:
echo      https://your-site.vercel.app/?backend=!TUNNEL_URL!
echo      (The website will auto-save and connect to your PC!)
echo.
echo   👉 Option 2 (Connect from Mobile/Browser UI):
echo      Open your Vercel website on your phone, tap the "Backend"
echo      status pill at the top, and paste your Tunnel URL!
echo.
echo   👉 Option 3 (Permanent in Vercel):
echo      Set BACKEND_URL = !TUNNEL_URL! in Vercel Project Settings.
echo.
echo ==================================================================
echo   🟢 LOCAL BACKEND LOGS (Starting Flask on port 5000...):
echo   Press Ctrl+C or close this window when you want to stop hosting.
echo ==================================================================
echo.

set PORT=5000
python app.py

:: Cleanup tunnel on exit
taskkill /F /IM cloudflared.exe >nul 2>&1
pause
