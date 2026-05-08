#!/usr/bin/env python3
"""Runtime configuration for AM-Connect."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_path(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///")).expanduser()
    return Path(database_url).expanduser()


@dataclass(frozen=True)
class Settings:
    app_name: str = "AM-Connect"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = _bool_env("DEBUG", False)
    allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    )

    secret_key: str = os.getenv("SECRET_KEY", "change-this-dev-secret-before-production")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
    min_password_length: int = int(os.getenv("MIN_PASSWORD_LENGTH", "10"))
    allow_registration_after_bootstrap: bool = _bool_env(
        "ALLOW_REGISTRATION_AFTER_BOOTSTRAP",
        False,
    )

    database_path: Path = _database_path(os.getenv("DATABASE_URL", "sqlite:///./am_connect.db"))

    use_ssl: bool = _bool_env("USE_SSL", False)
    ssl_cert: Path = Path(os.getenv("SSL_CERT", "certs/cert.pem"))
    ssl_key: Path = Path(os.getenv("SSL_KEY", "certs/key.pem"))

    enable_command_execution: bool = _bool_env("ENABLE_COMMAND_EXECUTION", True)
    enable_file_transfer: bool = _bool_env("ENABLE_FILE_TRANSFER", True)
    enable_screenshots: bool = _bool_env("ENABLE_SCREENSHOTS", True)
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "45"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


settings = Settings()
