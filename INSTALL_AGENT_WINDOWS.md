# Install AM-CONNECT Agent on Windows

The easiest path is from the AM-CONNECT dashboard:

1. Sign in.
2. Click **Agregar computadora** and name the store PC.
3. Copy the generated PowerShell command.
4. On the store computer, paste it into PowerShell.

That command downloads a pre-filled installer from `/install/windows.ps1`, installs the
agent under `%LOCALAPPDATA%\AM-CONNECT\agent`, starts it, and adds a visible Startup
shortcut named `AM-CONNECT Agent`.

## Manual installer

Use this on each authorized remote computer if you already have a Device ID and token.

From the AM-CONNECT admin panel/API, get:

- Backend URL, for example:

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
  -Uri "https://raw.githubusercontent.com/aba3bs-arch/remote3b/main/scripts/install_agent_windows.ps1" `
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
  -Uri "https://raw.githubusercontent.com/aba3bs-arch/remote3b/main/scripts/install_am_connect_simple.ps1" `
  -OutFile $installer

powershell -ExecutionPolicy Bypass -File $installer `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -AdminUsername "YOUR_ADMIN_USER" `
  -AdminPassword "YOUR_ADMIN_PASSWORD"
```

The simple installer logs in, registers the computer, receives its `DeviceId`
and `DeviceToken`, writes `.env`, installs dependencies, and starts the agent.

If you already have a device token, manual mode still works:

```powershell
powershell -ExecutionPolicy Bypass -File $installer `
  -ServerUrl "https://YOUR-RENDER-SERVICE.onrender.com" `
  -DeviceId "device_001" `
  -DeviceToken "TOKEN_FROM_AM_CONNECT"
```
