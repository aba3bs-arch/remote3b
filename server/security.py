#!/usr/bin/env python3
"""
Security Module - Handles authentication, encryption, and security features
Includes JWT, 2FA with TOTP, BCrypt password hashing, and data encryption
"""

import os
import json
import secrets
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional

import bcrypt
import jwt
import pyotp
import qrcode
from io import BytesIO
import base64
from cryptography.fernet import Fernet


class SecurityManager:
    """
    Comprehensive security management for AM-CONNECT
    Handles user authentication, token generation, 2FA, and data encryption
    """
    
    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
        self.algorithm = os.getenv('ALGORITHM', 'HS256')
        self.access_token_expire = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))
        self.refresh_token_expire = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', 7))
        
        # In-memory user store (replace with database in production)
        self.users = {}
        self.devices = {}
        self.refresh_tokens = {}
        
        # Encryption key for sensitive data
        self.encryption_key = os.getenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
        self.cipher = Fernet(self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key)
    
    # ===== PASSWORD SECURITY =====
    
    def hash_password(self, password: str) -> str:
        """
        Hash password using BCrypt
        
        Args:
            password: Plain text password
        
        Returns:
            Hashed password
        """
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        Verify password against hash
        
        Args:
            password: Plain text password
            hashed: Hashed password
        
        Returns:
            True if password matches
        """
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    def validate_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        Validate password strength
        
        Args:
            password: Password to validate
        
        Returns:
            Tuple of (is_valid, message)
        """
        if len(password) < 12:
            return False, "Password must be at least 12 characters"
        
        if not any(c.isupper() for c in password):
            return False, "Password must contain uppercase letters"
        
        if not any(c.islower() for c in password):
            return False, "Password must contain lowercase letters"
        
        if not any(c.isdigit() for c in password):
            return False, "Password must contain numbers"
        
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            return False, "Password must contain special characters"
        
        return True, "Password is strong"
    
    # ===== USER MANAGEMENT =====
    
    def register_user(self, username: str, email: str, password: str) -> Dict:
        """
        Register new user
        
        Args:
            username: Username
            email: Email address
            password: Password
        
        Returns:
            User data
        
        Raises:
            ValueError: If validation fails
        """
        # Validate inputs
        if username in self.users:
            raise ValueError("Username already exists")
        
        if any(u['email'] == email for u in self.users.values()):
            raise ValueError("Email already registered")
        
        # Validate password strength
        is_valid, message = self.validate_password_strength(password)
        if not is_valid:
            raise ValueError(message)
        
        # Create user
        user_id = secrets.token_hex(8)
        user = {
            'id': user_id,
            'username': username,
            'email': email,
            'password_hash': self.hash_password(password),
            'two_factor_enabled': False,
            'two_factor_secret': None,
            'created_at': datetime.now().isoformat(),
            'last_login': None
        }
        
        self.users[username] = user
        return user
    
    def login_user(self, username: str, password: str, totp_code: Optional[str] = None) -> Tuple[Dict, Dict]:
        """
        Authenticate user and generate tokens
        
        Args:
            username: Username
            password: Password
            totp_code: TOTP code if 2FA is enabled
        
        Returns:
            Tuple of (user, tokens)
        
        Raises:
            ValueError: If authentication fails
        """
        # Find user
        if username not in self.users:
            raise ValueError("Invalid username or password")
        
        user = self.users[username]
        
        # Verify password
        if not self.verify_password(password, user['password_hash']):
            raise ValueError("Invalid username or password")
        
        # Verify 2FA if enabled
        if user['two_factor_enabled']:
            if not totp_code:
                raise ValueError("2FA code required")
            
            if not self.verify_totp(user['two_factor_secret'], totp_code):
                raise ValueError("Invalid 2FA code")
        
        # Generate tokens
        access_token = self.create_access_token(user['id'])
        refresh_token = self.create_refresh_token(user['id'])
        
        # Update last login
        user['last_login'] = datetime.now().isoformat()
        
        return user, {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'bearer'
        }
    
    # ===== JWT TOKENS =====
    
    def create_access_token(self, user_id: str) -> str:
        """
        Create access token
        
        Args:
            user_id: User ID
        
        Returns:
            JWT access token
        """
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire)
        payload = {
            'sub': user_id,
            'type': 'access',
            'exp': expire,
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        Create refresh token
        
        Args:
            user_id: User ID
        
        Returns:
            JWT refresh token
        """
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire)
        payload = {
            'sub': user_id,
            'type': 'refresh',
            'exp': expire,
            'iat': datetime.utcnow(),
            'jti': secrets.token_hex(16)  # JWT ID for revocation
        }
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        self.refresh_tokens[payload['jti']] = True
        return token
    
    def create_device_token(self, device_id: str, user_id: str) -> str:
        """
        Create device token
        
        Args:
            device_id: Device ID
            user_id: User ID
        
        Returns:
            JWT device token
        """
        expire = datetime.utcnow() + timedelta(days=365)  # Long expiration for devices
        payload = {
            'sub': device_id,
            'user_id': user_id,
            'type': 'device',
            'exp': expire,
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Dict:
        """
        Verify and decode token
        
        Args:
            token: JWT token
        
        Returns:
            Token payload
        
        Raises:
            ValueError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
    
    # ===== TWO-FACTOR AUTHENTICATION =====
    
    def enable_2fa(self, user_id: str) -> Tuple[str, str]:
        """
        Enable 2FA for user
        
        Args:
            user_id: User ID
        
        Returns:
            Tuple of (secret, QR code as base64)
        
        Raises:
            ValueError: If user not found
        """
        # Find user
        user = next((u for u in self.users.values() if u['id'] == user_id), None)
        if not user:
            raise ValueError("User not found")
        
        # Generate secret
        secret = pyotp.random_base32()
        user['two_factor_secret'] = secret
        
        # Generate QR code
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name=user['email'],
            issuer_name=os.getenv('TOTP_ISSUER', 'AM-CONNECT')
        )
        
        qr = qrcode.QRCode()
        qr.add_data(uri)
        qr.make()
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return secret, f"data:image/png;base64,{qr_code_base64}"
    
    def confirm_2fa(self, user_id: str, totp_code: str) -> bool:
        """
        Confirm 2FA setup
        
        Args:
            user_id: User ID
            totp_code: TOTP code to verify
        
        Returns:
            True if confirmed
        
        Raises:
            ValueError: If verification fails
        """
        user = next((u for u in self.users.values() if u['id'] == user_id), None)
        if not user or not user['two_factor_secret']:
            raise ValueError("2FA not in progress")
        
        if not self.verify_totp(user['two_factor_secret'], totp_code):
            raise ValueError("Invalid 2FA code")
        
        user['two_factor_enabled'] = True
        return True
    
    def verify_totp(self, secret: str, totp_code: str, window: int = 1) -> bool:
        """
        Verify TOTP code
        
        Args:
            secret: TOTP secret
            totp_code: Code to verify
            window: Time window in steps (default 1)
        
        Returns:
            True if valid
        """
        totp = pyotp.TOTP(secret)
        return totp.verify(totp_code, valid_window=window)
    
    # ===== DATA ENCRYPTION =====
    
    def encrypt_data(self, data: str) -> str:
        """
        Encrypt sensitive data
        
        Args:
            data: Data to encrypt
        
        Returns:
            Encrypted data (base64 encoded)
        """
        encrypted = self.cipher.encrypt(data.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decrypt sensitive data
        
        Args:
            encrypted_data: Encrypted data (base64 encoded)
        
        Returns:
            Decrypted data
        """
        data = base64.b64decode(encrypted_data.encode())
        return self.cipher.decrypt(data).decode()
