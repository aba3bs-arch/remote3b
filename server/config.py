#!/usr/bin/env python3
"""
Configuration module
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration"""
    
    # Server
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    ALGORITHM = os.getenv('ALGORITHM', 'HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', 7))
    
    # TLS
    USE_SSL = os.getenv('USE_SSL', 'true').lower() == 'true'
    SSL_CERT = os.getenv('SSL_CERT', 'certs/cert.pem')
    SSL_KEY = os.getenv('SSL_KEY', 'certs/key.pem')
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./am_connect.db')
    
    # Video recording
    RECORDING_FPS = int(os.getenv('RECORDING_FPS', 30))
    RECORDING_QUALITY = int(os.getenv('RECORDING_QUALITY', 80))
    RECORDING_OUTPUT_DIR = os.getenv('RECORDING_OUTPUT_DIR', './recordings')
    
    # Performance
    WORKER_COUNT = int(os.getenv('WORKER_COUNT', 4))
    KEEP_ALIVE_TIMEOUT = int(os.getenv('KEEP_ALIVE_TIMEOUT', 60))
    CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', 30))
    CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', 65536))
