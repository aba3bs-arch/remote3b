$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ConfigDir = Join-Path $env:APPDATA "AM-Connect"
$ConfigPath = Join-Path $ConfigDir "agent-config.json"
$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"

Write-Host "== AM-Connect Agent ==" -ForegroundColor Cyan

if (!(Test-Path $ConfigPath)) {
    Write-Host "No se encontro configuracion del agente: $ConfigPath" -ForegroundColor Red
    Write-Host "Ejecuta primero scripts\install_unattended_agent_windows.ps1" -ForegroundColor Yellow
    exit 1
}

$Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

if (!(Test-Path $VenvPython)) {
    Write-Host "No se encontro el entorno virtual. Creandolo..." -ForegroundColor Yellow
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -m venv (Join-Path $RepoRoot "venv")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $RepoRoot "venv")
    } else {
        Write-Host "Python no esta instalado o no esta en PATH." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Verificando dependencias..." -ForegroundColor Yellow
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")

$env:AM_CONNECT_SERVER_URL = $Config.server_url
$env:AM_CONNECT_DEVICE_ID = $Config.device_id
$env:AM_CONNECT_DEVICE_SECRET = $Config.device_secret
$env:AM_CONNECT_VERIFY_SSL = if ($Config.verify_ssl) { "true" } else { "false" }
$env:AM_CONNECT_ALLOW_COMMANDS = if ($Config.allow_commands) { "true" } else { "false" }
$env:AM_CONNECT_ALLOW_FILE_TRANSFER = if ($Config.allow_file_transfer) { "true" } else { "false" }
$env:AM_CONNECT_ALLOW_SCREENSHOTS = if ($Config.allow_screenshots) { "true" } else { "false" }
$env:AM_CONNECT_ALLOW_REMOTE_CONTROL = if ($Config.allow_remote_control) { "true" } else { "false" }

Write-Host ""
Write-Host "AM-Connect desatendido visible esta activo." -ForegroundColor Green
Write-Host "Equipo: $($Config.device_id)" -ForegroundColor Green
Write-Host "Servidor: $($Config.server_url)" -ForegroundColor Green
Write-Host "Cierra esta ventana para detener el acceso remoto." -ForegroundColor Yellow
Write-Host ""

& $VenvPython (Join-Path $RepoRoot "client\agent.py")
