@echo off
chcp 65001 > nul
title FCC Catalyst Platform
echo Starting FCC Catalyst Platform (FastAPI)...
echo Please wait, browser will open automatically.
echo.
echo To stop the server, press Ctrl+C or close this window.
echo.

cd /d d:\cc_test

REM Kill any existing process on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

REM Open browser after a short delay
start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:8000"

python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
pause
