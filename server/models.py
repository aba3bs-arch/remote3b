#!/usr/bin/env python3
"""
Pydantic models for data validation
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """User registration model"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=12)


class UserLogin(BaseModel):
    """User login model"""
    username: str
    password: str
    totp_code: Optional[str] = None


class DeviceRegister(BaseModel):
    """Device registration model"""
    device_name: str
    os: str


class CommandRequest(BaseModel):
    """Command execution request"""
    command: str
    timeout: int = 30


class FileTransferRequest(BaseModel):
    """File transfer request"""
    filepath: str
    action: str  # download, upload, list


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ScreenshotRequest(BaseModel):
    """Screenshot request"""
    quality: int = Field(80, ge=1, le=100)
