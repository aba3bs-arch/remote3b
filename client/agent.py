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
from datetime import datetime, timezone
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

            logger.info("Reconnecting in %s seconds...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _send_system_info(self, websocket: aiohttp.ClientWebSocketResponse) -> None:
        await websocket.send_json(
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
            else:
                response = {"status": "error", "error": f"Unknown message type: {message_type}"}
        except Exception as exc:
            logger.exception("Failed to handle request %s", request_id)
            response = {"status": "error", "error": str(exc)}

        await websocket.send_json(
            {
                "request_id": request_id,
                "type": f"{message_type}_response",
                "timestamp": now(),
                **response,
            }
        )

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
        from io import BytesIO

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


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value


def main() -> None:
    server_url = os.getenv("AM_CONNECT_SERVER_URL", os.getenv("SERVER_URL", "ws://localhost:8000"))
    device_id = require_env("AM_CONNECT_DEVICE_ID")
    device_secret = require_env("AM_CONNECT_DEVICE_SECRET")
    verify_ssl = os.getenv("AM_CONNECT_VERIFY_SSL", "true").strip().lower() in {"1", "true", "yes", "on"}

    print("AM-Connect agent is visible and active for authorized remote support.")
    print("Close this terminal or press Ctrl+C to stop remote access.")

    agent = AMConnectAgent(server_url, device_id, device_secret, verify_ssl=verify_ssl)
    try:
        asyncio.run(agent.run_forever())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")


if __name__ == "__main__":
    main()
