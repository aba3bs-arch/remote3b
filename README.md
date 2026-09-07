# AM-CONNECT - Acceso remoto gratis para tiendas 3B

**AM-CONNECT** es tu alternativa gratis a RemotePC para ver y controlar las computadoras de tus sucursales. No hay suscripcion.

## Como abrir la app (sin Python)

1. En GitHub, abre **Actions → Build Windows executables** y descarga el artefacto `am-connect-windows`.
2. En tu PC, doble clic en **AM-CONNECT.exe**.
3. Se abre una ventana "AM-CONNECT esta abierto" y el panel en el navegador. **No cierres esa ventana.**
4. No escribas `localhost:8000` a mano: el ejecutable abre el panel solo.

En cada tienda, desde el panel pulsa **Agregar equipo / Descargar** y corre el comando. Si el artefacto incluye **AM-CONNECT-Agent.exe**, la tienda tampoco necesita Python.

## Como usarlo en las tiendas

1. Arranca el servidor y abre el panel en el navegador.
2. Crea un usuario e inicia sesion.
3. Pulsa **Agregar computadora** y nombra la sucursal (`3B7 Del Valle`, `3B6 Soli`, etc.).
4. Copia el comando de PowerShell y pegalo en la PC de esa tienda. Eso instala el agente y lo deja iniciar con Windows.
5. Cuando el icono se ponga verde, haz doble clic para ver la pantalla y usar mouse/teclado.

Solo instala el agente en equipos de 3B o con permiso explicito del dueno.

## ✨ Key Features

### 🔒 Advanced Security
- **TLS/SSL Encryption** - All communication is encrypted
- **JWT Authentication** - Secure and renewable tokens
- **2FA (Two-Factor Authentication)** - TOTP with QR codes
- **Password Hashing** - BCrypt with salt
- **Data Encryption** - Fernet for sensitive data
- **Complete Auditing** - Logging of all actions

### 🎮 Total Device Control
- 📸 **Live Screen Capture**
- ⌨️ **Real-Time Command Execution**
- 💾 **Bidirectional File Transfer**
- 🎥 **Screen Recording Video**
- 💬 **Real-Time Chat**
- 📊 **System Information**

### 📱 Multi-Device Support
- Control multiple devices simultaneously
- Unified central dashboard
- Per-device session management
- Automatic reconnection

### 🎨 Professional Interface
- Built-in web dashboard served by FastAPI
- Live screen viewer
- Remote terminal
- File manager
- Integrated chat
- Resource monitoring

## 🏗️ Architecture

```
AM-CONNECT/
├── server/                 # FastAPI Backend
│   ├── main.py            # Main server
│   ├── security.py        # Security module (TLS, JWT, 2FA)
│   ├── video_recorder.py  # Video recording
│   ├── connection_manager.py  # Connection management
│   └── models.py          # Pydantic schemas
│
├── client/                # Remote agent
│   └── agent.py           # Client that runs on devices
│
├── frontend/              # Static web dashboard
│   ├── index.html
│   └── assets/
│       ├── app.js
│       └── styles.css
│
└── generate_certs.py      # TLS certificate generator
```

## 🚀 Quick Installation

### Prerequisites
- Python 3.8+
- OpenSSL (for TLS certificates)

### Steps

1. **Clone repository**
```bash
git clone https://github.com/aba3bs-arch/remote3b.git
cd remote3b
```

2. **Setup Python environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Generate TLS certificates**
```bash
python generate_certs.py
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env if needed
```

## 📖 Usage

### Terminal 1: Start Server
```bash
source venv/bin/activate
python server/main.py
```
Server available at `http://127.0.0.1:8000`

### Terminal 2: Start Client
```bash
source venv/bin/activate
python client/agent.py
```

### Open Dashboard
Open `http://127.0.0.1:8000` in your browser.
The dashboard includes a RemotePC-style Always-ON computer list, recently accessed
stores, search, and a one-command Windows installer per store computer.
Starting a connection opens `/session` with live screen streaming and mouse/keyboard
control, plus file transfer for authorized devices.

## ☁️ Deploy on Render + Netlify

Use Render for the FastAPI/WebSocket backend and Netlify for the static dashboard.
See [DEPLOYMENT_RENDER_NETLIFY.md](DEPLOYMENT_RENDER_NETLIFY.md) for the full setup,
including `AM_CONNECT_API_BASE_URL`, Render environment variables, and the remote
agent `wss://.../ws` URL.

