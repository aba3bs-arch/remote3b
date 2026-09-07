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

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
from dotenv import load_dotenv

from connection_manager import ConnectionManager
from installer import build_windows_installer
from paths import agent_exe_candidates, runtime_root, user_data_dir
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
        'http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000'
    ).split(','),
    allow_credentials=True,
    allow_methods=["*"],
    expose_headers=["*"],
    allow_headers=["*"],
)

# Initialize managers
DATA_DIR = user_data_dir()
app_store = AppStore(DATA_DIR / "am_connect.json")
connection_manager = ConnectionManager()
security_manager = SecurityManager(store=app_store)

# Store connected devices (runtime overlay on persisted records)
connected_devices: Dict[str, dict] = {}
for saved_id, saved_device in app_store.devices().items():
    connected_devices[saved_id] = {
        **saved_device,
        "is_online": False,
        "in_session": False,
    }
latest_screenshots: Dict[str, dict] = {}
file_transfers: Dict[str, dict] = {}
audit_events = []
BASE_DIR = runtime_root()
DASHBOARD_DIR = BASE_DIR / "frontend"
ASSETS_DIR = DASHBOARD_DIR / "assets"

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


class FileUploadPayload(BaseModel):
    """Payload for uploading a file to an authorized remote device."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


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


def _persist_devices() -> None:
    serializable = {}
    for device_id, device in connected_devices.items():
        serializable[device_id] = {
            key: value
            for key, value in device.items()
            if key not in {"is_online", "in_session"}
        }
    app_store.data["devices"] = serializable
    app_store.save()


def _public_base_url(request: Optional[Request] = None) -> str:
    configured = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://localhost:8000"


def _ws_base_url(request: Optional[Request] = None) -> str:
    http_url = _public_base_url(request)
    if http_url.startswith("https://"):
        return "wss://" + http_url[len("https://"):] + "/ws"
    if http_url.startswith("http://"):
        return "ws://" + http_url[len("http://"):] + "/ws"
    return http_url.rstrip("/") + "/ws"


def _device_payload(device_id: str, device: dict) -> dict:
    is_online = device_id in connection_manager.active_connections
    connection_error = device.get("connection_error")
    if not is_online and not device.get("last_seen"):
        connection_error = connection_error or "Fallo de conexion"
    elif not is_online and device.get("last_seen"):
        connection_error = connection_error or "Fallo de conexion"
    else:
        connection_error = None

    return {
        "device_id": device_id,
        "device_name": device.get("device_name") or device_id,
        "os": device.get("os") or "Windows",
        "user_id": device.get("user_id"),
        "is_online": is_online,
        "in_session": connection_manager.viewer_count(device_id) > 0,
        "created_at": device.get("created_at"),
        "last_seen": device.get("last_seen"),
        "last_accessed": device.get("last_accessed"),
        "connection_error": connection_error,
        "install_code": device.get("install_code"),
    }


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
async def register(username: str, email: str, password: str):
    """Register a new user"""
    try:
        user = security_manager.register_user(username, email, password)
        return {
            "status": "success",
            "message": "User registered successfully",
            "user_id": user['id'],
            "username": user['username']
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def login(username: str, password: str, totp_code: str = None):
    """Login user"""
    try:
        user, tokens = security_manager.login_user(username, password, totp_code)
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
async def register_device(device_name: str, os: str, authorization: str = Header(None)):
    """Register a new device"""
    try:
        user_id = _current_user_id(authorization)
        
        device_id = f"device_{secrets.token_hex(4)}"
        device_token = security_manager.create_device_token(device_id, user_id)
        install_code = secrets.token_urlsafe(12)
        
        connected_devices[device_id] = {
            "device_name": device_name,
            "os": os,
            "user_id": user_id,
            "is_online": False,
            "created_at": datetime.now().isoformat(),
            "last_seen": None,
            "last_accessed": None,
            "connection_error": "Fallo de conexion",
            "install_code": install_code,
        }

        app_store.install_codes()[install_code] = {
            "device_id": device_id,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
        }
        _persist_devices()
        
        logger.info(f"Device registered: {device_id}")
        _record_audit("device_registered", user_id, device_id, {"device_name": device_name, "os": os})
        
        return {
            "status": "success",
            "device_id": device_id,
            "device_token": device_token,
            "install_code": install_code,
            "message": "Device registered successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/devices")
async def list_devices(authorization: str = Header(None)):
    """List all devices"""
    try:
        user_id = _current_user_id(authorization)
        
        devices = [
            _device_payload(dev_id, device_info)
            for dev_id, device_info in connected_devices.items()
            if device_info['user_id'] == user_id
        ]
        devices.sort(
            key=lambda item: (item.get("device_name") or "").lower()
        )
        
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
        connected_devices[device_id]['connection_error'] = None
        _persist_devices()
        
        logger.info(f"Device connected: {device_id}")
        
        if connection_manager.viewer_count(device_id) > 0:
            await connection_manager.send_to(device_id, {
                "type": "start_stream",
                "quality": 55,
                "timestamp": datetime.now().isoformat()
            })
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                
                # Process message based on type
                if data.get('type') == 'screen_capture':
                    latest_screenshots[device_id] = {
                        "device_id": device_id,
                        "image": data.get('image'),
                        "width": data.get('width'),
                        "height": data.get('height'),
                        "timestamp": data.get('timestamp') or datetime.now().isoformat()
                    }
                    await connection_manager.send_to_viewers(device_id, {
                        "type": "screen_capture",
                        "image": data.get('image'),
                        "width": data.get('width'),
                        "height": data.get('height'),
                        "timestamp": latest_screenshots[device_id]["timestamp"],
                    })
                
                elif data.get('type') == 'command_response':
                    await connection_manager.send_to_viewers(device_id, data)
                
                elif data.get('type') == 'chat':
                    await connection_manager.send_to_viewers(device_id, data)
                
                elif data.get('type') == 'file_transfer':
                    file_id = data.get('file_id') or data.get('upload_id')
                    if file_id:
                        file_transfers[file_id] = {
                            **data,
                            "device_id": device_id,
                            "received_at": datetime.now().isoformat()
                        }
                    await connection_manager.send_to_viewers(device_id, data)

                elif data.get('type') == 'heartbeat':
                    connected_devices[device_id]['last_seen'] = datetime.now().isoformat()
                    connected_devices[device_id]['connection_error'] = None
                
                elif data.get('type') == 'agent_error':
                    connected_devices[device_id]['connection_error'] = data.get('error') or 'Fallo de conexion'
                    await connection_manager.send_to_viewers(device_id, data)
                
                logger.debug(f"Message from {device_id}: {data.get('type')}")
                
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                continue
    
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id)
        if device_id in connected_devices:
            connected_devices[device_id]['is_online'] = False
            connected_devices[device_id]['last_seen'] = datetime.now().isoformat()
            connected_devices[device_id]['connection_error'] = "Fallo de conexion"
            _persist_devices()
        
        logger.info(f"Device disconnected: {device_id}")
        await connection_manager.send_to_viewers(device_id, {
            "type": "device_offline",
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"WebSocket error for {device_id}: {e}")
        connection_manager.disconnect(device_id)
        if device_id in connected_devices:
            connected_devices[device_id]['is_online'] = False
            connected_devices[device_id]['connection_error'] = "Fallo de conexion"
            _persist_devices()


@app.websocket("/ws/session/{device_id}")
async def session_viewer_socket(websocket: WebSocket, device_id: str, token: Optional[str] = None):
    """WebSocket for an authorized operator viewing a store computer."""
    try:
        payload = security_manager.verify_token(token or "")
        if payload.get("type") != "access":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_id = payload.get("sub")
        if device_id not in connected_devices or connected_devices[device_id]["user_id"] != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await connection_manager.add_viewer(websocket, device_id)
    connected_devices[device_id]["last_accessed"] = datetime.now().isoformat()
    connected_devices[device_id]["in_session"] = True
    _persist_devices()
    _record_audit("session_started", user_id, device_id)

    if device_id in connection_manager.active_connections:
        await connection_manager.send_to(device_id, {
            "type": "start_stream",
            "quality": 55,
            "timestamp": datetime.now().isoformat()
        })

    latest = latest_screenshots.get(device_id)
    if latest:
        await websocket.send_json({
            "type": "screen_capture",
            "image": latest.get("image"),
            "width": latest.get("width"),
            "height": latest.get("height"),
            "timestamp": latest.get("timestamp"),
        })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "input":
                await connection_manager.send_to(device_id, {
                    "type": "input",
                    "event": data.get("event"),
                    "x": data.get("x"),
                    "y": data.get("y"),
                    "button": data.get("button"),
                    "key": data.get("key"),
                    "dx": data.get("dx"),
                    "dy": data.get("dy"),
                })
            elif msg_type == "screenshot":
                await connection_manager.send_to(device_id, {
                    "type": "screenshot",
                    "request_id": data.get("request_id") or secrets.token_hex(8),
                })
            elif msg_type == "chat":
                await connection_manager.send_to(device_id, data)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"Viewer socket error for {device_id}: {exc}")
    finally:
        remaining = connection_manager.remove_viewer(websocket, device_id)
        if remaining == 0:
            connected_devices[device_id]["in_session"] = False
            await connection_manager.send_to(device_id, {"type": "stop_stream"})
            _persist_devices()


class InputPayload(BaseModel):
    event: str = Field(..., min_length=1, max_length=40)
    x: Optional[float] = None
    y: Optional[float] = None
    button: Optional[str] = None
    key: Optional[str] = None
    dx: Optional[float] = None
    dy: Optional[float] = None


@app.post("/api/devices/{device_id}/input")
async def send_input_event(
    device_id: str,
    payload: InputPayload,
    authorization: str = Header(None)
):
    """Forward a mouse/keyboard event to an authorized online device."""
    user_id = _require_device_access(device_id, authorization)
    if device_id not in connection_manager.active_connections:
        raise HTTPException(status_code=503, detail="Device is offline")

    sent = await connection_manager.send_to(device_id, {
        "type": "input",
        "event": payload.event,
        "x": payload.x,
        "y": payload.y,
        "button": payload.button,
        "key": payload.key,
        "dx": payload.dx,
        "dy": payload.dy,
    })
    if not sent:
        raise HTTPException(status_code=503, detail="Unable to reach device")
    _record_audit("input_sent", user_id, device_id, {"event": payload.event})
    return {"status": "success"}


@app.post("/api/devices/{device_id}/access")
async def mark_device_accessed(device_id: str, authorization: str = Header(None)):
    """Record that the operator opened a remote session."""
    _require_device_access(device_id, authorization)
    connected_devices[device_id]["last_accessed"] = datetime.now().isoformat()
    _persist_devices()
    return {"status": "success", "last_accessed": connected_devices[device_id]["last_accessed"]}


@app.get("/api/devices/{device_id}/installer")
async def device_installer(device_id: str, request: Request, authorization: str = Header(None)):
    """Return a copy/paste Always-ON installer command for a store computer."""
    user_id = _require_device_access(device_id, authorization)
    device = connected_devices[device_id]
    device_token = security_manager.create_device_token(device_id, user_id)
    install_code = device.get("install_code") or secrets.token_urlsafe(12)
    device["install_code"] = install_code
    app_store.install_codes()[install_code] = {
        "device_id": device_id,
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
    }
    _persist_devices()
    base_url = _public_base_url(request)
    script_url = f"{base_url}/install/windows.ps1?code={install_code}"
    command = (
        f"$installer = \"$env:TEMP\\am-connect-store.ps1\"; "
        f"Invoke-WebRequest -UseBasicParsing -Uri \"{script_url}\" -OutFile $installer; "
        f"powershell -ExecutionPolicy Bypass -File $installer"
    )
    return {
        "status": "success",
        "device_id": device_id,
        "device_name": device.get("device_name"),
        "install_code": install_code,
        "script_url": script_url,
        "command": command,
        "device_token": device_token,
        "ws_url": _ws_base_url(request),
    }


@app.get("/install/windows.ps1")
async def download_windows_installer(request: Request, code: str = Query(...)):
    """Serve a pre-filled PowerShell installer for one registered store computer."""
    record = app_store.install_codes().get(code)
    if not record:
        raise HTTPException(status_code=404, detail="Install code not found")
    device_id = record["device_id"]
    device = connected_devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device_token = security_manager.create_device_token(device_id, device["user_id"])
    script = build_windows_installer(
        api_url=_public_base_url(request),
        ws_url=_ws_base_url(request),
        device_id=device_id,
        device_token=device_token,
        device_name=device.get("device_name") or device_id,
    )
    return PlainTextResponse(script, media_type="text/plain; charset=utf-8")


@app.get("/api/downloads")
async def download_availability():
    has_agent = any(path.exists() and path.is_file() for path in agent_exe_candidates())
    return {"status": "success", "agent_exe": has_agent}


@app.get("/download/agent.exe")
async def download_agent_exe():
    """Serve the packaged Windows agent when it sits next to this app."""
    for candidate in agent_exe_candidates():
        if candidate.exists() and candidate.is_file():
            return FileResponse(
                candidate,
                media_type="application/octet-stream",
                filename="AM-CONNECT-Agent.exe",
            )
    raise HTTPException(status_code=404, detail="Agent executable is not bundled yet")


@app.get("/install/agent.py")
async def download_agent_script():
    """Serve the authorized Windows/Linux agent from this same server."""
    agent_file = BASE_DIR / "client" / "agent.py"
    if not agent_file.exists():
        raise HTTPException(status_code=404, detail="Agent script not found")
    return FileResponse(agent_file, media_type="text/x-python", filename="agent.py")


@app.get("/api/me")
async def current_user(authorization: str = Header(None)):
    payload = _current_user_payload(authorization)
    user = next((item for item in security_manager.users.values() if item["id"] == payload["sub"]), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "status": "success",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
        }
    }


@app.post("/api/auth/refresh")
async def refresh_session(refresh_token: str):
    try:
        payload = security_manager.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Refresh token required")
        access_token = security_manager.create_access_token(payload["sub"])
        return {"status": "success", "access_token": access_token}
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


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
    import sys as _sys

    host = os.getenv('HOST', '127.0.0.1' if getattr(_sys, 'frozen', False) else '0.0.0.0')
    port = int(os.getenv('PORT', 8000))
    use_ssl = os.getenv('USE_SSL', 'false').lower() == 'true'
    
    ssl_keyfile = None
    ssl_certfile = None
    
    if use_ssl:
        ssl_keyfile = os.getenv('SSL_KEY', 'certs/key.pem')
        ssl_certfile = os.getenv('SSL_CERT', 'certs/cert.pem')
        
        if not Path(ssl_certfile).exists() or not Path(ssl_keyfile).exists():
            logger.warning(f"SSL certificates not found at {ssl_certfile} and {ssl_keyfile}")
            logger.warning("Run 'python generate_certs.py' to generate them")
            use_ssl = False
    
    logger.info(f"Starting AM-CONNECT Server on {host}:{port}")
    logger.info(f"SSL/TLS: {'Enabled' if use_ssl else 'Disabled'}")
    logger.info(f"Dashboard: http://127.0.0.1:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_keyfile=ssl_keyfile if use_ssl else None,
        ssl_certfile=ssl_certfile if use_ssl else None,
        log_level="info"
    )
