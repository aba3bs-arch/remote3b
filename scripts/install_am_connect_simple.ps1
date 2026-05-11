<#
AM-CONNECT simple Windows agent installer.

Use only on 3B-owned computers or computers with explicit authorization.

Example:
powershell -ExecutionPolicy Bypass -File .\install_am_connect_simple.ps1 `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -AdminUsername "admin" `
  -AdminPassword "your-password"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,

    [string]$AdminUsername,

    [string]$AdminPassword,

    [string]$DeviceId,

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

function Encode-QueryValue {
    param([string]$Value)
    return [System.Uri]::EscapeDataString($Value)
}

function Invoke-AmConnectPost {
    param(
        [string]$Url,
        [hashtable]$Query,
        [hashtable]$Headers = @{}
    )

    $pairs = @()
    foreach ($key in $Query.Keys) {
        if ($null -ne $Query[$key] -and $Query[$key] -ne "") {
            $pairs += "$(Encode-QueryValue $key)=$(Encode-QueryValue ([string]$Query[$key]))"
        }
    }

    $requestUrl = $Url
    if ($pairs.Count -gt 0) {
        $requestUrl = "$Url?$($pairs -join '&')"
    }

    return Invoke-RestMethod -Method Post -Uri $requestUrl -Headers $Headers
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
$ApiUrl = Normalize-ApiUrl $ServerUrl
$Python = Get-Python

if (-not $DeviceToken) {
    if (-not $AdminUsername) {
        $AdminUsername = Read-Host "Usuario admin AM-CONNECT"
    }

    if (-not $AdminPassword) {
        $securePassword = Read-Host "Contrasena admin AM-CONNECT" -AsSecureString
        $AdminPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        )
    }

    Write-Host "Registrando esta computadora en AM-CONNECT..." -ForegroundColor Cyan
    $login = Invoke-AmConnectPost `
        -Url "$ApiUrl/api/auth/login" `
        -Query @{ username = $AdminUsername; password = $AdminPassword }

    $accessToken = $login.access_token
    if (-not $accessToken) {
        throw "No se pudo obtener access_token del servidor."
    }

    $registration = Invoke-AmConnectPost `
        -Url "$ApiUrl/api/devices/register" `
        -Query @{ device_name = $DeviceName; os = "Windows" } `
        -Headers @{ Authorization = "Bearer $accessToken" }

    $DeviceId = $registration.device_id
    $DeviceToken = $registration.device_token

    if (-not $DeviceId -or -not $DeviceToken) {
        throw "El servidor no devolvio DeviceId/DeviceToken."
    }
}

if (-not $DeviceId -or -not $DeviceToken) {
    throw "Falta DeviceId o DeviceToken. Usa credenciales admin o provee ambos valores manualmente."
}

Write-Host "Instalando AM-CONNECT Agent..." -ForegroundColor Cyan
Write-Host "Equipo: $DeviceName"
Write-Host "Servidor: $WsUrl"
Write-Host "Device ID: $DeviceId"
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
