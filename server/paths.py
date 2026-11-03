#!/usr/bin/env python3
"""Runtime paths for source installs and frozen Windows executables."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def executable_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return runtime_root()


def user_data_dir() -> Path:
    configured = os.getenv("AM_CONNECT_DATA_DIR")
    if configured:
        return Path(configured)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "AM-CONNECT" / "data"
    return Path.home() / ".am-connect" / "data"


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().strip("[]")
    return host in _LOOPBACK_HOSTS


def detect_lan_ip() -> str:
    """Best-effort address other PCs on this network can use to reach us."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        return ""
    if not ip or ip.startswith("127."):
        return ""
    return ip


def agent_exe_candidates() -> list[Path]:
    names = ("AM-CONNECT-Agent.exe", "AM-CONNECT-Agent")
    folders = [executable_dir(), runtime_root() / "dist", runtime_root()]
    return [folder / name for folder in folders for name in names]
