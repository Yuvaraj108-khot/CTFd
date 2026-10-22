@echo off
title CTFd + Cloudflare Tunnel Launcher
echo ========================================================
echo  Starting CTFd and Cloudflare Tunnel...
echo ========================================================

cd /d "%~dp0"

echo 1. Starting CTFd Server on port 4000...
start "CTFd Server" cmd /k ".\.venv\Scripts\python.exe serve.py --port 4000"

echo 2. Waiting 3 seconds for server to initialize...
timeout /t 3 /nobreak >nul

echo 3. Launching Cloudflare Tunnel...
echo Look for your https://*.trycloudflare.com link below:
echo ========================================================
cloudflared tunnel --url http://127.0.0.1:4000
pause
