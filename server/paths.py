#!/usr/bin/env python3
"""Runtime paths for source installs and frozen Windows executables."""

from __future__ import annotations

import os
import sys
from pathlib import Path


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


def agent_exe_candidates() -> list[Path]:
    names = ("AM-CONNECT-Agent.exe", "AM-CONNECT-Agent")
    folders = [executable_dir(), runtime_root() / "dist", runtime_root()]
    return [folder / name for folder in folders for name in names]
