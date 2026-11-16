@echo off
title Online - backend + ngrok tunnel
rem ===================================================================
rem  EVERY TIME you want your group to use the Vercel website:
rem  starts the backend (window 1) and the ngrok tunnel (this window),
rem  so https://<your domain>.ngrok-free.app reaches this laptop.
rem  Oracle runs as a Windows service already. Close both windows to go offline.
rem ===================================================================
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" goto noinstall
where ngrok >nul 2>nul
if errorlevel 1 goto nongrok

set "DOMAIN="
if exist "ngrok-domain.txt" set /p DOMAIN=<"ngrok-domain.txt"
if defined DOMAIN goto havedomain
echo One-time question: your free ngrok static domain
echo (ngrok dashboard - Domains), for example  your-name.ngrok-free.app
set /p DOMAIN=ngrok domain: 
if not defined DOMAIN goto nodomain
set "DOMAIN=%DOMAIN:https://=%"
set "DOMAIN=%DOMAIN:http://=%"
set "DOMAIN=%DOMAIN:/=%"
set "DOMAIN=%DOMAIN: =%"
>"ngrok-domain.txt" (echo %DOMAIN%)
echo Saved in ngrok-domain.txt - you won't be asked again.

:havedomain
rem A private login-token secret, created once (the default one is public on GitHub).
"backend\.venv\Scripts\python.exe" -c "import secrets,pathlib;p=pathlib.Path('backend/.env');t=p.read_text() if p.exists() else '';import sys;sys.exit(0) if 'JWT_SECRET=' in t else p.write_text(t+('\n' if t and not t.endswith('\n') else '')+'JWT_SECRET='+secrets.token_hex(32)+'\n')"

rem The backend is shared with START-APP.bat: start it only if it isn't running yet.
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if not errorlevel 1 goto backendup
start "Backend - FastAPI on port 8000" /D "%~dp0." cmd /k 3-start-backend.bat
echo Starting the backend...
timeout /t 8 /nobreak >nul
goto tunnel
:backendup
echo Backend already running on port 8000 - using it.
:tunnel
echo.
echo ==============================================================
echo  Backend is public at:  https://%DOMAIN%
echo  Check it:              https://%DOMAIN%/api/health
echo  Your group opens the Vercel link (e.g. https://is-project-xxxx.vercel.app)
echo  Keep BOTH windows open. Press Ctrl+C here to go offline.
echo ==============================================================
echo.
ngrok http --url=%DOMAIN% 8000
pause
exit /b 0

:noinstall
echo [X] Run 1-install.bat and 2-setup-database.bat first.
pause
exit /b 1

:nongrok
echo [X] ngrok is not installed (or this window was open before you installed it).
echo     1. Sign up free at https://ngrok.com
echo     2. Follow "Setup ^& Installation" on the ngrok dashboard (install + add-authtoken)
echo     3. Claim your free static domain under Domains
echo     Then close this window and double-click START-ONLINE.bat again.
pause
exit /b 1

:nodomain
echo [X] No domain typed. Run START-ONLINE.bat again.
pause
exit /b 1
