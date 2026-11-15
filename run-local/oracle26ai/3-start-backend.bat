@echo off
title Backend - FastAPI on port 8000
rem ===================================================================
rem  Application server (middle tier). Same as typing, inside backend\:
rem      uvicorn app.main:app --reload
rem ===================================================================
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" goto noinstall

echo Backend:   http://localhost:8000
echo API docs:  http://localhost:8000/docs
echo Health:    http://localhost:8000/api/health
echo Keep this window open while using the app. Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
pause
exit /b 0

:noinstall
echo [X] Run 1-install.bat first.
pause
exit /b 1
