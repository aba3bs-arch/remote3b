#!/usr/bin/env python3
"""Authentication and token helpers for AM-Connect."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

try:
    from .config import settings
except ImportError:  # pragma: no cover - allows running server/main.py directly
    from config import settings


class SecurityError(ValueError):
    """Raised when credentials or tokens are invalid."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def validate_password(password: str) -> None:
    if len(password) < settings.min_password_length:
        raise SecurityError(f"La contrasena debe tener al menos {settings.min_password_length} caracteres.")
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise SecurityError("La contrasena debe incluir letras y numeros.")


def create_access_token(user_id: str, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise SecurityError("La sesion expiro. Inicia sesion otra vez.") from exc
    except jwt.InvalidTokenError as exc:
        raise SecurityError("Token invalido.") from exc
    if payload.get("type") != "access":
        raise SecurityError("Tipo de token invalido.")
    return payload


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise SecurityError("Falta el encabezado Authorization.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise SecurityError("Authorization debe usar Bearer token.")
    return token


def new_device_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_device_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
