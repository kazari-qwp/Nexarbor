@echo off
chcp 65001 >nul
set "NEXARBOR_ROOT=%~dp0..\.."
if exist "%NEXARBOR_ROOT%\Nexarbor.exe" (
  if exist "%~dp0准备项目.py" (
    "%NEXARBOR_ROOT%\runtime\python\python.exe" -B -X utf8 "%~dp0准备项目.py"
    if errorlevel 1 exit /b 1
  )
  start "" "%NEXARBOR_ROOT%\Nexarbor.exe" --project "%~dp0."
) else (
  if exist "%~dp0准备项目.py" (
    "%NEXARBOR_ROOT%\.venv-runtime\Scripts\python.exe" -B -X utf8 "%~dp0准备项目.py"
    if errorlevel 1 exit /b 1
  )
  start "" "%NEXARBOR_ROOT%\frontends\desktop\node_modules\electron\dist\electron.exe" "%NEXARBOR_ROOT%\frontends\desktop" --project "%~dp0."
)
