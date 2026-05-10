# Install AM-CONNECT Agent on Windows

Use this on each authorized remote computer you want to connect to AM-CONNECT.

## What you need first

From the AM-CONNECT admin panel/API, get:

- Render backend URL, for example:

```txt
https://am-connect-api.onrender.com
```

- Device ID, for example:

```txt
device_001
```

- Device token, for example:

```txt
eyJ...
```

## Option A: Download and run the installer script

Open **PowerShell** on the remote computer and run:

```powershell
$installer = "$env:TEMP\install_agent_windows.ps1"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/aba3bs-arch/remote3b/cursor/remote-access-dashboard-3dae/scripts/install_agent_windows.ps1" `
  -OutFile $installer

powershell -ExecutionPolicy Bypass -File $installer `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -DeviceId "device_001" `
  -DeviceToken "TOKEN_FROM_AM_CONNECT" `
  -StartNow
```

You can also pass the WebSocket URL directly:

```powershell
-ServerUrl "wss://YOUR-RENDER-SERVICE.onrender.com/ws"
```

The installer accepts both formats.

## Optional: start automatically when Windows logs in

Add:

```powershell
-CreateStartupShortcut
```

Example:

```powershell
powershell -ExecutionPolicy Bypass -File $installer `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -DeviceId "device_001" `
  -DeviceToken "TOKEN_FROM_AM_CONNECT" `
  -StartNow `
  -CreateStartupShortcut
```

This creates a visible Startup shortcut named:

```txt
AM-CONNECT Agent
```

## Where it installs

Default install path:

```txt
%LOCALAPPDATA%\AM-CONNECT\agent
```

Generated files:

```txt
.env
start-agent.ps1
.venv\
```

Manual start command:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\AM-CONNECT\agent\start-agent.ps1"
```

## Important

Only install the agent on computers owned by 3B or where you have explicit authorization from the owner.

## Simplest installer

For the shortest installation flow, use:

```txt
scripts/install_am_connect_simple.ps1
```

Download and run it:

```powershell
$installer = "$env:TEMP\install_am_connect_simple.ps1"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/aba3bs-arch/remote3b/cursor/remote-access-dashboard-3dae/scripts/install_am_connect_simple.ps1" `
  -OutFile $installer

powershell -ExecutionPolicy Bypass -File $installer `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -DeviceId "device_001" `
  -DeviceToken "TOKEN_FROM_AM_CONNECT"
```
