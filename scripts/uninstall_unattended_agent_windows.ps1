param(
    [switch]$RemoveConfig
)

$ErrorActionPreference = "Stop"

$ConfigDir = Join-Path $env:APPDATA "AM-Connect"
$ConfigPath = Join-Path $ConfigDir "agent-config.json"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "AM-Connect Agent.lnk"

Write-Host "== Desinstalar AM-Connect acceso desatendido ==" -ForegroundColor Cyan

if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "Eliminado auto-inicio: $ShortcutPath" -ForegroundColor Green
} else {
    Write-Host "No habia acceso directo de auto-inicio." -ForegroundColor Yellow
}

if ($RemoveConfig) {
    if (Test-Path $ConfigPath) {
        Remove-Item $ConfigPath -Force
        Write-Host "Eliminada configuracion: $ConfigPath" -ForegroundColor Green
    }
    if ((Test-Path $ConfigDir) -and -not (Get-ChildItem $ConfigDir -Force)) {
        Remove-Item $ConfigDir -Force
    }
} else {
    Write-Host "La configuracion se conserva en: $ConfigPath" -ForegroundColor Yellow
    Write-Host "Usa -RemoveConfig si quieres borrar tambien el device secret guardado." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Si el agente esta corriendo, cierra su ventana o presiona Ctrl+C." -ForegroundColor Cyan
