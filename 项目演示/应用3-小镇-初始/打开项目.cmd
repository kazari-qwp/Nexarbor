@echo off
chcp 65001 >nul
setlocal
for %%I in ("%~dp0..\..") do set "NEXARBOR_PACKAGE=%%~fI"
set "NEXARBOR_EXE=%NEXARBOR_PACKAGE%\Nexarbor.exe"
if not exist "%NEXARBOR_EXE%" set "NEXARBOR_EXE=%NEXARBOR_PACKAGE%\build\desktop\Nexarbor Workbench-win32-x64\Nexarbor.exe"
if defined NEXARBOR_DESKTOP_EXE set "NEXARBOR_EXE=%NEXARBOR_DESKTOP_EXE%"
if not exist "%NEXARBOR_EXE%" (
 echo 请在 Nexarbor 中打开此项目文件夹，或将本文件夹放入运行包的“项目演示”目录。
 pause
 exit /b 1
)
set "NEXARBOR_PYTHON=%NEXARBOR_PACKAGE%\runtime\python\python.exe"
if not exist "%NEXARBOR_PYTHON%" set "NEXARBOR_PYTHON=%NEXARBOR_PACKAGE%\.venv\Scripts\python.exe"
if exist "%~dp0准备项目.py" (
 "%NEXARBOR_PYTHON%" "%~dp0准备项目.py"
 if errorlevel 1 (pause & exit /b 1)
)
start "" "%NEXARBOR_EXE%" --project "%~dp0."
