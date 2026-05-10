#!/usr/bin/env python3
"""
Remote3B Server - Professional RAT Backend
Handles multiple device connections via WebSocket with TLS encryption and JWT authentication
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Set
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

from connection_manager import ConnectionManager
from security import SecurityManager

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
    title="Remote3B Server",
    description="Professional Remote Access Tool with TLS, 2FA and Video Recording",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    expose_headers=["*"],
    allow_headers=["*"],
)

# Initialize managers
connection_manager = ConnectionManager()
security_manager = SecurityManager()

# Store connected devices
connected_devices: Dict[str, dict] = {}
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "frontend"
ASSETS_DIR = DASHBOARD_DIR / "assets"

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


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
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        
        user = security_manager.verify_token(authorization.replace('Bearer ', ''))
        
        device_id = f"device_{len(connected_devices) + 1:03d}"
        device_token = security_manager.create_device_token(device_id, user['id'])
        
        connected_devices[device_id] = {
            "device_name": device_name,
            "os": os,
            "user_id": user['id'],
            "is_online": False,
            "created_at": datetime.now().isoformat(),
            "last_seen": None
        }
        
        logger.info(f"Device registered: {device_id}")
        
        return {
            "status": "success",
            "device_id": device_id,
            "device_token": device_token,
            "message": "Device registered successfully"
        }
    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/devices")
async def list_devices(authorization: str = Header(None)):
    """List all devices"""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        
        user = security_manager.verify_token(authorization.replace('Bearer ', ''))
        
        devices = [
            {
                "device_id": dev_id,
                **device_info,
                "is_online": dev_id in connection_manager.active_connections
            }
            for dev_id, device_info in connected_devices.items()
            if device_info['user_id'] == user['id']
        ]
        
        return {
            "status": "success",
            "devices": devices,
            "total": len(devices)
        }
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/devices/{device_id}/status")
async def device_status(device_id: str, authorization: str = Header(None)):
    """Get device status"""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        
        if device_id not in connected_devices:
            raise HTTPException(status_code=404, detail="Device not found")
        
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
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    """
    WebSocket endpoint for device communication
    Handles real-time communication between control panel and devices
    """
    try:
        # Verify device exists
        if device_id not in connected_devices:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Accept connection
        await connection_manager.connect(websocket, device_id)
        connected_devices[device_id]['is_online'] = True
        connected_devices[device_id]['last_seen'] = datetime.now().isoformat()
        
        logger.info(f"Device connected: {device_id}")
        
        # Broadcast device online status
        await connection_manager.broadcast({
            "type": "device_online",
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                
                # Process message based on type
                if data.get('type') == 'screen_capture':
                    await connection_manager.broadcast(data)
                
                elif data.get('type') == 'command_response':
                    # Route to specific controller
                    target = data.get('target')
                    if target:
                        await connection_manager.send_to(target, data)
                
                elif data.get('type') == 'chat':
                    await connection_manager.broadcast(data)
                
                elif data.get('type') == 'file_transfer':
                    await connection_manager.broadcast(data)
                
                logger.debug(f"Message from {device_id}: {data.get('type')}")
                
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                continue
    
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id)
        connected_devices[device_id]['is_online'] = False
        connected_devices[device_id]['last_seen'] = datetime.now().isoformat()
        
        logger.info(f"Device disconnected: {device_id}")
        
        # Broadcast device offline status
        await connection_manager.broadcast({
            "type": "device_offline",
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"WebSocket error for {device_id}: {e}")
        connection_manager.disconnect(device_id)
        connected_devices[device_id]['is_online'] = False


# ===== COMMAND EXECUTION =====
@app.post("/api/devices/{device_id}/command")
async def execute_command(device_id: str, command: str, authorization: str = Header(None)):
    """Execute command on remote device"""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        
        if device_id not in connected_devices:
            raise HTTPException(status_code=404, detail="Device not found")
        
        if device_id not in connection_manager.active_connections:
            raise HTTPException(status_code=503, detail="Device is offline")
        
        command_id = f"cmd_{int(datetime.now().timestamp())}" 
        
        # Send command to device
        await connection_manager.send_to(device_id, {
            "type": "execute_command",
            "command": command,
            "command_id": command_id
        })
        
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
    
    logger.info(f"Starting Remote3B Server on {host}:{port}")
    logger.info(f"SSL/TLS: {'Enabled' if use_ssl else 'Disabled'}")
    logger.info(f"Dashboard: http://localhost:3000")
    
    # Run server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv('DEBUG', 'false').lower() == 'true',
        ssl_keyfile=ssl_keyfile if use_ssl else None,
        ssl_certfile=ssl_certfile if use_ssl else None,
        log_level="info"
    )
