@echo off
chcp 65001 >nul
set "NEXARBOR_ROOT=%~dp0..\.."
start "" "%NEXARBOR_ROOT%\frontends\desktop\node_modules\electron\dist\electron.exe" "%NEXARBOR_ROOT%\frontends\desktop" --project "%~dp0."
