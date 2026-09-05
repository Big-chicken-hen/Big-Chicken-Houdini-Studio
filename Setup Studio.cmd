@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
set "studioExit=%ERRORLEVEL%"
if not "%studioExit%"=="0" echo Studio setup did not finish. Review the message above.
pause
exit /b %studioExit%
