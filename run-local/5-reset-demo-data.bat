@echo off
title Reset demo data
rem ===================================================================
rem  OPTIONAL, e.g. just before the presentation: rebuilds the tables,
rem  package and views and reloads fresh demo data. Deletes all changes!
rem ===================================================================
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" goto noinstall

echo This DELETES all current data in the INVENTORY schema and loads fresh demo data.
choice /c YN /m "Continue"
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" setup_db.py
pause
exit /b 0

:noinstall
echo [X] Run 1-install.bat first.
pause
exit /b 1
