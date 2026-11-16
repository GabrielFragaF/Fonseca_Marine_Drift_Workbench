@echo off
setlocal
set "MDW_CHECK_OUTPUT=%TEMP%\MarineDriftCheck-%RANDOM%-%RANDOM%"
set "QT_QPA_PLATFORM=offscreen"
echo Checking bundled Python, OpenDrift, landmask, NetCDF, GUI and exports...
start "" /wait "%~dp0Marine Drift Workbench\Marine Drift Workbench.exe" --self-test "%MDW_CHECK_OUTPUT%"
if errorlevel 1 (echo Check failed. See the report below.) else (echo Check completed.)
echo Report: %MDW_CHECK_OUTPUT%\installation-check.json
if exist "%MDW_CHECK_OUTPUT%\installation-check.json" type "%MDW_CHECK_OUTPUT%\installation-check.json"
pause
