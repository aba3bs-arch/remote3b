#!/usr/bin/env python3
"""
Remote3B Client Agent - Remote device client
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
import mss
from PIL import Image
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
        """
        Initialize remote agent
        
        Args:
            server_url: Server WebSocket URL
            device_id: Device identifier
            device_name: Device name
            device_token: Device authentication token
        """
        self.server_url = server_url
        self.device_id = device_id
        self.device_name = device_name
        self.device_token = device_token
        
        self.websocket = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # seconds
    
    async def connect(self) -> bool:
        """
        Connect to server
        
        Returns:
            True if connected successfully
        """
        try:
            # Create SSL context (skip verification for self-signed certs)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            session = aiohttp.ClientSession(connector=connector)
            
            ws_url = f"{self.server_url}/{self.device_id}?token={self.device_token}"
            logger.info(f"Connecting to {ws_url}")
            
            self.websocket = await session.ws_connect(ws_url)
            self.connected = True
            self.reconnect_attempts = 0
            
            logger.info(f"Connected to server as {self.device_id}")
            return True
        
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            return False
    
    async def disconnect(self) -> None:
        """
        Disconnect from server
        """
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info("Disconnected from server")
    
    async def run(self) -> None:
        """
        Main agent loop
        Handles reconnection and message processing
        """
        while True:
            try:
                # Connect if not connected
                if not self.connected:
                    if not await self.connect():
                        self.reconnect_attempts += 1
                        wait_time = self.reconnect_delay * (2 ** min(self.reconnect_attempts, 3))
                        logger.warning(f"Reconnecting in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        continue
                
                # Listen for messages
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
        """
        Handle incoming message
        
        Args:
            message: Message dictionary
        """
        try:
            msg_type = message.get('type')
            
            if msg_type == 'execute_command':
                await self._handle_command(message)
            elif msg_type == 'file_download':
                await self._handle_file_download(message)
            elif msg_type == 'screenshot':
                await self._handle_screenshot(message)
            elif msg_type == 'ping':
                await self._handle_ping(message)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_command(self, message: Dict) -> None:
        """
        Execute command and send response
        
        Args:
            message: Command message
        """
        command = message.get('command')
        command_id = message.get('command_id')
        
        logger.info(f"Executing command: {command}")
        
        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Send response
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
    
    async def _handle_screenshot(self, message: Dict) -> None:
        """
        Capture and send screenshot
        
        Args:
            message: Screenshot request message
        """
        try:
            # Capture screen
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes('RGBA', screenshot.size, screenshot.rgb)
                
                # Compress and encode
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=80)
                img_base64 = base64.b64encode(buffer.getvalue()).decode()
                
                # Send screenshot
                await self.send_message({
                    'type': 'screen_capture',
                    'image': img_base64,
                    'width': screenshot.width,
                    'height': screenshot.height,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.debug("Screenshot captured and sent")
        
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
    
    async def _handle_file_download(self, message: Dict) -> None:
        """
        Download file from device
        
        Args:
            message: File download request
        """
        filepath = message.get('filepath')
        file_id = message.get('file_id')
        
        try:
            path = Path(filepath)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {filepath}")
            
            # Read and encode file
            with open(path, 'rb') as f:
                content = base64.b64encode(f.read()).decode()
            
            # Send file
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
    
    async def _handle_ping(self, message: Dict) -> None:
        """
        Respond to ping
        
        Args:
            message: Ping message
        """
        await self.send_message({
            'type': 'pong',
            'timestamp': datetime.now().isoformat()
        })
    
    async def send_message(self, message: Dict) -> None:
        """
        Send message to server
        
        Args:
            message: Message dictionary
        """
        if not self.connected or not self.websocket:
            logger.warning("Not connected to server")
            return
        
        try:
            await self.websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.connected = False
    
    async def send_system_info(self) -> None:
        """
        Send system information to server
        """
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
                'username': os.getenv('USERNAME', 'unknown'),
                'hostname': platform.node(),
                'timestamp': datetime.now().isoformat()
            }
            
            await self.send_message(system_info)
        
        except Exception as e:
            logger.error(f"Error sending system info: {e}")


async def main():
    """
    Main entry point
    """
    # Get configuration from environment
    server_url = os.getenv('SERVER_URL', 'wss://localhost:8000/ws')
    device_id = os.getenv('DEVICE_ID', 'device_001')
    device_name = os.getenv('DEVICE_NAME', platform.node())
    device_token = os.getenv('DEVICE_TOKEN', '')
    
    if not device_token:
        logger.error("DEVICE_TOKEN not set in environment")
        sys.exit(1)
    
    # Initialize and run agent
    agent = RemoteAgent(server_url, device_id, device_name, device_token)
    
    logger.info(f"Starting Remote3B Agent")
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
