#!/usr/bin/env python3
"""Visible AM-Connect agent for authorized remote support.

Run this program only on computers you own or administer with explicit consent.
It does not install persistence, hide itself, or attempt to bypass OS controls.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import aiohttp
import psutil
from dotenv import load_dotenv


load_dotenv()

AGENT_VERSION = "0.1.0"
MAX_DOWNLOAD_BYTES = int(os.getenv("AM_CONNECT_MAX_DOWNLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOW_COMMANDS = os.getenv("AM_CONNECT_ALLOW_COMMANDS", "true").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_FILE_TRANSFER = os.getenv("AM_CONNECT_ALLOW_FILE_TRANSFER", "true").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_SCREENSHOTS = os.getenv("AM_CONNECT_ALLOW_SCREENSHOTS", "true").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_REMOTE_CONTROL = os.getenv("AM_CONNECT_ALLOW_REMOTE_CONTROL", "true").strip().lower() in {"1", "true", "yes", "on"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("am-connect-agent")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AMConnectAgent:
    def __init__(self, server_url: str, device_id: str, device_secret: str, verify_ssl: bool = True):
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.device_secret = device_secret
        self.verify_ssl = verify_ssl
        self.send_lock = asyncio.Lock()
        self.stream_task: asyncio.Task | None = None
        self.stream_stop = asyncio.Event()
        self.current_monitor: dict[str, int] | None = None

    def websocket_url(self) -> str:
        scheme_url = self.server_url
        if scheme_url.startswith("http://"):
            scheme_url = "ws://" + scheme_url.removeprefix("http://")
        elif scheme_url.startswith("https://"):
            scheme_url = "wss://" + scheme_url.removeprefix("https://")
        return f"{scheme_url}/ws/agent/{self.device_id}?token={self.device_secret}"

    def ssl_context(self) -> ssl.SSLContext | bool:
        if self.websocket_url().startswith("wss://") and not self.verify_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        return True

    async def run_forever(self) -> None:
        backoff = 2
        while True:
            try:
                connector = aiohttp.TCPConnector(ssl=self.ssl_context())
                async with aiohttp.ClientSession(connector=connector) as session:
                    logger.info("Connecting to AM-Connect server: %s", self.server_url)
                    async with session.ws_connect(self.websocket_url(), heartbeat=25) as websocket:
                        logger.info("Connected as %s. Keep this window open while support is active.", self.device_id)
                        backoff = 2
                        await self._send_system_info(websocket)
                        async for message in websocket:
                            if message.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(websocket, json.loads(message.data))
                            elif message.type == aiohttp.WSMsgType.ERROR:
                                logger.error("WebSocket error: %s", websocket.exception())
                                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Disconnected: %s", exc)

            await self._stop_stream()
            logger.info("Reconnecting in %s seconds...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _send_json(self, websocket: aiohttp.ClientWebSocketResponse, payload: dict[str, Any]) -> None:
        async with self.send_lock:
            await websocket.send_json(payload)

    async def _send_system_info(self, websocket: aiohttp.ClientWebSocketResponse) -> None:
        await self._send_json(
            websocket,
            {
                "type": "system_info",
                "device_id": self.device_id,
                "agent_version": AGENT_VERSION,
                "platform": platform.platform(),
                "hostname": platform.node(),
                "python": platform.python_version(),
                "cpu_count": psutil.cpu_count(),
                "memory_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "timestamp": now(),
            }
        )

    async def _handle_message(self, websocket: aiohttp.ClientWebSocketResponse, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        message_type = message.get("type")
        try:
            if message_type == "command":
                response = await self._command(message)
            elif message_type == "screenshot":
                response = await self._screenshot(message)
            elif message_type == "file_list":
                response = self._file_list(message)
            elif message_type == "file_download":
                response = self._file_download(message)
            elif message_type == "file_upload":
                response = self._file_upload(message)
            elif message_type == "start_stream":
                await self._start_stream(websocket, message)
                return
            elif message_type == "stop_stream":
                await self._stop_stream()
                await self._send_status(websocket, "stream_stopped")
                return
            elif message_type == "mouse_event":
                response = self._mouse_event(message)
            elif message_type == "keyboard_event":
                response = self._keyboard_event(message)
            else:
                response = {"status": "error", "error": f"Unknown message type: {message_type}"}
        except Exception as exc:
            logger.exception("Failed to handle request %s", request_id)
            response = {"status": "error", "error": str(exc)}

        response_payload = {"type": f"{message_type}_response", "timestamp": now(), **response}
        if request_id:
            response_payload["request_id"] = request_id
        else:
            response_payload["type"] = "remote_control_status"
        await self._send_json(websocket, response_payload)

    async def _command(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_COMMANDS:
            return {"status": "error", "error": "Command execution is disabled on this agent."}

        command = message.get("command", "")
        timeout = int(message.get("timeout", 30))
        logger.info("Executing authorized command: %s", command)

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return {"status": "error", "error": "Command timed out", "return_code": None}

        return {
            "status": "ok",
            "return_code": process.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }

    async def _screenshot(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_SCREENSHOTS:
            return {"status": "error", "error": "Screenshots are disabled on this agent."}

        try:
            import mss
            from PIL import Image
        except ImportError as exc:
            return {"status": "error", "error": f"Screenshot dependencies are missing: {exc}"}

        quality = int(message.get("quality", 75))
        with mss.mss() as screen:
            monitor = screen.monitors[1] if len(screen.monitors) > 1 else screen.monitors[0]
            capture = screen.grab(monitor)

        image = Image.frombytes("RGB", capture.size, capture.rgb)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        return {
            "status": "ok",
            "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "mime_type": "image/jpeg",
            "width": capture.width,
            "height": capture.height,
        }

    def _file_list(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_FILE_TRANSFER:
            return {"status": "error", "error": "File transfer is disabled on this agent."}

        path = Path(message.get("path") or ".").expanduser()
        if not path.exists():
            return {"status": "error", "error": f"Path does not exist: {path}"}
        if not path.is_dir():
            return {"status": "error", "error": f"Path is not a directory: {path}"}

        entries = []
        for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            try:
                stat = child.stat()
            except OSError:
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
        return {"status": "ok", "path": str(path.resolve()), "entries": entries}

    def _file_download(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_FILE_TRANSFER:
            return {"status": "error", "error": "File transfer is disabled on this agent."}

        path = Path(message.get("path") or "").expanduser()
        if not path.is_file():
            return {"status": "error", "error": f"File does not exist: {path}"}
        size = path.stat().st_size
        if size > MAX_DOWNLOAD_BYTES:
            return {"status": "error", "error": f"File exceeds {MAX_DOWNLOAD_BYTES} bytes"}
        return {
            "status": "ok",
            "filename": path.name,
            "size": size,
            "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    def _file_upload(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_FILE_TRANSFER:
            return {"status": "error", "error": "File transfer is disabled on this agent."}

        path = Path(message.get("path") or "").expanduser()
        if path.exists() and not message.get("overwrite", True):
            return {"status": "error", "error": f"File already exists: {path}"}

        path.parent.mkdir(parents=True, exist_ok=True)
        content = base64.b64decode(message.get("content_base64", "").encode("ascii"), validate=True)
        path.write_bytes(content)
        return {"status": "ok", "path": str(path), "size": len(content)}

    async def _start_stream(self, websocket: aiohttp.ClientWebSocketResponse, message: dict[str, Any]) -> None:
        if not ALLOW_SCREENSHOTS:
            await self._send_status(websocket, "error", "Screenshots are disabled on this agent.")
            return

        fps = max(1, min(int(message.get("fps", 8)), 20))
        quality = max(25, min(int(message.get("quality", 65)), 90))
        if self.stream_task and not self.stream_task.done():
            await self._send_status(websocket, "stream_already_running")
            return

        self.stream_stop.clear()
        self.stream_task = asyncio.create_task(self._stream_screen(websocket, fps=fps, quality=quality))
        await self._send_status(websocket, "stream_started")

    async def _stop_stream(self) -> None:
        self.stream_stop.set()
        if self.stream_task and not self.stream_task.done():
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
        self.stream_task = None

    async def _stream_screen(self, websocket: aiohttp.ClientWebSocketResponse, fps: int, quality: int) -> None:
        try:
            import mss
            from PIL import Image
        except ImportError as exc:
            await self._send_status(websocket, "error", f"Streaming dependencies are missing: {exc}")
            return

        frame_delay = 1 / fps
        try:
            with mss.mss() as screen:
                monitor = screen.monitors[1] if len(screen.monitors) > 1 else screen.monitors[0]
                self.current_monitor = {
                    "left": int(monitor.get("left", 0)),
                    "top": int(monitor.get("top", 0)),
                    "width": int(monitor["width"]),
                    "height": int(monitor["height"]),
                }
                while not self.stream_stop.is_set():
                    started = time.monotonic()
                    capture = screen.grab(monitor)
                    image = Image.frombytes("RGB", capture.size, capture.rgb)
                    buffer = BytesIO()
                    image.save(buffer, format="JPEG", quality=quality, optimize=True)
                    await self._send_json(
                        websocket,
                        {
                            "type": "screen_frame",
                            "status": "ok",
                            "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                            "mime_type": "image/jpeg",
                            "width": capture.width,
                            "height": capture.height,
                            "timestamp": now(),
                        },
                    )
                    elapsed = time.monotonic() - started
                    await asyncio.sleep(max(0.01, frame_delay - elapsed))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Screen stream failed")
            await self._send_status(websocket, "error", str(exc))

    async def _send_status(
        self,
        websocket: aiohttp.ClientWebSocketResponse,
        status: str,
        message: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"type": "remote_control_status", "status": status, "timestamp": now()}
        if message:
            payload["message"] = message
        await self._send_json(websocket, payload)

    def _mouse_event(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_REMOTE_CONTROL:
            return {"status": "error", "error": "Remote control is disabled on this agent."}

        try:
            import pyautogui
        except ImportError as exc:
            return {"status": "error", "error": f"Mouse control dependency is missing: {exc}"}

        pyautogui.FAILSAFE = True
        action = message.get("action", "move")
        x, y = self._screen_coordinates(message)
        button = message.get("button", "left")

        if action == "move":
            pyautogui.moveTo(x, y, duration=0)
        elif action == "click":
            pyautogui.click(x=x, y=y, button=button)
        elif action == "double_click":
            pyautogui.doubleClick(x=x, y=y, button=button)
        elif action == "scroll":
            pyautogui.scroll(int(message.get("delta", 0)), x=x, y=y)
        else:
            return {"status": "error", "error": f"Unknown mouse action: {action}"}

        return {"status": "ok", "action": action}

    def _keyboard_event(self, message: dict[str, Any]) -> dict[str, Any]:
        if not ALLOW_REMOTE_CONTROL:
            return {"status": "error", "error": "Remote control is disabled on this agent."}

        try:
            import pyautogui
        except ImportError as exc:
            return {"status": "error", "error": f"Keyboard control dependency is missing: {exc}"}

        pyautogui.FAILSAFE = True
        action = message.get("action", "key_press")
        if action == "text":
            text = str(message.get("text", ""))
            if text:
                pyautogui.write(text, interval=0)
            return {"status": "ok", "action": action}

        key = self._normalize_key(str(message.get("key", "")))
        if not key:
            return {"status": "error", "error": "Missing key."}

        modifiers = [self._normalize_key(item) for item in message.get("modifiers", [])]
        modifiers = [item for item in modifiers if item]
        if modifiers:
            pyautogui.hotkey(*modifiers, key)
        else:
            pyautogui.press(key)
        return {"status": "ok", "action": action, "key": key}

    def _screen_coordinates(self, message: dict[str, Any]) -> tuple[int, int]:
        monitor = self.current_monitor or {"left": 0, "top": 0, "width": 1, "height": 1}
        frame_width = max(float(message.get("frame_width") or monitor["width"]), 1.0)
        frame_height = max(float(message.get("frame_height") or monitor["height"]), 1.0)
        x_ratio = max(0.0, min(float(message.get("x", 0)) / frame_width, 1.0))
        y_ratio = max(0.0, min(float(message.get("y", 0)) / frame_height, 1.0))
        x = int(monitor["left"] + x_ratio * monitor["width"])
        y = int(monitor["top"] + y_ratio * monitor["height"])
        return x, y

    @staticmethod
    def _normalize_key(key: str) -> str:
        mapping = {
            " ": "space",
            "arrowup": "up",
            "arrowdown": "down",
            "arrowleft": "left",
            "arrowright": "right",
            "escape": "esc",
            "control": "ctrl",
            "meta": "win",
            "delete": "delete",
            "backspace": "backspace",
            "enter": "enter",
            "tab": "tab",
            "shift": "shift",
            "alt": "alt",
        }
        lowered = key.strip().lower()
        return mapping.get(lowered, lowered)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value


def http_url(server_url: str) -> str:
    if server_url.startswith("ws://"):
        return "http://" + server_url.removeprefix("ws://")
    if server_url.startswith("wss://"):
        return "https://" + server_url.removeprefix("wss://")
    return server_url


def update_config_file(config_path: str, values: dict[str, Any]) -> None:
    path = Path(config_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update(values)
    current.pop("link_code", None)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")


async def link_with_code(server_url: str, link_code: str, verify_ssl: bool) -> tuple[str, str]:
    connector = aiohttp.TCPConnector(ssl=verify_ssl)
    payload = {
        "code": link_code,
        "device_name": platform.node() or "AM-Connect PC",
        "platform": platform.platform(),
        "hostname": platform.node(),
        "agent_version": AGENT_VERSION,
    }
    async with aiohttp.ClientSession(connector=connector) as session:
        response = await session.post(f"{http_url(server_url).rstrip('/')}/api/agents/link", json=payload)
        data = await response.json()
        if response.status >= 400:
            raise RuntimeError(data.get("message") or data.get("detail") or "No se pudo enlazar el equipo.")

    config_path = os.getenv("AM_CONNECT_CONFIG_PATH")
    if config_path:
        update_config_file(
            config_path,
            {
                "server_url": server_url,
                "device_id": data["device_id"],
                "device_secret": data["device_secret"],
                "verify_ssl": verify_ssl,
            },
        )
        logger.info("Linked device config saved to %s", config_path)

    return data["device_id"], data["device_secret"]


def main() -> None:
    server_url = os.getenv("AM_CONNECT_SERVER_URL", os.getenv("SERVER_URL", "ws://localhost:8000"))
    device_id = os.getenv("AM_CONNECT_DEVICE_ID")
    device_secret = os.getenv("AM_CONNECT_DEVICE_SECRET")
    link_code = os.getenv("AM_CONNECT_LINK_CODE")
    verify_ssl = os.getenv("AM_CONNECT_VERIFY_SSL", "true").strip().lower() in {"1", "true", "yes", "on"}

    if (not device_id or not device_secret) and link_code:
        logger.info("Linking this PC with AM-Connect code %s", link_code)
        try:
            device_id, device_secret = asyncio.run(link_with_code(server_url, link_code, verify_ssl))
        except Exception as exc:
            logger.error("Unable to link this PC: %s", exc)
            sys.exit(1)

    if not device_id or not device_secret:
        logger.error("Set AM_CONNECT_DEVICE_ID/AM_CONNECT_DEVICE_SECRET or AM_CONNECT_LINK_CODE.")
        sys.exit(1)

    print("AM-Connect agent is visible and active for authorized remote support.")
    print("Close this terminal or press Ctrl+C to stop remote access.")

    agent = AMConnectAgent(server_url, device_id, device_secret, verify_ssl=verify_ssl)
    try:
        asyncio.run(agent.run_forever())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")


if __name__ == "__main__":
    main()
