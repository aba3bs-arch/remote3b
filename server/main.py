#!/usr/bin/env python3
"""
AM-CONNECT Server - authorized remote access backend
Handles multiple device connections via WebSocket with TLS encryption and JWT authentication
"""

import os
import json
import asyncio
import logging
import secrets
import base64
from datetime import datetime
from typing import Dict, Optional, Set
from pathlib import Path

from fastapi import Body, FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
from dotenv import load_dotenv

from connection_manager import ConnectionManager
from security import SecurityManager
from store import AppStore

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AM-CONNECT Server",
    description="Authorized remote access for 3B with TLS, 2FA and video recording",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        'ALLOWED_ORIGINS',
        'http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000'
    ).split(','),
    allow_credentials=True,
    allow_methods=["*"],
    expose_headers=["*"],
    allow_headers=["*"],
)

# Initialize managers
connection_manager = ConnectionManager()
security_manager = SecurityManager()
store = AppStore()

# Store connected devices
connected_devices: Dict[str, dict] = {}
latest_screenshots: Dict[str, dict] = {}
file_transfers: Dict[str, dict] = {}
audit_events = []
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "frontend"
ASSETS_DIR = DASHBOARD_DIR / "assets"
SCRIPTS_DIR = BASE_DIR / "scripts"
CLIENT_DIR = BASE_DIR / "client"


def reset_app_state(db_path: Optional[os.PathLike] = None) -> None:
    """Reset runtime state. Used by tests and local bootstraps."""
    global store
    connected_devices.clear()
    latest_screenshots.clear()
    file_transfers.clear()
    audit_events.clear()
    connection_manager.active_connections.clear()
    connection_manager.connection_metadata.clear()
    connection_manager.operator_connections.clear()
    store = AppStore(db_path) if db_path else AppStore()
    security_manager.reset(store)
    security_manager.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    connected_devices.update(store.load_devices())


def bootstrap_admin() -> None:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@3b.local")
    if not username or not password:
        return
    if username in security_manager.users:
        return
    try:
        security_manager.register_user(username, email, password)
        logger.info("Bootstrap admin user created: %s", username)
    except ValueError as exc:
        logger.warning("Bootstrap admin not created: %s", exc)


reset_app_state()
bootstrap_admin()

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


