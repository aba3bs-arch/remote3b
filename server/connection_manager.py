#!/usr/bin/env python3
"""
Connection Manager - Handles multiple WebSocket connections from devices
"""

import json
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for multiple devices
    Handles broadcasting, targeted messaging, and connection tracking
    """
    
    def __init__(self):
        # Store active connections
        self.active_connections: Dict[str, WebSocket] = {}
        # Store connection metadata
        self.connection_metadata: Dict[str, dict] = {}
        # Operator viewers keyed by device_id
        self.operator_connections: Dict[str, list] = {}
    
    async def connect(self, websocket: WebSocket, device_id: str) -> None:
        """
        Register a new device connection
        
        Args:
            websocket: WebSocket connection
            device_id: Unique device identifier
        """
        try:
            await websocket.accept()
            self.active_connections[device_id] = websocket
            logger.info(f"Device {device_id} connected")
        except Exception as e:
            logger.error(f"Error connecting device {device_id}: {e}")
            raise
    
    def disconnect(self, device_id: str) -> None:
        """
        Unregister a device connection
        
        Args:
            device_id: Unique device identifier
        """
        if device_id in self.active_connections:
            del self.active_connections[device_id]
            if device_id in self.connection_metadata:
                del self.connection_metadata[device_id]
            logger.info(f"Device {device_id} disconnected")

    async def connect_operator(self, websocket: WebSocket, device_id: str) -> None:
        """Accept an operator/viewer websocket for a device."""
        await websocket.accept()
        self.operator_connections.setdefault(device_id, []).append(websocket)
        logger.info(f"Operator connected to {device_id}")

    def disconnect_operator(self, websocket: WebSocket, device_id: str) -> None:
        """Remove an operator/viewer websocket."""
        viewers = self.operator_connections.get(device_id) or []
        self.operator_connections[device_id] = [item for item in viewers if item is not websocket]
        if not self.operator_connections[device_id]:
            self.operator_connections.pop(device_id, None)
        logger.info(f"Operator disconnected from {device_id}")

    def operator_count(self, device_id: str) -> int:
        return len(self.operator_connections.get(device_id) or [])

    async def send_to_operators(self, device_id: str, message: dict) -> int:
        """Push a message to every operator watching this device."""
        viewers = list(self.operator_connections.get(device_id) or [])
        sent = 0
        stale = []
        for websocket in viewers:
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception as exc:
                logger.error(f"Error sending to operator of {device_id}: {exc}")
                stale.append(websocket)
        for websocket in stale:
            self.disconnect_operator(websocket, device_id)
        return sent
    
    async def send_to(self, device_id: str, message: dict) -> bool:
        """
        Send message to specific device
        
        Args:
            device_id: Target device ID
            message: Message dictionary
        
        Returns:
            True if message sent successfully
        """
        if device_id not in self.active_connections:
            logger.warning(f"Device {device_id} not connected")
            return False
        
        try:
            websocket = self.active_connections[device_id]
            await websocket.send_json(message)
            logger.debug(f"Message sent to {device_id}: {message.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Error sending message to {device_id}: {e}")
            self.disconnect(device_id)
            return False
    
    async def broadcast(self, message: dict, exclude: Optional[Set[str]] = None) -> int:
        """
        Broadcast message to all connected devices
        
        Args:
            message: Message dictionary
            exclude: Set of device IDs to exclude
        
        Returns:
            Number of successful broadcasts
        """
        exclude = exclude or set()
        success_count = 0
        
        disconnected = []
        
        for device_id, websocket in list(self.active_connections.items()):
            if device_id in exclude:
                continue
            
            try:
                await websocket.send_json(message)
                success_count += 1
            except Exception as e:
                logger.error(f"Error broadcasting to {device_id}: {e}")
                disconnected.append(device_id)
        
        # Clean up disconnected devices
        for device_id in disconnected:
            self.disconnect(device_id)
        
        logger.debug(f"Broadcast sent to {success_count} devices")
        return success_count
    
    async def broadcast_to_group(self, device_ids: Set[str], message: dict) -> int:
        """
        Broadcast message to specific group of devices
        
        Args:
            device_ids: Set of target device IDs
            message: Message dictionary
        
        Returns:
            Number of successful broadcasts
        """
        success_count = 0
        disconnected = []
        
        for device_id in device_ids:
            if device_id not in self.active_connections:
                continue
            
            try:
                websocket = self.active_connections[device_id]
                await websocket.send_json(message)
                success_count += 1
            except Exception as e:
                logger.error(f"Error sending to {device_id}: {e}")
                disconnected.append(device_id)
        
        # Clean up disconnected devices
        for device_id in disconnected:
            self.disconnect(device_id)
        
        return success_count
    
    def get_connected_devices(self) -> list:
        """
        Get list of connected device IDs
        
        Returns:
            List of device IDs
        """
        return list(self.active_connections.keys())
    
    def get_connection_count(self) -> int:
        """
        Get number of connected devices
        
        Returns:
            Number of active connections
        """
        return len(self.active_connections)
    
    def is_connected(self, device_id: str) -> bool:
        """
        Check if device is connected
        
        Args:
            device_id: Device ID to check
        
        Returns:
            True if device is connected
        """
        return device_id in self.active_connections
    
    def set_metadata(self, device_id: str, key: str, value: any) -> None:
        """
        Store metadata for a device
        
        Args:
            device_id: Device ID
            key: Metadata key
            value: Metadata value
        """
        if device_id not in self.connection_metadata:
            self.connection_metadata[device_id] = {}
        
        self.connection_metadata[device_id][key] = value
    
    def get_metadata(self, device_id: str, key: str, default=None) -> any:
        """
        Retrieve metadata for a device
        
        Args:
            device_id: Device ID
            key: Metadata key
            default: Default value if key doesn't exist
        
        Returns:
            Metadata value or default
        """
        if device_id not in self.connection_metadata:
            return default
        
        return self.connection_metadata[device_id].get(key, default)
