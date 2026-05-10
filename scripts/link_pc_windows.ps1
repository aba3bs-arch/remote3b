param(
    [string]$ServerUrl,
    [string]$Code
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"

Write-Host "== Enlazar esta PC con AM-Connect ==" -ForegroundColor Cyan

if (!$ServerUrl) {
    $ServerUrl = Read-Host "URL del servidor (ejemplo: ws://192.168.1.50:8000)"
}
if (!$Code) {
    $Code = Read-Host "Codigo de enlace"
}

if (!$ServerUrl -or !$Code) {
    Write-Host "URL del servidor y codigo son obligatorios." -ForegroundColor Red
    exit 1
}

if (!(Test-Path $VenvPython)) {
    Write-Host "Creando entorno virtual..." -ForegroundColor Yellow
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -m venv (Join-Path $RepoRoot "venv")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $RepoRoot "venv")
    } else {
        Write-Host "Python no esta instalado o no esta en PATH." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Instalando dependencias..." -ForegroundColor Yellow
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")

$env:AM_CONNECT_SERVER_URL = $ServerUrl
$env:AM_CONNECT_LINK_CODE = $Code.Replace("-", "")

Write-Host ""
Write-Host "Enlazando y conectando esta PC..." -ForegroundColor Green
Write-Host "Deja esta ventana abierta mientras quieras soporte remoto." -ForegroundColor Yellow
Write-Host ""

& $VenvPython (Join-Path $RepoRoot "client\agent.py")
