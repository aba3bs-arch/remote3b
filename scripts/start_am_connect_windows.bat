@echo off
setlocal

cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_am_connect_windows.ps1"

if errorlevel 1 (
  echo.
  echo AM-Connect no pudo iniciar. Revisa el mensaje de error de arriba.
  pause
  exit /b 1
)
