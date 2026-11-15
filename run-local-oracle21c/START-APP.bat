@echo off
title Start Inventory App
rem ===================================================================
rem  EVERY TIME: opens the backend and the website in two windows,
rem  then opens the browser. Oracle runs as a Windows service already.
rem ===================================================================
start "Backend - FastAPI on port 8000" /D "%~dp0." cmd /k 3-start-backend.bat
start "Website - Angular on port 4200" /D "%~dp0." cmd /k 4-start-website.bat

echo Starting the backend and the website in two new windows...
echo The browser opens in about 30 seconds. If the page is blank, wait a little and refresh.
timeout /t 30 /nobreak >nul
start "" http://localhost:4200
