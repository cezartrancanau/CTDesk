@echo off
setlocal
title CTDesk - Junior IT Support Demo
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing requirements...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :error

if not exist "ctdesk.db" (
    echo Creating demo database...
    ".venv\Scripts\python.exe" database.py
    if errorlevel 1 goto :error
)

echo.
echo CTDesk is starting at http://127.0.0.1:5000
echo Press Ctrl+C to stop.
".venv\Scripts\python.exe" app.py
goto :end

:error
echo.
echo Setup could not be completed. Confirm that Python 3 is installed.
pause

:end
endlocal
