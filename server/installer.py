#!/usr/bin/env python3
"""Generate a one-click Windows installer for a store computer."""

from __future__ import annotations


def escape_ps(value: str) -> str:
    return (value or "").replace("`", "``").replace('"', '`"').replace("$", "`$")


def build_windows_installer(
    api_url: str,
    ws_url: str,
    device_id: str,
    device_token: str,
    device_name: str,
) -> str:
    api_url = api_url.rstrip("/")
    ws_url = ws_url.rstrip("/")
    return f"""# AM-CONNECT Always-ON agent installer
# Use only on computers owned by 3B or with explicit owner authorization.
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ApiUrl = "{escape_ps(api_url)}"
$WsUrl = "{escape_ps(ws_url)}"
$DeviceId = "{escape_ps(device_id)}"
$DeviceToken = "{escape_ps(device_token)}"
$DeviceName = "{escape_ps(device_name)}"
$InstallDir = Join-Path $env:LOCALAPPDATA "AM-CONNECT\\agent"

Write-Host "Instalando AM-CONNECT Always-ON en $DeviceName..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

@"
SERVER_URL=$WsUrl
DEVICE_ID=$DeviceId
DEVICE_TOKEN=$DeviceToken
DEVICE_NAME=$DeviceName
AM_CONNECT_UPLOAD_DIR=client/downloads
"@ | Set-Content -Path (Join-Path $InstallDir ".env") -Encoding UTF8

$ExePath = Join-Path $InstallDir "AM-CONNECT-Agent.exe"
$usedExe = $false
try {{
    Write-Host "Descargando AM-CONNECT-Agent.exe..."
    Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/download/agent.exe" -OutFile $ExePath
    if (Test-Path $ExePath) {{
        $usedExe = $true
    }}
}} catch {{
    Write-Host "No hay ejecutable en el servidor; se instalara el agente Python." -ForegroundColor Yellow
}}

$StartScript = Join-Path $InstallDir "start-agent.ps1"
if ($usedExe) {{
@"
Set-Location `"$InstallDir`"
Start-Process -FilePath `"$ExePath`" -WorkingDirectory `"$InstallDir`"
"@ | Set-Content -Path $StartScript -Encoding UTF8
    $shortcutTarget = $ExePath
    $shortcutArgs = ""
}} else {{
    function Get-Python {{
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($python) {{ return $python.Source }}
        $python3 = Get-Command python3 -ErrorAction SilentlyContinue
        if ($python3) {{ return $python3.Source }}
        throw "No hay AM-CONNECT-Agent.exe ni Python. Compila el .exe o instala Python."
    }}
    $Python = Get-Python
    New-Item -ItemType Directory -Path (Join-Path $InstallDir "client") -Force | Out-Null
    Invoke-WebRequest -Uri "$ApiUrl/install/agent.py" -OutFile (Join-Path $InstallDir "client\\agent.py")
    Set-Location $InstallDir
    & $Python -m venv .venv
    $VenvPython = Join-Path $InstallDir ".venv\\Scripts\\python.exe"
    $VenvPip = Join-Path $InstallDir ".venv\\Scripts\\pip.exe"
    & $VenvPython -m pip install --upgrade pip
    & $VenvPip install aiohttp psutil mss pillow python-dotenv pynput
@"
Set-Location `"$InstallDir`"
& `"$VenvPython`" `"client\\agent.py`"
"@ | Set-Content -Path $StartScript -Encoding UTF8
    $shortcutTarget = "powershell.exe"
    $shortcutArgs = "-WindowStyle Minimized -ExecutionPolicy Bypass -File `"$StartScript`""
}}

$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "AM-CONNECT Agent.lnk"
$Wsh = New-Object -ComObject WScript.Shell
$Shortcut = $Wsh.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $shortcutTarget
$Shortcut.Arguments = $shortcutArgs
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "AM-CONNECT Always-ON agent"
$Shortcut.Save()

Write-Host ""
Write-Host "Instalacion completa. El agente se iniciara con Windows." -ForegroundColor Green
Write-Host "Iniciando ahora..."
if ($usedExe) {{
    Start-Process -FilePath $ExePath -WorkingDirectory $InstallDir
}} else {{
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$StartScript`"" -WorkingDirectory $InstallDir
}}
"""
