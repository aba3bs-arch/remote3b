# Instalar el agente AM-CONNECT en Windows

Usa esto en cada computadora de tienda que quieras controlar. Solo en PCs de 3B o con permiso del dueno.

## Lo mas simple (recomendado)

1. En el panel AM-CONNECT inicia sesion.
2. Pulsa **Agregar equipo / Descargar agente**.
3. Escribe el nombre de la tienda, por ejemplo `3B7 Del Valle`.
4. Copia el comando PowerShell y pegalo **en la PC de la tienda**.

Ese comando descarga el agente desde tu propio servidor, lo deja Always-ON en el Inicio de Windows y lo arranca.

Python 3.10+ debe estar instalado en la tienda, con **Add python.exe to PATH**.

## Comando de ejemplo

```powershell
$Api="https://TU-SERVIDOR"
$Id="dev_abc123"
$Tok="TOKEN"
$Name="3B7 Del Valle"
irm "$Api/install/windows.ps1" -OutFile "$env:TEMP\am-connect-install.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\am-connect-install.ps1" `
  -ServerUrl $Api `
  -DeviceId $Id `
  -DeviceToken $Tok `
  -DeviceName $Name
```

## Donde queda instalado

```txt
%LOCALAPPDATA%\AM-CONNECT\agent
```

Inicio manual:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\AM-CONNECT\agent\start-agent.ps1"
```

## Importante

Solo instala el agente en computadoras de 3B o donde tengas autorizacion explicita.
