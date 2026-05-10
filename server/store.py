#!/usr/bin/env python3
"""SQLite persistence layer for AM-Connect."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    device_secret_hash TEXT NOT NULL,
                    platform TEXT,
                    hostname TEXT,
                    agent_version TEXT,
                    created_at TEXT NOT NULL,
                    last_seen TEXT,
                    FOREIGN KEY(owner_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS link_codes (
                    code TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    requested_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    used_device_id TEXT,
                    FOREIGN KEY(owner_user_id) REFERENCES users(id),
                    FOREIGN KEY(used_device_id) REFERENCES devices(id)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    device_id TEXT,
                    action TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                );
                """
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    def count_users(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()
            return int(row["total"])

    def create_user(self, username: str, password_hash: str) -> dict[str, Any]:
        user_id = f"user_{uuid4().hex}"
        created_at = utc_now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO users (id, username, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, username, password_hash, created_at),
            )
        return {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
            "created_at": created_at,
            "last_login": None,
        }

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return self._row_to_dict(row)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._row_to_dict(row)

    def update_last_login(self, user_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE users SET last_login = ? WHERE id = ?", (utc_now(), user_id))

    def create_device(self, owner_user_id: str, name: str, secret_hash: str) -> dict[str, Any]:
        device_id = f"dev_{uuid4().hex}"
        created_at = utc_now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO devices (
                    id, owner_user_id, name, device_secret_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, owner_user_id, name, secret_hash, created_at),
            )
        return {
            "id": device_id,
            "owner_user_id": owner_user_id,
            "name": name,
            "created_at": created_at,
            "last_seen": None,
            "platform": None,
            "hostname": None,
            "agent_version": None,
        }

    def create_link_code(self, code: str, owner_user_id: str, requested_name: str, expires_at: str) -> dict[str, Any]:
        created_at = utc_now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO link_codes (code, owner_user_id, requested_name, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (code, owner_user_id, requested_name, created_at, expires_at),
            )
        return {
            "code": code,
            "owner_user_id": owner_user_id,
            "requested_name": requested_name,
            "created_at": created_at,
            "expires_at": expires_at,
            "used_at": None,
            "used_device_id": None,
        }

    def get_link_code(self, code: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM link_codes WHERE code = ?", (code,)).fetchone()
            return self._row_to_dict(row)

    def mark_link_code_used(self, code: str, device_id: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE link_codes
                SET used_at = ?, used_device_id = ?
                WHERE code = ?
                """,
                (utc_now(), device_id, code),
            )

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
            return self._row_to_dict(row)

    def list_devices(self, owner_user_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, owner_user_id, name, platform, hostname, agent_version, created_at, last_seen
                FROM devices
                WHERE owner_user_id = ?
                ORDER BY created_at DESC
                """,
                (owner_user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def touch_device(self, device_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (utc_now(), device_id))

    def update_device_metadata(self, device_id: str, metadata: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE devices
                SET platform = COALESCE(?, platform),
                    hostname = COALESCE(?, hostname),
                    agent_version = COALESCE(?, agent_version),
                    last_seen = ?
                WHERE id = ?
                """,
                (
                    metadata.get("platform"),
                    metadata.get("hostname"),
                    metadata.get("agent_version"),
                    utc_now(),
                    device_id,
                ),
            )

    def log_event(
        self,
        action: str,
        user_id: str | None = None,
        device_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO audit_events (id, user_id, device_id, action, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"audit_{uuid4().hex}", user_id, device_id, action, detail, utc_now()),
            )
