@echo off
chcp 65001 >nul
set "NEXARBOR_ROOT=%~dp0..\.."
"%NEXARBOR_ROOT%\.venv-runtime\Scripts\python.exe" "%~dp0准备项目.py"
if errorlevel 1 exit /b 1
start "" "%NEXARBOR_ROOT%rontends\desktop
ode_modules\electron\dist\electron.exe" "%NEXARBOR_ROOT%rontends\desktop" --project "%~dp0."
