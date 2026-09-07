# Deploy AM-CONNECT on Render + Netlify

This setup uses:

- **Render** for the FastAPI backend, REST API, and WebSocket agent endpoint.
- **Netlify** for the static AM-CONNECT dashboard and session UI.

The remote agent connects outbound to Render, so computers on different networks do not need inbound ports opened.

## 1. Deploy the backend on Render

Create a new Render **Blueprint** from this repository or create a Web Service manually.

### Blueprint

Use `render.yaml` from the repository.

### Manual service settings

- Runtime: Python
- Build command:

```bash
pip install -r requirements-render.txt
```

- Start command:

```bash
python server/main.py
```

### Render environment variables

Set these values:

```env
HOST=0.0.0.0
USE_SSL=false
SECRET_KEY=<generate-a-long-random-secret>
TOTP_ISSUER=AM-CONNECT
AM_CONNECT_UPLOAD_DIR=client/downloads
ALLOWED_ORIGINS=https://YOUR-NETLIFY-SITE.netlify.app
```

For the first deploy, if you do not have the Netlify URL yet, set:

```env
ALLOWED_ORIGINS=http://localhost:8000
```

After Netlify is deployed, update `ALLOWED_ORIGINS` to the Netlify URL and redeploy Render.

Render will provide a backend URL like:

```txt
https://am-connect-api.onrender.com
```

The agent WebSocket URL will be:

```txt
wss://am-connect-api.onrender.com/ws
```

## 2. Deploy the frontend on Netlify

Create a Netlify site from this repository.

Netlify reads `netlify.toml` automatically.

### Netlify build settings

- Base directory: repository root
- Build command:

```bash
python3 scripts/write_frontend_config.py
```

- Publish directory:

```txt
frontend
```

### Netlify environment variables

Set:

```env
AM_CONNECT_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Do not include a trailing slash.

Netlify will write `frontend/assets/config.js` during build so the dashboard calls Render instead of same-origin `/api`.

## 3. Create admin user and register devices

Open:

```txt
https://YOUR-NETLIFY-SITE.netlify.app/dashboard
```

Use the visual authentication dialog to:

1. Create an admin user.
2. Log in.
3. Register or load authorized devices.

## 4. Run an agent on a remote computer

On the remote computer, install the client dependencies and set the Render WebSocket URL:

```powershell
git clone https://github.com/aba3bs-arch/remote3b.git am-connect
cd am-connect

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install aiohttp psutil mss pillow python-dotenv

$env:SERVER_URL="wss://YOUR-RENDER-SERVICE.onrender.com/ws"
$env:DEVICE_ID="device_001"
$env:DEVICE_TOKEN="TOKEN_FROM_DEVICE_REGISTRATION"
$env:DEVICE_NAME=$env:COMPUTERNAME

python client/agent.py
```

## Notes

- Render free instances can sleep. For reliable remote access, use a paid Render instance or a VPS.
- Current user/device/session state is in memory. If Render restarts, users and registered devices are lost until persistent database storage is added.
- Only run agents on computers you own or where you have explicit authorization.