## 🖥️ Install agents on Windows computers

Use [INSTALL_AGENT_WINDOWS.md](INSTALL_AGENT_WINDOWS.md) for a copy/paste PowerShell
installer that configures `SERVER_URL`, `DEVICE_ID`, `DEVICE_TOKEN`, dependencies,
and optional visible startup shortcut for authorized machines.

## 🔐 Security Features

### TLS Encryption
All data in transit is encrypted with TLS 1.2+

### JWT Authentication
- **Access Token**: Valid for 30 minutes
- **Refresh Token**: Valid for 7 days
- Automatic token renewal

### 2FA (Two-Factor Authentication)
```bash
POST /api/auth/enable-2fa
GET QR code with Google Authenticator
POST /api/auth/confirm-2fa with TOTP code
```

### Password Policies
- Minimum 12 characters
- Must contain: uppercase, lowercase, numbers, and symbols
- Stored with BCrypt hash

## 📡 REST API

### Authentication
```bash
# Register user
POST /api/auth/register
{
  "username": "user",
  "email": "user@example.com",
  "password": "Secure@12345"
}

# Login
POST /api/auth/login
{
  "username": "user",
  "password": "Secure@12345",
  "totp_code": "123456"  # Optional if 2FA enabled
}
```

### Devices
```bash
# Register device
POST /api/devices/register

# List devices
GET /api/devices

# Device status
GET /api/devices/{device_id}/status
```

### Video Recording
```bash
# Start recording
POST /api/recording/start/{device_id}

# Stop recording
POST /api/recording/stop/{device_id}

# Download video
GET /api/recording/download/{device_id}
```

## 🔗 WebSocket

### Connection
```
wss://localhost:8000/ws/{device_id}?token={device_token}
```

### Message Types

**Screen Capture**
```json
{
  "type": "screen_capture",
  "image": "base64_encoded_image",
  "timestamp": "2024-01-01T12:00:00"
}
```

**Command Execution**
```json
{
  "type": "command",
  "command": "whoami",
  "command_id": "cmd_123"
}
```

**File Transfer**
```json
{
  "type": "file_upload",
  "filepath": "/home/user/file.txt",
  "content": "base64_encoded_content"
}
```

**Chat**
```json
{
  "type": "chat",
  "from": "admin",
  "message": "How are you?"
}
```

## 🎥 Video Recording

### Features
- Automatic screen recording in MP4
- Smart compression
- 30 FPS default (configurable)
- Multiple resolution support
- On-demand download

## 🔧 Advanced Configuration

### Environment Variables (.env)
```env
# Server
HOST=0.0.0.0
PORT=8000
USE_SSL=true
SECRET_KEY=change-this-in-production

# Certificates
SSL_CERT=certs/cert.pem
SSL_KEY=certs/key.pem

# Client
SERVER_URL=wss://localhost:8000
DEVICE_ID=device_001

# Video
RECORDING_FPS=30
RECORDING_QUALITY=80
```

## 📝 Usage Examples

### Register and Connect New Device

```bash
# 1. Register device on server
curl -X POST https://localhost:8000/api/devices/register \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{"device_name": "My PC", "os": "Windows"}'

# Response:
# {
#   "device_id": "device_002",
#   "device_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
# }

# 2. Configure client
export DEVICE_ID=device_002
export DEVICE_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGc...
python client/agent.py

# 3. View in control panel (https://localhost:8000/dashboard)
# Device appears as connected
```

## 🐛 Troubleshooting

### Error: "TLS certificates not found"
```bash
python generate_certs.py
```

### Error: "WebSocket connection failed"
- Verify server is running
- Check firewall settings
- Validate TLS certificate

### Error: "Invalid token"
- Token has expired, use refresh token
- POST to `/api/auth/refresh`

## 📄 License

MIT License - See LICENSE.md

## ⚠️ Legal Notice

**AM-CONNECT** is an authorized 3B remote access tool. Should only be used:

- ✅ With explicit consent of the device owner
- ✅ For legitimate administration and maintenance purposes
- ✅ In authorized corporate environments

❌ **DO NOT use for:**
- Unauthorized access
- Data theft
- Spyware or illegal surveillance
- Malicious activities

Unauthorized use can result in serious legal consequences.

---

**Made with ❤️ by aba3bs-arch**

For questions or support: [GitHub Issues](https://github.com/aba3bs-arch/remote3b/issues)
