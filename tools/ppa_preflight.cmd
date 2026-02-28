@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ppa_preflight.ps1"
exit /b %ERRORLEVEL%
