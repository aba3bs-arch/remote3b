#!/usr/bin/env python3
"""SQLite persistence for AM-CONNECT users and authorized devices."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional


def default_db_path() -> Path:
    raw = os.getenv("AM_CONNECT_DB_PATH") or os.getenv("DATABASE_URL", "sqlite:///./am_connect.db")
    if raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///"):]
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class AppStore:
    """Small SQLite store so store computers survive server restarts."""

    def __init__(self, db_path: Optional[os.PathLike[str] | str] = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def save_user(self, user: Dict) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (id, username, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username = excluded.username,
                    payload = excluded.payload
                """,
                (user["id"], user["username"], json.dumps(user)),
            )

    def load_users(self) -> Dict[str, Dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT username, payload FROM users").fetchall()
        return {row["username"]: json.loads(row["payload"]) for row in rows}

    def save_device(self, device_id: str, device: Dict) -> None:
        persistable = {
            key: value
            for key, value in device.items()
            if key != "is_online"
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO devices (device_id, user_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    payload = excluded.payload
                """,
                (device_id, persistable["user_id"], json.dumps(persistable)),
            )

    def load_devices(self) -> Dict[str, Dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT device_id, payload FROM devices").fetchall()
        devices = {}
        for row in rows:
            payload = json.loads(row["payload"])
            payload["is_online"] = False
            devices[row["device_id"]] = payload
        return devices

    def delete_device(self, device_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))

    def list_devices_for_user(self, user_id: str) -> List[Dict]:
        devices = []
        for device_id, payload in self.load_devices().items():
            if payload.get("user_id") == user_id:
                devices.append({"device_id": device_id, **payload})
        return devices
