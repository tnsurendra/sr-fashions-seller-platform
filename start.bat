@echo off
setlocal
title SR Fashions
set "PATH=%ProgramFiles%\nodejs;%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
if /I "%~1"=="--backend" goto backend
if /I "%~1"=="--frontend" goto frontend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Startup failed. Review the error above.
if /I not "%~1"=="--no-pause" pause
exit /b %RESULT%
:backend
cd /d "%~dp0backend"
".venv312\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
exit /b %ERRORLEVEL%
:frontend
cd /d "%~dp0frontend"
call npm.cmd run dev
exit /b %ERRORLEVEL%
