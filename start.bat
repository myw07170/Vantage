@echo off
rem Vantage - one-click start. Double-click, or run from a terminal.
rem Any extra arguments go straight through, e.g.  start.bat -Reload -Show
setlocal

rem When double-clicked, Explorer runs us as `cmd.exe /c "..."`. Pause at the
rem end in that case so the window does not vanish before you can read it.
set "KEEPOPEN="
echo.%cmdcmdline% | findstr /i /c:"/c " >nul && set "KEEPOPEN=1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\vantage.ps1" -Action start %*
set "RC=%ERRORLEVEL%"

if defined KEEPOPEN pause
exit /b %RC%