class FileUploadPayload(BaseModel):
    """Payload for uploading a file to an authorized remote device."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


async def _json_or_query(request: Request, **query_values) -> dict:
    data = {key: value for key, value in query_values.items() if value not in (None, "")}
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            for key, value in body.items():
                if value not in (None, ""):
                    data[key] = value
    return data


def _persist_device(device_id: str) -> None:
    device = connected_devices.get(device_id)
    if device:
        store.save_device(device_id, device)


def _authorization_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return authorization.replace('Bearer ', '')


def _current_user_payload(authorization: Optional[str]) -> dict:
    try:
        payload = security_manager.verify_token(_authorization_token(authorization))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.get('type') != 'access':
        raise HTTPException(status_code=403, detail="Access token required")
    return payload


def _current_user_id(authorization: Optional[str]) -> str:
    return _current_user_payload(authorization)['sub']


def _require_device_access(device_id: str, authorization: Optional[str]) -> str:
    user_id = _current_user_id(authorization)
    if device_id not in connected_devices:
        raise HTTPException(status_code=404, detail="Device not found")

    if connected_devices[device_id]['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Device is not assigned to this user")
    return user_id


def _record_audit(action: str, user_id: str, device_id: Optional[str] = None, details: Optional[dict] = None) -> None:
    audit_events.append({
        "action": action,
        "user_id": user_id,
        "device_id": device_id,
        "details": details or {},
        "timestamp": datetime.now().isoformat(),
    })

    # Keep the in-memory audit list bounded for long-running development sessions.
    del audit_events[:-100]


# ===== HEALTH CHECK =====
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "connected_devices": len(connected_devices),
        "version": "1.0.0"
    }


# ===== DASHBOARD =====
@app.get("/")
async def dashboard_home():
    """Serve the web dashboard."""
    index_file = DASHBOARD_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard frontend not found")
    return FileResponse(index_file)


@app.get("/dashboard")
async def dashboard():
    """Serve the web dashboard from a dedicated route."""
    return await dashboard_home()


@app.get("/session")
async def remote_session():
    """Serve the remote session viewer shell."""
    session_file = DASHBOARD_DIR / "session.html"
    if not session_file.exists():
        raise HTTPException(status_code=404, detail="Session frontend not found")
    return FileResponse(session_file)


# ===== AUTHENTICATION ENDPOINTS =====
@app.post("/api/auth/register")
async def register(
    request: Request,
    username: str = None,
    email: str = None,
    password: str = None
):
    """Register a new user"""
    data = await _json_or_query(request, username=username, email=email, password=password)
    try:
        user = security_manager.register_user(
            data.get("username", ""),
            data.get("email", ""),
            data.get("password", "")
        )
        return {
            "status": "success",
            "message": "User registered successfully",
            "user_id": user['id'],
            "username": user['username']
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def login(
    request: Request,
    username: str = None,
    password: str = None,
    totp_code: str = None
):
    """Login user"""
    data = await _json_or_query(
        request,
        username=username,
        password=password,
        totp_code=totp_code
    )
    try:
        user, tokens = security_manager.login_user(
            data.get("username", ""),
            data.get("password", ""),
            data.get("totp_code")
        )
        return {
            "status": "success",
            "message": "Login successful",
            "access_token": tokens['access_token'],
            "refresh_token": tokens['refresh_token'],
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "two_factor_enabled": user.get('two_factor_enabled', False)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/auth/refresh")
async def refresh_token(request: Request, refresh_token: str = None):
    """Renew an access token."""
    data = await _json_or_query(request, refresh_token=refresh_token)
    try:
        tokens = security_manager.refresh_access_token(data.get("refresh_token", ""))
        return {"status": "success", **tokens}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/auth/enable-2fa")
async def enable_2fa(user_id: str):
    """Enable 2FA for user"""
    try:
        secret, qr_code = security_manager.enable_2fa(user_id)
        return {
            "status": "success",
            "message": "2FA enabled",
            "secret": secret,
            "qr_code": qr_code
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/confirm-2fa")
async def confirm_2fa(user_id: str, totp_code: str):
    """Confirm 2FA setup"""
    try:
        security_manager.confirm_2fa(user_id, totp_code)
        return {
            "status": "success",
            "message": "2FA confirmed successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== DEVICE ENDPOINTS =====
@app.post("/api/devices/register")
async def register_device(
    request: Request,
    device_name: str = None,
    os: str = None,
    authorization: str = Header(None)
):
    """Register a new device"""
    try:
        user_id = _current_user_id(authorization)
        data = await _json_or_query(request, device_name=device_name, os=os)
        device_name = (data.get("device_name") or "").strip()
        os_name = (data.get("os") or "Windows").strip() or "Windows"
        if not device_name:
            raise HTTPException(status_code=400, detail="device_name is required")
        
        device_id = f"dev_{secrets.token_hex(6)}"
        device_token = security_manager.create_device_token(device_id, user_id)
        
        connected_devices[device_id] = {
            "device_name": device_name,
            "os": os_name,
            "user_id": user_id,
            "is_online": False,
            "created_at": datetime.now().isoformat(),
            "last_seen": None
        }
        _persist_device(device_id)
        
        logger.info(f"Device registered: {device_id}")
        _record_audit("device_registered", user_id, device_id, {"device_name": device_name, "os": os_name})
        
        return {
            "status": "success",
            "device_id": device_id,
            "device_token": device_token,
            "device_name": device_name,
            "os": os_name,
            "message": "Device registered successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: str, authorization: str = Header(None)):
    """Remove an authorized store computer from this account."""
    user_id = _require_device_access(device_id, authorization)
    connection_manager.disconnect(device_id)
    connected_devices.pop(device_id, None)
    latest_screenshots.pop(device_id, None)
    store.delete_device(device_id)
    _record_audit("device_removed", user_id, device_id)
    return {"status": "success", "message": "Device removed", "device_id": device_id}


@app.get("/api/devices")
async def list_devices(authorization: str = Header(None)):
    """List all devices"""
    try:
        user_id = _current_user_id(authorization)
        
        devices = [
            {
                "device_id": dev_id,
                **device_info,
                "is_online": dev_id in connection_manager.active_connections,
                "in_session": connection_manager.operator_count(dev_id) > 0,
            }
            for dev_id, device_info in connected_devices.items()
            if device_info['user_id'] == user_id
        ]
        
        return {
            "status": "success",
            "devices": devices,
            "total": len(devices)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/devices/{device_id}/status")
async def device_status(device_id: str, authorization: str = Header(None)):
    """Get device status"""
    try:
        _require_device_access(device_id, authorization)
        
        device = connected_devices[device_id]
        
        return {
            "status": "success",
            "device_id": device_id,
            "device_name": device['device_name'],
            "os": device['os'],
            "is_online": device_id in connection_manager.active_connections,
            "created_at": device['created_at'],
            "last_seen": device['last_seen']
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device status: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ===== WEBSOCKET ENDPOINT =====
@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str, token: Optional[str] = None):
    """
    WebSocket endpoint for device communication
    Handles real-time communication between control panel and devices
    """
    try:
        # Verify device exists
        if device_id not in connected_devices:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            device_payload = security_manager.verify_token(token or "")
            if device_payload.get('type') != 'device' or device_payload.get('sub') != device_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Accept connection
        await connection_manager.connect(websocket, device_id)
        connected_devices[device_id]['is_online'] = True
        connected_devices[device_id]['last_seen'] = datetime.now().isoformat()
        _persist_device(device_id)
        
        logger.info(f"Device connected: {device_id}")
        
        online_message = {
            "type": "device_online",
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        }
        await connection_manager.send_to_operators(device_id, online_message)
        if connection_manager.operator_count(device_id) > 0:
            await connection_manager.send_to(device_id, {"type": "start_stream"})
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get('type')
                
                if msg_type == 'screen_capture':
                    snapshot = {
                        "device_id": device_id,
                        "image": data.get('image'),
                        "width": data.get('width'),
                        "height": data.get('height'),
                        "screen_width": data.get('screen_width') or data.get('width'),
                        "screen_height": data.get('screen_height') or data.get('height'),
                        "timestamp": data.get('timestamp') or datetime.now().isoformat()
                    }
                    latest_screenshots[device_id] = snapshot
                    await connection_manager.send_to_operators(device_id, {
                        "type": "screen_capture",
                        **snapshot
                    })
                
                elif msg_type == 'command_response':
                    target = data.get('target')
                    if target:
                        await connection_manager.send_to(target, data)
                    await connection_manager.send_to_operators(device_id, data)
                
                elif msg_type == 'chat':
                    await connection_manager.send_to_operators(device_id, data)
                
                elif msg_type in {'file_transfer', 'system_info', 'pong', 'input_ack'}:
                    if msg_type == 'file_transfer':
                        file_id = data.get('file_id') or data.get('upload_id')
                        if file_id:
                            file_transfers[file_id] = {
                                **data,
                                "device_id": device_id,
                                "received_at": datetime.now().isoformat()
                            }
                    await connection_manager.send_to_operators(device_id, {
                        **data,
                        "device_id": device_id
                    })
                
                logger.debug(f"Message from {device_id}: {msg_type}")
                
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                continue
    
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id)
        if device_id in connected_devices:
            connected_devices[device_id]['is_online'] = False
            connected_devices[device_id]['last_seen'] = datetime.now().isoformat()
            _persist_device(device_id)
        
        logger.info(f"Device disconnected: {device_id}")
        await connection_manager.send_to_operators(device_id, {
            "type": "device_offline",
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"WebSocket error for {device_id}: {e}")
        connection_manager.disconnect(device_id)
        if device_id in connected_devices:
            connected_devices[device_id]['is_online'] = False
            _persist_device(device_id)


@app.websocket("/ws/operator/{device_id}")
async def operator_websocket(websocket: WebSocket, device_id: str, token: Optional[str] = None):
    """Operator/viewer websocket used by the remote session page."""
    try:
        payload = security_manager.verify_token(token or "")
        if payload.get("type") != "access":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if device_id not in connected_devices:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if connected_devices[device_id]["user_id"] != payload.get("sub"):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await connection_manager.connect_operator(websocket, device_id)
    is_online = device_id in connection_manager.active_connections
    await websocket.send_json({
        "type": "session_ready",
        "device_id": device_id,
        "device_name": connected_devices[device_id]["device_name"],
        "is_online": is_online,
    })
    latest = latest_screenshots.get(device_id)
    if latest:
        await websocket.send_json({"type": "screen_capture", **latest})
    if is_online:
        await connection_manager.send_to(device_id, {"type": "start_stream"})
    else:
        await websocket.send_json({
            "type": "device_offline",
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type in {"input", "execute_command", "screenshot", "start_stream", "stop_stream", "chat"}:
                sent = await connection_manager.send_to(device_id, data)
                if not sent:
                    await websocket.send_json({
                        "type": "device_offline",
                        "device_id": device_id,
                        "message": "El agente de la tienda no esta conectado"
                    })
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"Operator websocket error for {device_id}: {exc}")
    finally:
        connection_manager.disconnect_operator(websocket, device_id)
        if connection_manager.operator_count(device_id) == 0:
            await connection_manager.send_to(device_id, {"type": "stop_stream"})


@app.get("/api/public-config")
async def public_config(request: Request):
    """Public URLs the dashboard uses to generate store installers."""
    base = str(request.base_url).rstrip("/")
    return {
        "status": "success",
        "app": "AM-CONNECT",
        "api_base_url": base,
        "websocket_url": base.replace("https://", "wss://").replace("http://", "ws://") + "/ws",
        "install_script": f"{base}/install/windows.ps1",
        "agent_download": f"{base}/install/agent.py",
    }


@app.get("/install/windows.ps1")
async def install_windows_script():
    """Windows Always-ON installer served by this server so stores match the running version."""
    script = SCRIPTS_DIR / "install_from_server.ps1"
    if not script.exists():
        raise HTTPException(status_code=404, detail="Installer script not found")
    return FileResponse(
        script,
        media_type="text/plain; charset=utf-8",
        filename="install_from_server.ps1",
    )


@app.get("/install/agent.py")
async def install_agent_source():
    agent = CLIENT_DIR / "agent.py"
    if not agent.exists():
        raise HTTPException(status_code=404, detail="Agent source not found")
    return FileResponse(agent, media_type="text/plain; charset=utf-8", filename="agent.py")


@app.get("/install/agent-requirements.txt")
async def install_agent_requirements():
    requirements = SCRIPTS_DIR / "agent-requirements.txt"
    if not requirements.exists():
        return PlainTextResponse("aiohttp\npsutil\nmss\npillow\npython-dotenv\npynput\n")
    return FileResponse(requirements, media_type="text/plain; charset=utf-8")


# ===== COMMAND EXECUTION =====
@app.post("/api/devices/{device_id}/command")
async def execute_command(device_id: str, command: str, authorization: str = Header(None)):
    """Execute command on remote device"""
    try:
        user_id = _require_device_access(device_id, authorization)
        
        if device_id not in connection_manager.active_connections:
            raise HTTPException(status_code=503, detail="Device is offline")
        
        command_id = f"cmd_{int(datetime.now().timestamp())}" 
        
        # Send command to device
        await connection_manager.send_to(device_id, {
            "type": "execute_command",
            "command": command,
            "command_id": command_id
        })
        _record_audit("command_requested", user_id, device_id, {"command_id": command_id})
        
        return {
            "status": "success",
            "message": "Command sent to device",
            "command_id": command_id,
            "device_id": device_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ===== SCREEN VIEWER =====
@app.post("/api/devices/{device_id}/screenshot")
async def request_screenshot(device_id: str, authorization: str = Header(None)):
    """Request a fresh screenshot from an authorized online device."""
    user_id = _require_device_access(device_id, authorization)

    if device_id not in connection_manager.active_connections:
        raise HTTPException(status_code=503, detail="Device is offline")

    request_id = f"shot_{secrets.token_hex(8)}"
    sent = await connection_manager.send_to(device_id, {
        "type": "screenshot",
        "request_id": request_id,
        "timestamp": datetime.now().isoformat()
    })

    if not sent:
        raise HTTPException(status_code=503, detail="Unable to reach device")

    _record_audit("screenshot_requested", user_id, device_id, {"request_id": request_id})
    return {
        "status": "success",
        "message": "Screenshot requested",
        "request_id": request_id,
        "device_id": device_id
    }


@app.get("/api/devices/{device_id}/screenshot/latest")
async def latest_screenshot(device_id: str, authorization: str = Header(None)):
    """Return the latest screenshot captured for an authorized device."""
    _require_device_access(device_id, authorization)

    screenshot = latest_screenshots.get(device_id)
    if not screenshot:
        raise HTTPException(status_code=404, detail="No screenshot available yet")

    return {
        "status": "success",
        **screenshot
    }


# ===== FILE TRANSFER =====
@app.post("/api/devices/{device_id}/files/download")
async def request_file_download(device_id: str, filepath: str, authorization: str = Header(None)):
    """Request a file from an authorized online device."""
    user_id = _require_device_access(device_id, authorization)

    if device_id not in connection_manager.active_connections:
        raise HTTPException(status_code=503, detail="Device is offline")

    file_id = f"file_{secrets.token_hex(8)}"
    file_transfers[file_id] = {
        "type": "file_transfer",
        "file_id": file_id,
        "device_id": device_id,
        "filepath": filepath,
        "status": "pending",
        "requested_at": datetime.now().isoformat()
    }

    sent = await connection_manager.send_to(device_id, {
        "type": "file_download",
        "filepath": filepath,
        "file_id": file_id
    })

    if not sent:
        file_transfers[file_id]["status"] = "error"
        file_transfers[file_id]["error"] = "Unable to reach device"
        raise HTTPException(status_code=503, detail="Unable to reach device")

    _record_audit("file_download_requested", user_id, device_id, {"file_id": file_id, "filepath": filepath})
    return {
        "status": "pending",
        "message": "File download requested",
        "file_id": file_id,
        "device_id": device_id
    }


@app.post("/api/devices/{device_id}/files/upload")
async def request_file_upload(
    device_id: str,
    payload: FileUploadPayload = Body(...),
    authorization: str = Header(None)
):
    """Upload a file to the authorized device's configured AM-CONNECT uploads folder."""
    user_id = _require_device_access(device_id, authorization)

    if device_id not in connection_manager.active_connections:
        raise HTTPException(status_code=503, detail="Device is offline")

    try:
        base64.b64decode(payload.content_base64.encode(), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="content_base64 must be valid base64")

    safe_filename = Path(payload.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_id = f"upload_{secrets.token_hex(8)}"
    file_transfers[upload_id] = {
        "type": "file_upload",
        "upload_id": upload_id,
        "device_id": device_id,
        "filename": safe_filename,
        "status": "pending",
        "requested_at": datetime.now().isoformat()
    }

    sent = await connection_manager.send_to(device_id, {
        "type": "file_upload",
        "upload_id": upload_id,
        "filename": safe_filename,
        "content": payload.content_base64
    })

    if not sent:
        file_transfers[upload_id]["status"] = "error"
        file_transfers[upload_id]["error"] = "Unable to reach device"
        raise HTTPException(status_code=503, detail="Unable to reach device")

    _record_audit("file_upload_requested", user_id, device_id, {"upload_id": upload_id, "filename": safe_filename})
    return {
        "status": "pending",
        "message": "File upload requested",
        "upload_id": upload_id,
        "device_id": device_id
    }


@app.get("/api/files/{file_id}")
async def file_transfer_status(file_id: str, authorization: str = Header(None)):
    """Return file transfer status and content when available."""
    user_id = _current_user_id(authorization)
    transfer = file_transfers.get(file_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="File transfer not found")

    device_id = transfer.get("device_id")
    if device_id not in connected_devices or connected_devices[device_id]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="File transfer is not assigned to this user")

    return {
        "status": "success",
        "transfer": transfer
    }


