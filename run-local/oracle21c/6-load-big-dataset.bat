@echo off
title Load the big dataset (50,000 customers)
rem ===================================================================
rem  OPTIONAL: replaces the demo data with the large dataset in
rem  database\dataset\*.csv (50,000 customers, ~89,000 orders).
rem  Run 2-setup-database.bat first. To go back to the small demo data,
rem  run 5-reset-demo-data.bat.
rem ===================================================================
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" goto noinstall

echo This REPLACES all current data in the INVENTORY schema with the large dataset
echo (50,000 customers, about 89,000 orders). It takes about 2-5 minutes.
choice /c YN /m "Continue"
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" load_dataset.py --yes
pause
exit /b 0

:noinstall
echo [X] Run 1-install.bat first.
pause
exit /b 1
