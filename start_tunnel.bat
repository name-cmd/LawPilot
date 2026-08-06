@echo off
title LawTrust - Tunnel Launcher
cd /d "%~dp0"

echo ============================================
echo   LawTrust - Public Tunnel Launcher
echo   Exposes local port 6006 to the internet
echo   Prerequisite: start_server.bat must be running
echo ============================================
echo.

:: ============ Prefer cpolar (domestic, no VPN needed) ============
where cpolar >nul 2>&1
if not errorlevel 1 (
    echo cpolar detected. Starting tunnel...
    echo.
    echo Check the cpolar window for the public URL
    echo Format: https://xxxx.cpolar.cn
    echo Send this URL to testers so they can access the system.
    echo.
    echo Tip: if cpolar asks for login, register at https://www.cpolar.com once.
    echo.
    start "cpolar-tunnel" cpolar http 6006
    echo cpolar started! Public URL is shown in the cpolar window.
    goto :end
)

:: ============ Fallback: ngrok ============
where ngrok >nul 2>&1
if not errorlevel 1 (
    echo ngrok detected. Starting tunnel...
    echo Check the ngrok window for the Forwarding URL (https://xxx.ngrok-free.app)
    echo Send this URL to testers so they can access the system.
    echo.
    start "ngrok-tunnel" ngrok http 6006
    goto :end
)

:: ============ Neither installed: show setup guide ============
echo Neither cpolar nor ngrok found. Install one of them:
echo.
echo ---------------------------------------------------
echo Quick start cpolar (recommended, ~2 minutes):
echo   1. Download and install Windows version from
echo      https://www.cpolar.com/download
echo   2. Open cpolar, register / login
echo   3. Run:  cpolar http 6006
echo ---------------------------------------------------
echo.
echo Quick start ngrok (alternative):
echo   1. Download Windows version from https://ngrok.com/download
echo   2. Register, copy your authtoken, then run:
echo      ngrok config add-authtoken YOUR_TOKEN
echo   3. Start tunnel:  ngrok http 6006
echo ---------------------------------------------------
echo.
echo After installation, double-click this script again
echo or simply run:  cpolar http 6006

:end
pause
