@echo off
title Website - Angular on port 4200
rem ===================================================================
rem  Presentation tier: serves the Angular website at http://localhost:4200
rem  Same as typing, inside frontend\:   npm start
rem ===================================================================
cd /d "%~dp0frontend"
if not exist "node_modules" goto noinstall

echo Website: http://localhost:4200  (ready when you see "Local: http://localhost:4200/")
echo Keep this window open while using the app. Press Ctrl+C to stop.
echo.
call npm start
pause
exit /b 0

:noinstall
echo [X] Run 1-install.bat first.
pause
exit /b 1
