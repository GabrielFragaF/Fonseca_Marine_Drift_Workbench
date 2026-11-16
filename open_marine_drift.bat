@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0tools\windows_entry.py"
) else (
  python "%~dp0tools\windows_entry.py"
)
if errorlevel 1 pause
