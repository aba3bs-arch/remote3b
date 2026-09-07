<#
AM-CONNECT Always-ON installer for store computers.

Downloads the agent from YOUR AM-CONNECT server (no paid RemotePC account).
Use only on computers owned by 3B or with explicit owner authorization.

Example from the dashboard "Agregar equipo" dialog:
powershell -ExecutionPolicy Bypass -File .\install_from_server.ps1 `
  -ServerUrl "https://TU-SERVIDOR" `
  -DeviceId "dev_abc123" `
  -DeviceToken "eyJ..." `
  -DeviceName "3B7 Del Valle"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,

    [Parameter(Mandatory = $true)]
    [string]$DeviceId,

    [Parameter(Mandatory = $true)]
    [string]$DeviceToken,

    [string]$DeviceName = $env:COMPUTERNAME,

    [string]$InstallDir = "$env:LOCALAPPDATA\AM-CONNECT\agent",

    [switch]$NoStartupShortcut,

    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

function Normalize-ApiUrl {
    param([string]$Url)
    $Url = $Url.Trim().TrimEnd("/")
    $Url = $Url -replace "^wss://", "https://"
    $Url = $Url -replace "^ws://", "http://"
    $Url = $Url -replace "/ws$", ""
    if ($Url -notmatch "^https?://") {
        throw "ServerUrl debe iniciar con https://, http://, wss:// o ws://"
    }
    return $Url
}

function Normalize-WsUrl {
    param([string]$Url)
    $Url = (Normalize-ApiUrl $Url)
    $Url = $Url -replace "^https://", "wss://"
    $Url = $Url -replace "^http://", "ws://"
    return "$Url/ws"
}

function Get-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) { return $python3.Source }
    throw "Python no esta instalado. Instala Python 3.10+ desde python.org (marca 'Add python.exe to PATH') y vuelve a correr este script."
}

$ApiUrl = Normalize-ApiUrl $ServerUrl
$WsUrl = Normalize-WsUrl $ServerUrl
$Python = Get-Python

Write-Host "Instalando AM-CONNECT Agent (Always-ON)..." -ForegroundColor Cyan
Write-Host "Equipo: $DeviceName"
Write-Host "Servidor: $WsUrl"
Write-Host "Device ID: $DeviceId"
Write-Host "Destino: $InstallDir"

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

Write-Host "Descargando agente desde el servidor..."
Invoke-WebRequest -Uri "$ApiUrl/install/agent.py" -OutFile "$InstallDir\agent.py"
Invoke-WebRequest -Uri "$ApiUrl/install/agent-requirements.txt" -OutFile "$InstallDir\requirements.txt"

Set-Location $InstallDir
& $Python -m venv .venv
$VenvPython = "$InstallDir\.venv\Scripts\python.exe"
$VenvPip = "$InstallDir\.venv\Scripts\pip.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPip install -r "$InstallDir\requirements.txt"

@"
SERVER_URL=$WsUrl
DEVICE_ID=$DeviceId
DEVICE_TOKEN=$DeviceToken
DEVICE_NAME=$DeviceName
AM_CONNECT_UPLOAD_DIR=$InstallDir\downloads
"@ | Set-Content -Path "$InstallDir\.env" -Encoding UTF8

New-Item -ItemType Directory -Path "$InstallDir\downloads" -Force | Out-Null

@"
`$ErrorActionPreference = "Stop"
Set-Location "$InstallDir"
& "$VenvPython" "agent.py"
"@ | Set-Content -Path "$InstallDir\start-agent.ps1" -Encoding UTF8

if (-not $NoStartupShortcut) {
    $startupFolder = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupFolder "AM-CONNECT Agent.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$InstallDir\start-agent.ps1`""
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "AM-CONNECT authorized remote agent"
    $shortcut.Save()
    Write-Host "Acceso Always-ON creado en Inicio de Windows." -ForegroundColor Green
}

Write-Host ""
Write-Host "Instalacion completa." -ForegroundColor Green
Write-Host "Inicio manual:"
Write-Host "powershell -ExecutionPolicy Bypass -File `"$InstallDir\start-agent.ps1`""

if (-not $SkipStart) {
    Write-Host "Iniciando agente ahora..."
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$InstallDir\start-agent.ps1`"" -WorkingDirectory $InstallDir
}
