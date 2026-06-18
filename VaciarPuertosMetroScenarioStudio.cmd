@echo off
setlocal
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\clear-metro-scenario-studio-ports.ps1" %*
endlocal
