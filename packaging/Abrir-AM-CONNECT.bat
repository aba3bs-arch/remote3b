@echo off
setlocal
cd /d "%~dp0"

if exist "AM-CONNECT.exe" (
  start "" "AM-CONNECT.exe"
  exit /b 0
)

if exist "..\dist\AM-CONNECT.exe" (
  start "" "..\dist\AM-CONNECT.exe"
  exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
  echo No esta AM-CONNECT.exe ni Python.
  echo Descarga el ejecutable desde GitHub Actions: artefacto am-connect-windows
  pause
  exit /b 1
)

set USE_SSL=false
set HOST=127.0.0.1
set PORT=8000
set PUBLIC_URL=http://127.0.0.1:8000
python "%~dp0..\desktop\am_connect_app.py"
