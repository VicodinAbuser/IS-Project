@echo off
title Install - one time
rem ===================================================================
rem  ONE-TIME: installs the Python and Node.js packages the app needs.
rem  Requires Python 3.10+ (with "Add python.exe to PATH" ticked) and Node.js 18+.
rem ===================================================================
cd /d "%~dp0.."

echo === Checking Python and Node.js ===
where python >nul 2>nul
if errorlevel 1 goto nopython
where npm >nul 2>nul
if errorlevel 1 goto nonode
python --version
call node --version

echo.
echo === Backend: creating the Python environment and installing packages ===
cd backend
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo.
echo === Website: installing packages - this can take a few minutes ===
cd ..\frontend
call npm install
if errorlevel 1 goto fail

echo.
echo ==============================================================
echo  Install finished. Next: double-click 2-setup-database.bat
echo ==============================================================
pause
exit /b 0

:nopython
echo [X] Python was not found.
echo     Install Python 3.10 or newer from python.org and tick "Add python.exe to PATH".
echo     Then close this window and run 1-install.bat again.
pause
exit /b 1

:nonode
echo [X] Node.js was not found. Install the LTS version from nodejs.org,
echo     then close this window and run 1-install.bat again.
pause
exit /b 1

:fail
echo.
echo [X] Something went wrong - read the messages above.
pause
exit /b 1
