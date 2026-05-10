#!/usr/bin/env python3
"""AM-Connect server.

The server exposes a small web dashboard, authenticated REST APIs and an
authenticated WebSocket endpoint used by visible, enrolled agents.
"""

from __future__ import annotations

import base64
import binascii
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

try:
    from .config import settings
    from .connection_manager import AgentRequestTimeout, ConnectionManager, DeviceOfflineError
    from .models import (
        AgentLinkRequest,
        BootstrapRequest,
        CommandRequest,
        DeviceCreateRequest,
        FileUploadRequest,
        LoginRequest,
        ScreenshotRequest,
        TokenResponse,
    )
    from .security import (
        SecurityError,
        constant_time_equals,
        create_access_token,
        decode_access_token,
        extract_bearer_token,
        hash_device_secret,
        hash_password,
        new_device_secret,
        validate_password,
        verify_password,
    )
    from .store import Store
except ImportError:  # pragma: no cover - allows running python server/main.py
    from config import settings
    from connection_manager import AgentRequestTimeout, ConnectionManager, DeviceOfflineError
    from models import (
        AgentLinkRequest,
        BootstrapRequest,
        CommandRequest,
        DeviceCreateRequest,
        FileUploadRequest,
        LoginRequest,
        ScreenshotRequest,
        TokenResponse,
    )
    from security import (
        SecurityError,
        constant_time_equals,
        create_access_token,
        decode_access_token,
        extract_bearer_token,
        hash_device_secret,
        hash_password,
        new_device_secret,
        validate_password,
        verify_password,
    )
    from store import Store


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("am-connect")

app = FastAPI(
    title=settings.app_name,
    description="Panel de acceso remoto autorizado para equipos enrolados explicitamente.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = Store(settings.database_path)
connections = ConnectionManager()


def public_device(device: dict, online: bool) -> dict:
    return {
        "id": device["id"],
        "name": device["name"],
        "platform": device.get("platform"),
        "hostname": device.get("hostname"),
        "agent_version": device.get("agent_version"),
        "created_at": device["created_at"],
        "last_seen": device.get("last_seen"),
        "online": online,
    }


def current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    try:
        user = user_from_access_token(extract_bearer_token(authorization))
    except SecurityError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return user


def user_from_access_token(token: str) -> dict:
    payload = decode_access_token(token)
    user = store.get_user_by_id(payload["sub"])
    if user is None:
        raise SecurityError("Usuario no encontrado.")
    return user


def get_owned_device(device_id: str, user: dict) -> dict:
    device = store.get_device(device_id)
    if device is None or device["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
    return device


async def ask_agent(device_id: str, payload: dict, timeout: int | None = None) -> dict:
    try:
        return await connections.send_request(
            device_id,
            payload,
            timeout=timeout or settings.request_timeout_seconds,
        )
    except DeviceOfflineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentRequestTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc


def public_server_ws_url() -> str:
    scheme = "wss" if settings.use_ssl else "ws"
    host = "localhost" if settings.host in {"0.0.0.0", "::"} else settings.host
    return f"{scheme}://{host}:{settings.port}"


def make_link_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
    )


@app.get("/")
async def dashboard():
    index_path = Path(__file__).parent / "static" / "index.html"
    return FileResponse(index_path)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "users_configured": store.count_users() > 0,
        "online_devices": len(connections.online_device_ids()),
    }


