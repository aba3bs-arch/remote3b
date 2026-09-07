#!/usr/bin/env python3
"""
AM-CONNECT Client Agent - authorized remote device client
Connects to server and executes commands, captures screen, transfers files, etc.
"""

import os
import sys
import json
import asyncio
import logging
import base64
import subprocess
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import aiohttp
import psutil
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import ssl

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SPECIAL_KEYS = {
    "Enter": "enter",
    "Tab": "tab",
    "Backspace": "backspace",
    "Escape": "esc",
    "Esc": "esc",
    "Space": "space",
    " ": "space",
    "ArrowLeft": "left",
    "ArrowRight": "right",
    "ArrowUp": "up",
    "ArrowDown": "down",
    "Delete": "delete",
    "Home": "home",
    "End": "end",
    "PageUp": "page_up",
    "PageDown": "page_down",
    "Shift": "shift",
    "Control": "ctrl",
    "Ctrl": "ctrl",
    "Alt": "alt",
    "Meta": "cmd",
    "Win": "cmd",
    "Insert": "insert",
    "CapsLock": "caps_lock",
}


class RemoteAgent:
    """
    Remote device agent
    Handles communication with server and executes remote commands
    """
    
    def __init__(
        self,
        server_url: str,
        device_id: str,
        device_name: str,
        device_token: str
    ):
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.device_name = device_name
        self.device_token = device_token
        
        self.websocket = None
        self.session = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5
        self.streaming = False
        self.stream_task: Optional[asyncio.Task] = None
        self.stream_interval = float(os.getenv("STREAM_INTERVAL", "0.4"))
        self.jpeg_quality = int(os.getenv("SCREEN_JPEG_QUALITY", "55"))
        self.max_width = int(os.getenv("SCREEN_MAX_WIDTH", "1400"))
        self.mock_screen = os.getenv("AM_CONNECT_MOCK_SCREEN", "").lower() in {"1", "true", "yes"}
    
    async def connect(self) -> bool:
        """
        Connect to server
        
        Returns:
            True if connected successfully
        """
        try:
            await self._close_session()

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(connector=connector)
            
            ws_url = f"{self.server_url}/{self.device_id}?token={self.device_token}"
            logger.info(f"Connecting to {ws_url}")
            
            self.websocket = await self.session.ws_connect(ws_url, heartbeat=20)
            self.connected = True
            self.reconnect_attempts = 0
            
            logger.info(f"Connected to server as {self.device_id}")
            await self.send_system_info()
            return True
        
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            await self._close_session()
            return False
    
    async def _close_session(self) -> None:
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None
        if self.session is not None:
            try:
                await self.session.close()
            except Exception:
                pass
            self.session = None

    async def disconnect(self) -> None:
        """Disconnect from server"""
        self.streaming = False
        if self.stream_task:
            self.stream_task.cancel()
            self.stream_task = None
        await self._close_session()
        self.connected = False
        logger.info("Disconnected from server")
    
    async def run(self) -> None:
        """
        Main agent loop
        Handles reconnection and message processing
        """
        while True:
            try:
                if not self.connected:
                    if not await self.connect():
                        self.reconnect_attempts += 1
                        wait_time = self.reconnect_delay * (2 ** min(self.reconnect_attempts, 3))
                        logger.warning(f"Reconnecting in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        continue
                
                async for msg in self.websocket:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(json.loads(msg.data))
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {self.websocket.exception()}")
                        self.connected = False
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("WebSocket closed")
                        self.connected = False
                        break
            
            except Exception as e:
                logger.error(f"Error in agent loop: {e}")
                self.connected = False
                await asyncio.sleep(1)
    
    async def _handle_message(self, message: Dict) -> None:
        try:
            msg_type = message.get('type')
            
            if msg_type == 'execute_command':
                await self._handle_command(message)
            elif msg_type == 'file_download':
                await self._handle_file_download(message)
            elif msg_type == 'file_upload':
                await self._handle_file_upload(message)
            elif msg_type == 'screenshot':
                await self._handle_screenshot(message)
            elif msg_type == 'start_stream':
                await self._start_stream()
            elif msg_type == 'stop_stream':
                self._stop_stream()
            elif msg_type == 'input':
                await self._handle_input(message)
            elif msg_type == 'ping':
                await self._handle_ping(message)
            elif msg_type in {'device_online', 'device_offline'}:
                return
            else:
                logger.warning(f"Unknown message type: {msg_type}")
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _start_stream(self) -> None:
        self.streaming = True
        if self.stream_task is None or self.stream_task.done():
            self.stream_task = asyncio.create_task(self._stream_loop())
        logger.info("Live screen stream started")

    def _stop_stream(self) -> None:
        self.streaming = False
        logger.info("Live screen stream stopped")

    async def _stream_loop(self) -> None:
        try:
            while self.streaming and self.connected:
                await self._handle_screenshot({})
                await asyncio.sleep(self.stream_interval)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Stream loop error: {exc}")
        finally:
            self.stream_task = None

    async def _handle_command(self, message: Dict) -> None:
        command = message.get('command')
        command_id = message.get('command_id')
        
        logger.info(f"Executing command: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            response = {
                'type': 'command_response',
                'command_id': command_id,
                'status': 'success',
                'output': result.stdout + result.stderr if result.returncode != 0 else result.stdout,
                'return_code': result.returncode,
                'timestamp': datetime.now().isoformat()
            }
            
            await self.send_message(response)
        
        except subprocess.TimeoutExpired:
            await self.send_message({
                'type': 'command_response',
                'command_id': command_id,
                'status': 'error',
                'error': 'Command timeout'
            })
        except Exception as e:
            await self.send_message({
                'type': 'command_response',
                'command_id': command_id,
                'status': 'error',
                'error': str(e)
            })

    def _grab_screen(self):
        if self.mock_screen:
            width, height = 1280, 720
            img = Image.new("RGB", (width, height), (12, 74, 122))
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, width, 72), fill=(8, 120, 189))
            title = f"AM-CONNECT  {self.device_name}"
            clock = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            draw.text((28, 24), title, fill="white", font=font)
            draw.rectangle((80, 160, 1200, 560), fill=(236, 244, 250))
            draw.text((110, 200), "Pantalla de prueba (Always-ON)", fill=(32, 48, 64), font=font)
            draw.text((110, 250), clock, fill=(8, 120, 189), font=font)
            draw.text((110, 320), "Este agente esta listo para control remoto.", fill=(80, 96, 110), font=font)
            return img, width, height

        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            screenshot = sct.grab(monitor)
            img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
            return img, screenshot.width, screenshot.height
    
    async def _handle_screenshot(self, message: Dict) -> None:
        try:
            img, screen_width, screen_height = await asyncio.to_thread(self._grab_screen)
            if img.width > self.max_width:
                ratio = self.max_width / img.width
                img = img.resize((self.max_width, max(1, int(img.height * ratio))), Image.BILINEAR)

            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=self.jpeg_quality)
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            await self.send_message({
                'type': 'screen_capture',
                'image': img_base64,
                'width': img.width,
                'height': img.height,
                'screen_width': screen_width,
                'screen_height': screen_height,
                'timestamp': datetime.now().isoformat()
            })
        
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")

    def _apply_input(self, message: Dict) -> None:
        try:
            from pynput.mouse import Button, Controller as MouseController
            from pynput.keyboard import Controller as KeyboardController, Key
        except Exception as exc:
            logger.warning("pynput is not available; remote input disabled (%s)", exc)
            return

        kind = message.get("kind") or message.get("input_type")
        action = message.get("action")
        mouse = MouseController()
        keyboard = KeyboardController()

        if kind == "mouse":
            x = int(message.get("x") or 0)
            y = int(message.get("y") or 0)
            if action in {"move", "down", "up", "click", "wheel"}:
                mouse.position = (x, y)
            button_name = (message.get("button") or "left").lower()
            button = {
                "left": Button.left,
                "right": Button.right,
                "middle": Button.middle,
            }.get(button_name, Button.left)
            if action == "down":
                mouse.press(button)
            elif action == "up":
                mouse.release(button)
            elif action == "click":
                mouse.click(button, 1)
            elif action == "wheel":
                mouse.scroll(0, int(message.get("delta") or 0))
            return

        if kind == "key":
            key_name = message.get("key") or ""
            key_obj = self._pynput_key(key_name, Key)
            if key_obj is None:
                return
            if action in {"down", "press"}:
                keyboard.press(key_obj)
            elif action in {"up", "release"}:
                keyboard.release(key_obj)
            elif action == "type":
                keyboard.press(key_obj)
                keyboard.release(key_obj)

    def _pynput_key(self, key_name: str, Key):
        if not key_name:
            return None
        mapped = SPECIAL_KEYS.get(key_name, SPECIAL_KEYS.get(key_name.capitalize()))
        if mapped:
            return getattr(Key, mapped, None)
        if key_name.startswith("F") and key_name[1:].isdigit():
            return getattr(Key, key_name.lower(), None)
        if len(key_name) == 1:
            return key_name
        return None

    async def _handle_input(self, message: Dict) -> None:
        try:
            await asyncio.to_thread(self._apply_input, message)
        except Exception as exc:
            logger.error(f"Error applying remote input: {exc}")
    
    async def _handle_file_download(self, message: Dict) -> None:
        filepath = message.get('filepath')
        file_id = message.get('file_id')
        
        try:
            path = Path(filepath)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {filepath}")
            
            with open(path, 'rb') as f:
                content = base64.b64encode(f.read()).decode()
            
            await self.send_message({
                'type': 'file_transfer',
                'file_id': file_id,
                'filename': path.name,
                'content': content,
                'size': path.stat().st_size,
                'status': 'success'
            })
        
        except Exception as e:
            await self.send_message({
                'type': 'file_transfer',
                'file_id': file_id,
                'status': 'error',
                'error': str(e)
            })

    async def _handle_file_upload(self, message: Dict) -> None:
        """
        Save an uploaded file into the configured AM-CONNECT uploads folder.

        The server sends only a filename, not an absolute destination path, so
        uploads cannot overwrite arbitrary files on the remote device.
        """
        upload_id = message.get('upload_id')
        filename = Path(message.get('filename', 'upload.bin')).name
        content = message.get('content', '')
        upload_dir = Path(os.getenv('AM_CONNECT_UPLOAD_DIR', 'client/downloads')).resolve()

        try:
            upload_dir.mkdir(parents=True, exist_ok=True)
            destination = upload_dir / filename
            destination.write_bytes(base64.b64decode(content.encode()))

            await self.send_message({
                'type': 'file_transfer',
                'upload_id': upload_id,
                'filename': filename,
                'saved_path': str(destination),
                'size': destination.stat().st_size,
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            await self.send_message({
                'type': 'file_transfer',
                'upload_id': upload_id,
                'filename': filename,
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    async def _handle_ping(self, message: Dict) -> None:
        await self.send_message({
            'type': 'pong',
            'timestamp': datetime.now().isoformat()
        })
    
    async def send_message(self, message: Dict) -> None:
        if not self.connected or not self.websocket:
            logger.warning("Not connected to server")
            return
        
        try:
            await self.websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.connected = False
    
    async def send_system_info(self) -> None:
        try:
            system_info = {
                'type': 'system_info',
                'device_id': self.device_id,
                'device_name': self.device_name,
                'os': platform.system(),
                'os_version': platform.version(),
                'platform': platform.platform(),
                'processor': platform.processor(),
                'cpu_cores': psutil.cpu_count(),
                'total_ram_gb': round(psutil.virtual_memory().total / (1024 ** 3), 2),
                'username': os.getenv('USERNAME') or os.getenv('USER', 'unknown'),
                'hostname': platform.node(),
                'timestamp': datetime.now().isoformat()
            }
            
            await self.send_message(system_info)
        
        except Exception as e:
            logger.error(f"Error sending system info: {e}")


async def main():
    server_url = os.getenv('SERVER_URL', 'wss://localhost:8000/ws')
    device_id = os.getenv('DEVICE_ID', 'device_001')
    device_name = os.getenv('DEVICE_NAME', platform.node())
    device_token = os.getenv('DEVICE_TOKEN', '')
    
    if not device_token:
        logger.error("DEVICE_TOKEN not set in environment")
        sys.exit(1)
    
    agent = RemoteAgent(server_url, device_id, device_name, device_token)
    
    logger.info("Starting AM-CONNECT Agent")
    logger.info(f"  Device ID: {device_id}")
    logger.info(f"  Device Name: {device_name}")
    logger.info(f"  Server: {server_url}")
    
    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
        await agent.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
