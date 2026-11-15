@echo off
title Database setup - one time
rem ===================================================================
rem  ONE-TIME: creates the INVENTORY user, tables, PL/SQL package,
rem  trigger, views and demo data in Oracle 26ai Free on this laptop.
rem  Oracle must be installed and running.
rem ===================================================================
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" goto noinstall

echo This sets up the project database in Oracle (localhost:1521/FREEPDB1).
echo It will ask for the SYSTEM password you chose when installing Oracle.
echo WARNING: if the project tables already exist, their data is replaced with fresh demo data.
echo.
".venv\Scripts\python.exe" setup_db.py --create-user
pause
exit /b 0

:noinstall
echo [X] Run 1-install.bat first.
pause
exit /b 1
