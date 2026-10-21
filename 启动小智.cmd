@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-assistant.ps1"
if errorlevel 1 (
  echo Startup failed. See the error above and logs folder.
  pause
  exit /b 1
)
