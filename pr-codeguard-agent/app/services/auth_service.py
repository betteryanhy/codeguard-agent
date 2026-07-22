import hashlib
import uuid
from datetime import datetime, timedelta

import jwt

from app.config import settings


def hash_password(password: str) -> str:
    """Hash a password with a random salt."""
    salt = uuid.uuid4().hex
    return hashlib.sha256(salt.encode() + password.encode()).hexdigest() + ":" + salt


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hashed string."""
    try:
        hash_str, salt = hashed.split(":")
        return hash_str == hashlib.sha256(salt.encode() + password.encode()).hexdigest()
    except (ValueError, AttributeError):
        return False


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
