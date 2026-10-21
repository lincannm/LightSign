@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
pause >nul
endlocal & exit /b %EXIT_CODE%
