param(
    [string]$ServerUrl,
    [string]$DeviceId,
    [string]$DeviceSecret,
    [bool]$VerifySsl = $true
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ConfigDir = Join-Path $env:APPDATA "AM-Connect"
$ConfigPath = Join-Path $ConfigDir "agent-config.json"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "AM-Connect Agent.lnk"
$RunnerPath = Join-Path $RepoRoot "scripts\run_am_connect_agent_windows.ps1"

Write-Host "== Instalar AM-Connect acceso desatendido visible ==" -ForegroundColor Cyan
Write-Host "Este modo inicia el agente automaticamente cuando este usuario inicia sesion." -ForegroundColor Yellow
Write-Host "No es invisible: se abrira una ventana visible del agente y puede cerrarse." -ForegroundColor Yellow
Write-Host ""

if (!$ServerUrl) {
    $ServerUrl = Read-Host "URL del servidor WebSocket (ejemplo: ws://192.168.1.50:8000)"
}
if (!$DeviceId) {
    $DeviceId = Read-Host "Device ID del panel (ejemplo: dev_xxx)"
}
if (!$DeviceSecret) {
    $DeviceSecret = Read-Host "Device secret del panel"
}

if (!$ServerUrl -or !$DeviceId -or !$DeviceSecret) {
    Write-Host "ServerUrl, DeviceId y DeviceSecret son obligatorios." -ForegroundColor Red
    exit 1
}

if (!(Test-Path $RunnerPath)) {
    Write-Host "No se encontro $RunnerPath" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null

$Config = [ordered]@{
    server_url = $ServerUrl
    device_id = $DeviceId
    device_secret = $DeviceSecret
    verify_ssl = $VerifySsl
    allow_commands = $true
    allow_file_transfer = $true
    allow_screenshots = $true
    allow_remote_control = $true
    installed_at = (Get-Date).ToString("o")
}

$Config | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8

$PowerShellPath = (Get-Command powershell.exe).Source
$Shortcut = New-Object -ComObject WScript.Shell
$Link = $Shortcut.CreateShortcut($ShortcutPath)
$Link.TargetPath = $PowerShellPath
$Link.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerPath`""
$Link.WorkingDirectory = $RepoRoot
$Link.WindowStyle = 1
$Link.Description = "AM-Connect Agent visible"
$Link.Save()

Write-Host ""
Write-Host "Listo. El agente se iniciara automaticamente al iniciar sesion de Windows." -ForegroundColor Green
Write-Host "Configuracion: $ConfigPath" -ForegroundColor Green
Write-Host "Acceso directo: $ShortcutPath" -ForegroundColor Green
Write-Host ""
Write-Host "Para probar ahora:" -ForegroundColor Cyan
Write-Host ".\scripts\run_am_connect_agent_windows.ps1"
Write-Host ""
Write-Host "Para desinstalar:" -ForegroundColor Cyan
Write-Host ".\scripts\uninstall_unattended_agent_windows.ps1"
