@echo off
title Update to the latest version
rem ===================================================================
rem  Downloads the latest project code from GitHub and updates THIS folder.
rem  Kept as they are: backend\.venv (installed Python packages), backend\.env
rem  (your settings), frontend\node_modules, ngrok-domain.txt.
rem  Your Oracle data is not touched.
rem ===================================================================
rem This file is replaced during the update, so run a copy of it from the TEMP folder.
if /i "%~1"=="--run" goto run
copy /y "%~f0" "%TEMP%\ims-update.bat" >nul
"%TEMP%\ims-update.bat" --run "%~dp0."

:run
set "TARGET=%~f2"
set "ZIP=%TEMP%\ims-latest.zip"
set "UNZIP=%TEMP%\ims-latest"
set "SRC=%TEMP%\ims-latest\IS-Project-main\run-local\{{FOLDER}}"
echo This updates the code in:
echo   %TARGET%
echo Close the Backend / Website / ngrok windows first if they are open.
echo.
choice /c YN /m "Continue"
if errorlevel 2 exit /b 0

echo.
echo === Downloading the latest version from GitHub ===
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/VicodinAbuser/IS-Project/archive/refs/heads/main.zip' -OutFile $env:ZIP; if (Test-Path $env:UNZIP) { Remove-Item -Recurse -Force $env:UNZIP }; Expand-Archive -Path $env:ZIP -DestinationPath $env:UNZIP"
if errorlevel 1 goto fail
if not exist "%SRC%\backend\app\main.py" goto fail

echo === Copying the new code ===
rem /MIR makes each folder an exact copy (old files are removed); /XD and /XF are left alone.
robocopy "%SRC%\backend" "%TARGET%\backend" /MIR /XD .venv __pycache__ .pytest_cache /XF .env *.db /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto fail
robocopy "%SRC%\frontend" "%TARGET%\frontend" /MIR /XD node_modules .angular dist /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto fail
robocopy "%SRC%\database" "%TARGET%\database" /MIR /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto fail
robocopy "%SRC%" "%TARGET%" *.bat *.md /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto fail

if not exist "%TARGET%\backend\.venv\Scripts\python.exe" goto noinstall
echo === Updating the Python packages ===
"%TARGET%\backend\.venv\Scripts\python.exe" -m pip install -q -r "%TARGET%\backend\requirements.txt"
if errorlevel 1 goto fail
echo === Updating the website packages ===
pushd "%TARGET%\frontend"
call npm install --no-audit --no-fund
set "NPMERR=%errorlevel%"
popd
if not "%NPMERR%"=="0" goto fail

echo.
echo ==============================================================
echo  Update finished.
echo  If the new version changed the DATABASE (see the README on
echo  GitHub), also double-click 2-setup-database.bat, and then
echo  6-load-big-dataset.bat if you use the large data set.
echo ==============================================================
pause
exit /b 0

:noinstall
echo.
echo Code updated. Now double-click 1-install.bat to install the packages.
pause
exit /b 0

:fail
echo.
echo [X] The update did not finish - read the messages above. Your folder may be partly updated;
echo     run UPDATE.bat again when the problem is fixed (e.g. no internet connection).
pause
exit /b 1