@app.post("/api/auth/bootstrap", response_model=TokenResponse)
async def bootstrap(payload: BootstrapRequest):
    if store.count_users() > 0 and not settings.allow_registration_after_bootstrap:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El primer usuario ya fue creado. Inicia sesion.",
        )
    validate_password(payload.password)
    if store.get_user_by_username(payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El usuario ya existe.")
    user = store.create_user(payload.username, hash_password(payload.password))
    store.log_event("user.bootstrap", user_id=user["id"])
    return TokenResponse(access_token=create_access_token(user["id"], user["username"]), username=user["username"])


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    user = store.get_user_by_username(payload.username)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contrasena incorrectos.")
    store.update_last_login(user["id"])
    store.log_event("user.login", user_id=user["id"])
    return TokenResponse(access_token=create_access_token(user["id"], user["username"]), username=user["username"])


@app.get("/api/me")
async def me(user: Annotated[dict, Depends(current_user)]):
    return {"id": user["id"], "username": user["username"], "created_at": user["created_at"]}


@app.post("/api/devices")
async def create_device(payload: DeviceCreateRequest, user: Annotated[dict, Depends(current_user)]):
    secret = new_device_secret()
    device = store.create_device(user["id"], payload.name, hash_device_secret(secret))
    store.log_event("device.create", user_id=user["id"], device_id=device["id"], detail=payload.name)
    return {
        "device": public_device(device, online=False),
        "device_id": device["id"],
        "device_secret": secret,
        "agent_command": (
            f"AM_CONNECT_SERVER_URL=ws://localhost:{settings.port} "
            f"AM_CONNECT_DEVICE_ID={device['id']} "
            f"AM_CONNECT_DEVICE_SECRET={secret} python client/agent.py"
        ),
        "note": "Guarda este secreto ahora; no se vuelve a mostrar.",
    }


@app.post("/api/devices/link-code")
async def create_device_link_code(payload: DeviceCreateRequest, user: Annotated[dict, Depends(current_user)]):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.link_code_expire_minutes)
    for _ in range(10):
        code = make_link_code()
        if store.get_link_code(code) is None:
            break
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo generar codigo.")

    link_code = store.create_link_code(code, user["id"], payload.name, expires_at.isoformat())
    store.log_event("device.link_code.create", user_id=user["id"], detail=payload.name)
    return {
        "code": link_code["code"],
        "name": payload.name,
        "expires_at": link_code["expires_at"],
        "expires_in_minutes": settings.link_code_expire_minutes,
        "agent_command": (
            f"$env:AM_CONNECT_SERVER_URL=\"{public_server_ws_url()}\"; "
            f"$env:AM_CONNECT_LINK_CODE=\"{link_code['code']}\"; "
            ".\\venv\\Scripts\\python.exe client\\agent.py"
        ),
        "note": "Este codigo se usa una sola vez y vence automaticamente.",
    }


@app.post("/api/agents/link")
async def link_agent(payload: AgentLinkRequest):
    code = payload.code.strip().replace("-", "")
    link_code = store.get_link_code(code)
    if link_code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Codigo de enlace invalido.")
    if link_code.get("used_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Codigo de enlace ya usado.")
    if parse_utc(link_code["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Codigo de enlace vencido.")

    device_name = payload.device_name or payload.hostname or link_code["requested_name"]
    secret = new_device_secret()
    device = store.create_device(link_code["owner_user_id"], device_name, hash_device_secret(secret))
    store.update_device_metadata(
        device["id"],
        {
            "platform": payload.platform,
            "hostname": payload.hostname,
            "agent_version": payload.agent_version,
        },
    )
    store.mark_link_code_used(code, device["id"])
    store.log_event("device.link_code.redeem", user_id=link_code["owner_user_id"], device_id=device["id"], detail=code)
    return {
        "device_id": device["id"],
        "device_secret": secret,
        "device_name": device_name,
        "server_url": public_server_ws_url(),
        "message": "Equipo enlazado correctamente.",
    }


@app.get("/api/devices")
async def list_devices(user: Annotated[dict, Depends(current_user)]):
    online_ids = connections.online_device_ids()
    devices = [public_device(device, device["id"] in online_ids) for device in store.list_devices(user["id"])]
    return {"devices": devices}


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str, user: Annotated[dict, Depends(current_user)]):
    device = get_owned_device(device_id, user)
    return {"device": public_device(device, connections.is_online(device_id))}


@app.post("/api/devices/{device_id}/command")
async def execute_command(
    device_id: str,
    payload: CommandRequest,
    user: Annotated[dict, Depends(current_user)],
):
    if not settings.enable_command_execution:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La ejecucion de comandos esta deshabilitada.")
    get_owned_device(device_id, user)
    store.log_event("device.command", user_id=user["id"], device_id=device_id, detail=payload.command[:250])
    return await ask_agent(
        device_id,
        {"type": "command", "command": payload.command, "timeout": payload.timeout},
        timeout=payload.timeout + 5,
    )


@app.post("/api/devices/{device_id}/screenshot")
async def request_screenshot(
    device_id: str,
    payload: ScreenshotRequest,
    user: Annotated[dict, Depends(current_user)],
):
    if not settings.enable_screenshots:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Las capturas estan deshabilitadas.")
    get_owned_device(device_id, user)
    store.log_event("device.screenshot", user_id=user["id"], device_id=device_id)
    return await ask_agent(device_id, {"type": "screenshot", "quality": payload.quality})


@app.get("/api/devices/{device_id}/files")
async def list_files(
    device_id: str,
    user: Annotated[dict, Depends(current_user)],
    path: str = Query(default="."),
):
    if not settings.enable_file_transfer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La transferencia de archivos esta deshabilitada.")
    get_owned_device(device_id, user)
    store.log_event("device.files.list", user_id=user["id"], device_id=device_id, detail=path[:250])
    return await ask_agent(device_id, {"type": "file_list", "path": path})


