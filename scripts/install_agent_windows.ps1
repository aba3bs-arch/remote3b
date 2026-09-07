<#
.SYNOPSIS
Installs the AM-CONNECT authorized remote agent on a Windows computer.

.DESCRIPTION
This script is intended for computers owned by 3B or explicitly authorized by
their owner. It installs the visible AM-CONNECT agent files, writes the device
configuration, and can optionally start the agent or add a visible Startup
shortcut for unattended authorized support.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\install_agent_windows.ps1 `
  -ServerUrl "wss://am-connect-api.onrender.com/ws" `
  -DeviceId "device_001" `
  -DeviceToken "eyJ..." `
  -StartNow
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,

    [Parameter(Mandatory = $true)]
    [string]$DeviceId,

    [Parameter(Mandatory = $true)]
    [string]$DeviceToken,

    [string]$DeviceName = $env:COMPUTERNAME,

    [string]$InstallDir = "$env:LOCALAPPDATA\AM-CONNECT\agent",

    [string]$RepoUrl = "https://github.com/aba3bs-arch/remote3b.git",

    [string]$Branch = "main",

    [switch]$StartNow,

    [switch]$CreateStartupShortcut,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[AM-CONNECT] $Message" -ForegroundColor Cyan
}

function Convert-ToWebSocketUrl {
    param([string]$Value)

    $normalized = $Value.Trim().TrimEnd("/")
    if ($normalized -match "^https://") {
        $normalized = $normalized -replace "^https://", "wss://"
    } elseif ($normalized -match "^http://") {
        $normalized = $normalized -replace "^http://", "ws://"
    }

    if ($normalized -notmatch "^wss?://") {
        throw "ServerUrl must start with http://, https://, ws://, or wss://"
    }

    if ($normalized -notmatch "/ws$") {
        $normalized = "$normalized/ws"
    }

    return $normalized
}

function Get-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return $python3.Source
    }

    throw "Python is not installed or not available in PATH. Install Python 3.10+ from https://www.python.org/downloads/windows/ and retry."
}

function Install-Repository {
    param(
        [string]$Destination,
        [string]$Remote,
        [string]$GitBranch
    )

    if ((Test-Path $Destination) -and $Force) {
        Write-Step "Removing existing install directory because -Force was provided"
        Remove-Item -Recurse -Force $Destination
    }

    if (Test-Path "$Destination\.git") {
        Write-Step "Updating existing repository"
        git -C $Destination fetch origin $GitBranch
        git -C $Destination checkout $GitBranch
        git -C $Destination pull origin $GitBranch
        return
    }

    if (Test-Path $Destination) {
        Write-Step "Install directory already exists; reusing it"
        return
    }

    New-Item -ItemType Directory -Path (Split-Path $Destination -Parent) -Force | Out-Null

    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        Write-Step "Cloning AM-CONNECT repository"
        git clone -b $GitBranch $Remote $Destination
        return
    }

    Write-Step "Git not found; downloading repository zip"
    $tempRoot = Join-Path $env:TEMP ("am-connect-" + [Guid]::NewGuid().ToString("N"))
    $zipPath = "$tempRoot.zip"
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $zipUrl = "https://github.com/aba3bs-arch/remote3b/archive/refs/heads/$GitBranch.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $tempRoot
    $expanded = Get-ChildItem -Path $tempRoot -Directory | Select-Object -First 1
    if (-not $expanded) {
        throw "Could not extract repository archive."
    }
    Copy-Item -Path $expanded.FullName -Destination $Destination -Recurse
    Remove-Item -Recurse -Force $tempRoot, $zipPath
}

$wsUrl = Convert-ToWebSocketUrl -Value $ServerUrl
$pythonCommand = Get-PythonCommand
$installPath = [System.IO.Path]::GetFullPath($InstallDir)

Write-Step "Installing authorized agent for device '$DeviceName'"
Write-Step "Install path: $installPath"
Write-Step "Server URL: $wsUrl"

Install-Repository -Destination $installPath -Remote $RepoUrl -GitBranch $Branch

Set-Location $installPath

Write-Step "Creating Python virtual environment"
& $pythonCommand -m venv .venv

$venvPython = Join-Path $installPath ".venv\Scripts\python.exe"
$venvPip = Join-Path $installPath ".venv\Scripts\pip.exe"

Write-Step "Installing agent dependencies"
& $venvPython -m pip install --upgrade pip
& $venvPip install aiohttp psutil mss pillow python-dotenv pynput

Write-Step "Writing agent configuration"
$envContent = @"
SERVER_URL=$wsUrl
DEVICE_ID=$DeviceId
DEVICE_TOKEN=$DeviceToken
DEVICE_NAME=$DeviceName
AM_CONNECT_UPLOAD_DIR=client/downloads
"@
$envContent | Set-Content -Path (Join-Path $installPath ".env") -Encoding UTF8

$startScript = @"
`$ErrorActionPreference = "Stop"
Set-Location "$installPath"
& "$venvPython" "client\agent.py"
"@
$startScriptPath = Join-Path $installPath "start-agent.ps1"
$startScript | Set-Content -Path $startScriptPath -Encoding UTF8

if ($CreateStartupShortcut) {
    Write-Step "Creating visible Startup shortcut"
    $startupFolder = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupFolder "AM-CONNECT Agent.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$startScriptPath`""
    $shortcut.WorkingDirectory = $installPath
    $shortcut.Description = "AM-CONNECT authorized remote agent"
    $shortcut.Save()
}

Write-Step "Installation complete"
Write-Host ""
Write-Host "To start the agent manually, run:" -ForegroundColor Green
Write-Host "powershell -ExecutionPolicy Bypass -File `"$startScriptPath`""
Write-Host ""

if ($StartNow) {
    Write-Step "Starting AM-CONNECT agent in a new PowerShell window"
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$startScriptPath`"" -WorkingDirectory $installPath
}
