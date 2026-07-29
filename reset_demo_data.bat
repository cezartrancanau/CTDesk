@echo off
setlocal
title Reset CTDesk Demo Data
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run run_ctdesk.bat once before resetting the demo.
    pause
    exit /b 1
)

echo This replaces the local demo database with fresh sample data.
choice /C YN /M "Continue"
if errorlevel 2 exit /b 0

".venv\Scripts\python.exe" database.py
if errorlevel 1 (
    echo Reset failed.
) else (
    echo Demo data reset successfully.
)
pause
endlocal