@app.get("/api/devices/{device_id}/files/download")
async def download_file(
    device_id: str,
    user: Annotated[dict, Depends(current_user)],
    path: str = Query(..., min_length=1),
):
    if not settings.enable_file_transfer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La transferencia de archivos esta deshabilitada.")
    get_owned_device(device_id, user)
    store.log_event("device.files.download", user_id=user["id"], device_id=device_id, detail=path[:250])
    return await ask_agent(device_id, {"type": "file_download", "path": path})


@app.post("/api/devices/{device_id}/files/upload")
async def upload_file(
    device_id: str,
    payload: FileUploadRequest,
    user: Annotated[dict, Depends(current_user)],
):
    if not settings.enable_file_transfer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La transferencia de archivos esta deshabilitada.")
    try:
        raw_size = len(base64.b64decode(payload.content_base64.encode("utf-8"), validate=True))
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contenido base64 invalido.") from exc
    if raw_size > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Archivo demasiado grande.")
    get_owned_device(device_id, user)
    store.log_event("device.files.upload", user_id=user["id"], device_id=device_id, detail=payload.path[:250])
    return await ask_agent(
        device_id,
        {
            "type": "file_upload",
            "path": payload.path,
            "content_base64": payload.content_base64,
            "overwrite": payload.overwrite,
        },
    )


@app.websocket("/ws/agent/{device_id}")
async def agent_socket(websocket: WebSocket, device_id: str, token: str):
    device = store.get_device(device_id)
    expected_hash = device["device_secret_hash"] if device else ""
    provided_hash = hash_device_secret(token)
    if device is None or not constant_time_equals(provided_hash, expected_hash):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await connections.connect_device(device_id, websocket)
    store.touch_device(device_id)
    logger.info("Agent connected: %s", device_id)
    try:
        while True:
            message = await websocket.receive_json()
            store.touch_device(device_id)
            if message.get("type") == "system_info":
                store.update_device_metadata(device_id, message)
            elif message.get("type") in {"screen_frame", "remote_control_status"}:
                await connections.broadcast_to_controllers(device_id, message)
            else:
                handled = connections.resolve_agent_message(message)
                if not handled:
                    await connections.broadcast_to_controllers(device_id, message)
    except WebSocketDisconnect:
        logger.info("Agent disconnected: %s", device_id)
    except Exception:
        logger.exception("Agent socket failed for %s", device_id)
    finally:
        await connections.disconnect_device(device_id)


@app.websocket("/ws/control/{device_id}")
async def control_socket(websocket: WebSocket, device_id: str, token: str):
    if not settings.enable_remote_control:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user = user_from_access_token(token)
        get_owned_device(device_id, user)
    except (SecurityError, HTTPException):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not connections.is_online(device_id):
        await websocket.close(code=4004, reason="Device offline")
        return

    await connections.connect_controller(device_id, websocket)
    store.log_event("device.remote_control.start", user_id=user["id"], device_id=device_id)
    logger.info("Controller connected for %s by %s", device_id, user["username"])
    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "start_stream":
                await connections.send_event(
                    device_id,
                    {
                        "type": "start_stream",
                        "fps": int(message.get("fps", 8)),
                        "quality": int(message.get("quality", 65)),
                    },
                )
            elif message_type == "stop_stream":
                await connections.send_event(device_id, {"type": "stop_stream"})
            elif message_type in {"mouse_event", "keyboard_event"}:
                await connections.send_event(device_id, message)
            else:
                await websocket.send_json({"type": "error", "message": "Mensaje de control desconocido."})
    except WebSocketDisconnect:
        logger.info("Controller disconnected for %s", device_id)
    except Exception:
        logger.exception("Controller socket failed for %s", device_id)
    finally:
        await connections.disconnect_controller(device_id, websocket)
        if connections.controller_count(device_id) == 0 and connections.is_online(device_id):
            try:
                await connections.send_event(device_id, {"type": "stop_stream"})
            except DeviceOfflineError:
                pass


if __name__ == "__main__":
    ssl_keyfile = str(settings.ssl_key) if settings.use_ssl and settings.ssl_key.exists() else None
    ssl_certfile = str(settings.ssl_cert) if settings.use_ssl and settings.ssl_cert.exists() else None
    logger.info("Starting AM-Connect on %s:%s", settings.host, settings.port)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="debug" if settings.debug else "info",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )
