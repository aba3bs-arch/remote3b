#!/usr/bin/env python3
"""WebSocket connection manager for AM-Connect agents."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import WebSocket


class DeviceOfflineError(RuntimeError):
    """Raised when an API request targets an offline device."""


class AgentRequestTimeout(RuntimeError):
    """Raised when an agent does not answer a request in time."""


class ConnectionManager:
    def __init__(self) -> None:
        self._devices: dict[str, WebSocket] = {}
        self._device_send_locks: dict[str, asyncio.Lock] = {}
        self._controllers: dict[str, set[WebSocket]] = {}
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._pending_devices: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def connect_device(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            previous = self._devices.get(device_id)
            if previous is not None:
                await previous.close(code=4000, reason="New connection opened for this device")
            self._devices[device_id] = websocket
            self._device_send_locks[device_id] = asyncio.Lock()

    async def disconnect_device(self, device_id: str) -> None:
        async with self._lock:
            current = self._devices.pop(device_id, None)
            self._device_send_locks.pop(device_id, None)
        if current is not None:
            for request_id, future in list(self._pending.items()):
                if self._pending_devices.get(request_id) != device_id:
                    continue
                if not future.done():
                    future.set_exception(DeviceOfflineError(f"Device {device_id} disconnected"))
                self._pending.pop(request_id, None)
                self._pending_devices.pop(request_id, None)

            for controller in list(self._controllers.get(device_id, set())):
                await controller.close(code=4001, reason="Device disconnected")
            self._controllers.pop(device_id, None)

    async def connect_controller(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._controllers.setdefault(device_id, set()).add(websocket)

    async def disconnect_controller(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            controllers = self._controllers.get(device_id)
            if not controllers:
                return
            controllers.discard(websocket)
            if not controllers:
                self._controllers.pop(device_id, None)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._devices

    def online_device_ids(self) -> set[str]:
        return set(self._devices.keys())

    def controller_count(self, device_id: str) -> int:
        return len(self._controllers.get(device_id, set()))

    async def send_request(self, device_id: str, payload: dict, timeout: int) -> dict:
        websocket = self._devices.get(device_id)
        if websocket is None:
            raise DeviceOfflineError("El equipo esta desconectado.")

        request_id = f"req_{uuid4().hex}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[request_id] = future
        self._pending_devices[request_id] = device_id

        message = {"request_id": request_id, **payload}
        try:
            async with self._device_send_locks.setdefault(device_id, asyncio.Lock()):
                await websocket.send_json(message)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise AgentRequestTimeout("El equipo no respondio a tiempo.") from exc
        finally:
            self._pending.pop(request_id, None)
            self._pending_devices.pop(request_id, None)

    async def send_event(self, device_id: str, payload: dict) -> None:
        websocket = self._devices.get(device_id)
        if websocket is None:
            raise DeviceOfflineError("El equipo esta desconectado.")
        async with self._device_send_locks.setdefault(device_id, asyncio.Lock()):
            await websocket.send_json(payload)

    async def broadcast_to_controllers(self, device_id: str, message: dict) -> int:
        controllers = list(self._controllers.get(device_id, set()))
        sent = 0
        disconnected: list[WebSocket] = []
        for controller in controllers:
            try:
                await controller.send_json(message)
                sent += 1
            except Exception:
                disconnected.append(controller)

        for controller in disconnected:
            await self.disconnect_controller(device_id, controller)
        return sent

    def resolve_agent_message(self, message: dict) -> bool:
        request_id = message.get("request_id")
        if not request_id:
            return False

        future = self._pending.get(request_id)
        if future is None or future.done():
            return False

        future.set_result(message)
        return True