# ===== ADMIN PANEL DATA =====
@app.get("/api/admin/summary")
async def admin_summary(authorization: str = Header(None)):
    """Return authorized dashboard metrics for the current user."""
    user_id = _current_user_id(authorization)
    user_devices = {
        dev_id: info
        for dev_id, info in connected_devices.items()
        if info["user_id"] == user_id
    }
    online_devices = [dev_id for dev_id in user_devices if dev_id in connection_manager.active_connections]
    user_events = [event for event in audit_events if event["user_id"] == user_id][-20:]
    user_transfers = [
        transfer
        for transfer in file_transfers.values()
        if transfer.get("device_id") in user_devices
    ]

    return {
        "status": "success",
        "summary": {
            "total_devices": len(user_devices),
            "online_devices": len(online_devices),
            "offline_devices": len(user_devices) - len(online_devices),
            "stored_screenshots": len([dev_id for dev_id in user_devices if dev_id in latest_screenshots]),
            "file_transfers": len(user_transfers),
            "recent_events": list(reversed(user_events))
        }
    }


# ===== ERROR HANDLERS =====
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 8000))
    use_ssl = os.getenv('USE_SSL', 'true').lower() == 'true'
    
    ssl_keyfile = None
    ssl_certfile = None
    
    if use_ssl:
        ssl_keyfile = os.getenv('SSL_KEY', 'certs/key.pem')
        ssl_certfile = os.getenv('SSL_CERT', 'certs/cert.pem')
        
        # Check if certificates exist
        if not Path(ssl_certfile).exists() or not Path(ssl_keyfile).exists():
            logger.warning(f"SSL certificates not found at {ssl_certfile} and {ssl_keyfile}")
            logger.warning("Run 'python generate_certs.py' to generate them")
            use_ssl = False
    
    scheme = "https" if use_ssl else "http"
    logger.info(f"Starting AM-CONNECT Server on {host}:{port}")
    logger.info(f"SSL/TLS: {'Enabled' if use_ssl else 'Disabled'}")
    logger.info(f"Dashboard: {scheme}://localhost:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_keyfile=ssl_keyfile if use_ssl else None,
        ssl_certfile=ssl_certfile if use_ssl else None,
        log_level="info"
    )
