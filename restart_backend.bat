@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Restart literature-assistant backend
echo ============================================
echo.

echo [1/5] Locating python ...
set PY=
if exist "%~dp0.venv\Scripts\python.exe" set PY=%~dp0.venv\Scripts\python.exe
if "%PY%"=="" (
  where python >nul 2>&1
  if not errorlevel 1 set PY=python
)
if "%PY%"=="" (
  echo       [ERROR] python not found.
  echo       Install Python 3.10+ and add it to PATH, or create a .venv here.
  pause
  exit /b 1
)
echo       %PY%

echo.
echo [2/5] Trying to kill whatever listens on 5000 ...
set KILLED=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
  echo       killing PID %%a
  taskkill /F /PID %%a >nul 2>&1
  set KILLED=1
)
if "%KILLED%"=="0" echo       (nothing was listening - fine)

echo.
echo [3/5] Waiting for the port to be released ...
timeout /t 3 /nobreak >nul

set BUSY=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do set BUSY=1

if "%BUSY%"=="1" goto USE5001

echo.
echo [4/5] Port 5000 is free - starting backend on 5000 ...
start "lit-backend-5000" cmd /k "%PY% -m uvicorn backend.main:app --host 127.0.0.1 --port 5000 --reload"
goto DONE

:USE5001
echo.
echo       Port 5000 is STILL occupied (old process cannot be killed).
echo       Starting on 5001 instead - the page auto-detects the port.
echo.
echo [4/5] Starting backend on 5001 ...
start "lit-backend-5001" cmd /k "%PY% -m uvicorn backend.main:app --host 127.0.0.1 --port 5001 --reload"

:DONE
echo.
echo [5/5] A new window has been opened.
echo       Wait until it prints:  Uvicorn running on http://127.0.0.1:500x
echo       Then open demo/index.html and press Ctrl+F5.
echo.
pause
