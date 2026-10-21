@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-assistant.ps1"
if errorlevel 1 (
  echo Stop failed. See the error above and logs folder.
  pause
  exit /b 1
)
