@echo off
rem Vantage - one-click stop. Kills both services and frees their ports.
setlocal

set "KEEPOPEN="
echo.%cmdcmdline% | findstr /i /c:"/c " >nul && set "KEEPOPEN=1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\vantage.ps1" -Action stop %*
set "RC=%ERRORLEVEL%"

if defined KEEPOPEN pause
exit /b %RC%
