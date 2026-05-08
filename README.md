# AM-Connect

AM-Connect es una base de aplicacion para soporte remoto autorizado. Incluye login con usuario y contrasena, panel web para ver equipos en linea, enrolamiento explicito de agentes, ejecucion de comandos, capturas de pantalla y transferencia de archivos.

> Usa AM-Connect solo en PCs propias o administradas con consentimiento explicito. El agente es visible por consola, no se instala como persistencia y no intenta ocultarse.

## Arquitectura

```text
server/
  main.py                FastAPI, REST, WebSocket y panel web
  store.py               Persistencia SQLite
  security.py            Hash de contrasenas, JWT y secretos de equipos
  connection_manager.py  Solicitudes/respuestas hacia agentes conectados
  static/index.html      Panel web embebido
client/
  agent.py               Agente visible para la PC remota autorizada
```

## Instalacion

### Windows rapido

En Cursor, abre la terminal con **Terminal > New Terminal** y pega:

```powershell
.\scripts\start_am_connect_windows.bat
```

Tambien puedes abrir el archivo `scripts/start_am_connect_windows.bat` con doble click desde el Explorador de Windows. El script crea el entorno virtual, instala dependencias y arranca el servidor.

Cuando termine de iniciar, abre:

```text
http://localhost:8000
```

### Linux/macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y cambia `SECRET_KEY` antes de usarlo fuera de desarrollo.

## Ejecutar el servidor

```bash
source venv/bin/activate
python server/main.py
```

Abre el panel en:

```text
http://localhost:8000
```

La primera vez usa **Crear primer usuario**. Despues entra con **Iniciar sesion**.

## Registrar una PC remota

1. En el panel, crea un equipo con un nombre descriptivo.
2. Copia el `device_id` y `device_secret` que se muestran una sola vez.
3. En la PC autorizada, ejecuta el agente visible:

```bash
source venv/bin/activate
AM_CONNECT_SERVER_URL=ws://localhost:8000 \
AM_CONNECT_DEVICE_ID=dev_xxx \
AM_CONNECT_DEVICE_SECRET=secret_xxx \
python client/agent.py
```

Cuando el agente este conectado, el equipo aparecera en linea en el panel.

## Funciones actuales

- Autenticacion JWT con usuario y contrasena.
- Creacion del primer administrador y bloqueo de registros posteriores por defecto.
- SQLite persistente para usuarios, equipos y auditoria basica.
- Equipos en linea mediante WebSocket autenticado con secreto de dispositivo.
- Ejecucion de comandos autorizada desde el panel.
- Captura de pantalla bajo permisos del sistema operativo.
- Listado, descarga y subida de archivos.
- Flags para deshabilitar comandos, archivos o capturas desde `.env`.

## Configuracion importante

```env
SECRET_KEY=change-this-long-random-secret-before-production
DATABASE_URL=sqlite:///./am_connect.db
ENABLE_COMMAND_EXECUTION=true
ENABLE_FILE_TRANSFER=true
ENABLE_SCREENSHOTS=true
```

Para usar HTTPS/WSS, genera certificados y activa:

```env
USE_SSL=true
SSL_CERT=certs/cert.pem
SSL_KEY=certs/key.pem
```

## API principal

- `POST /api/auth/bootstrap` crea el primer usuario.
- `POST /api/auth/login` inicia sesion.
- `POST /api/devices` registra un nuevo equipo.
- `GET /api/devices` lista equipos y estado online.
- `POST /api/devices/{device_id}/command` ejecuta un comando.
- `POST /api/devices/{device_id}/screenshot` solicita una captura.
- `GET /api/devices/{device_id}/files?path=...` lista archivos.
- `GET /api/devices/{device_id}/files/download?path=...` descarga un archivo en base64.
- `POST /api/devices/{device_id}/files/upload` sube un archivo.

## Siguientes mejoras recomendadas

- Control remoto grafico interactivo con eventos de teclado/mouse y streaming de pantalla.
- 2FA para administradores.
- Roles/permisos por equipo.
- Empaquetado del agente para Windows/macOS/Linux con instalador visible.
- Almacenamiento externo para archivos grandes.
