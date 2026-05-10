#!/usr/bin/env python3
"""Pydantic request and response models for AM-Connect."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=10, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class DeviceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class AgentLinkRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=20)
    device_name: str | None = Field(default=None, max_length=80)
    platform: str | None = Field(default=None, max_length=200)
    hostname: str | None = Field(default=None, max_length=200)
    agent_version: str | None = Field(default=None, max_length=50)


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4000)
    timeout: int = Field(default=30, ge=1, le=300)


class ScreenshotRequest(BaseModel):
    quality: int = Field(default=75, ge=20, le=95)


class FileUploadRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=2000)
    content_base64: str = Field(..., min_length=1)
    overwrite: bool = True
