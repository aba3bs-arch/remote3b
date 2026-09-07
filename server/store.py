#!/usr/bin/env python3
"""JSON persistence for AM-CONNECT users, devices, and install codes."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict


class AppStore:
    """Small file-backed store so store computers survive server restarts."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = Lock()
        self.data: Dict[str, Any] = {
            "users": {},
            "devices": {},
            "install_codes": {},
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(loaded, dict):
            return
        with self.lock:
            self.data["users"] = loaded.get("users") or {}
            self.data["devices"] = loaded.get("devices") or {}
            self.data["install_codes"] = loaded.get("install_codes") or {}

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(self.path)

    def users(self) -> Dict[str, Any]:
        return self.data["users"]

    def devices(self) -> Dict[str, Any]:
        return self.data["devices"]

    def install_codes(self) -> Dict[str, Any]:
        return self.data["install_codes"]
