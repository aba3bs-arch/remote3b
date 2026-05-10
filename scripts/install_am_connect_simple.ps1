<#
AM-CONNECT simple Windows agent installer.

Use only on 3B-owned computers or computers with explicit authorization.

Example:
powershell -ExecutionPolicy Bypass -File .\install_am_connect_simple.ps1 `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -DeviceId "device_001" `
  -DeviceToken "TOKEN_FROM_AM_CONNECT"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,

    [Parameter(Mandatory = $true)]
    [string]$DeviceId,

    [Parameter(Mandatory = $true)]
    [string]$DeviceToken,

    [string]$DeviceName = $env:COMPUTERNAME
)

$ErrorActionPreference = "Stop"

function Normalize-ServerUrl {
    param([string]$Url)

    $Url = $Url.Trim().TrimEnd("/")
    $Url = $Url -replace "^https://", "wss://"
    $Url = $Url -replace "^http://", "ws://"

    if ($Url -notmatch "^wss?://") {
        throw "ServerUrl debe iniciar con https://, http://, wss:// o ws://"
    }

    if ($Url -notmatch "/ws$") {
        $Url = "$Url/ws"
    }

    return $Url
}

function Get-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return $python3.Source
    }

    throw "Python no esta instalado. Instala Python 3.10+ y vuelve a correr este script."
}

$InstallDir = "$env:LOCALAPPDATA\AM-CONNECT\agent"
$ZipUrl = "https://github.com/aba3bs-arch/remote3b/archive/refs/heads/cursor/remote-access-dashboard-3dae.zip"
$ZipFile = "$env:TEMP\am-connect-agent.zip"
$ExtractDir = "$env:TEMP\am-connect-agent"
$WsUrl = Normalize-ServerUrl $ServerUrl
$Python = Get-Python

Write-Host "Instalando AM-CONNECT Agent..." -ForegroundColor Cyan
Write-Host "Equipo: $DeviceName"
Write-Host "Servidor: $WsUrl"
Write-Host "Destino: $InstallDir"

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}

if (Test-Path $ExtractDir) {
    Remove-Item -Recurse -Force $ExtractDir
}

Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipFile
Expand-Archive -Path $ZipFile -DestinationPath $ExtractDir -Force

$SourceDir = Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1
if (-not $SourceDir) {
    throw "No se pudo extraer AM-CONNECT."
}

New-Item -ItemType Directory -Path (Split-Path $InstallDir -Parent) -Force | Out-Null
Copy-Item -Path $SourceDir.FullName -Destination $InstallDir -Recurse

Set-Location $InstallDir

& $Python -m venv .venv
$VenvPython = "$InstallDir\.venv\Scripts\python.exe"
$VenvPip = "$InstallDir\.venv\Scripts\pip.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPip install aiohttp psutil mss pillow python-dotenv

@"
SERVER_URL=$WsUrl
DEVICE_ID=$DeviceId
DEVICE_TOKEN=$DeviceToken
DEVICE_NAME=$DeviceName
AM_CONNECT_UPLOAD_DIR=client/downloads
"@ | Set-Content -Path "$InstallDir\.env" -Encoding UTF8

@"
Set-Location "$InstallDir"
& "$VenvPython" "client\agent.py"
"@ | Set-Content -Path "$InstallDir\start-agent.ps1" -Encoding UTF8

Write-Host ""
Write-Host "Instalacion completa." -ForegroundColor Green
Write-Host "Para iniciar el agente:"
Write-Host "powershell -ExecutionPolicy Bypass -File `"$InstallDir\start-agent.ps1`""
Write-Host ""
Write-Host "Iniciando agente ahora..."

Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$InstallDir\start-agent.ps1`"" -WorkingDirectory $InstallDir
