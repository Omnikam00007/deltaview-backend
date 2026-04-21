import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from redis.asyncio import Redis

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str) -> str:
    return _create_token(
        {"sub": subject, "type": "access"},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        {"sub": subject, "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Raises JWTError if the token is invalid or expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# --------------- Password Reset Tokens (Redis-backed) ---------------

_RESET_PREFIX = "password_reset:"


def _generate_reset_token() -> str:
    """Generate a URL-safe random token."""
    return secrets.token_urlsafe(32)


async def create_password_reset_token(redis: Redis, email: str) -> str:
    """Create a reset token, store in Redis with TTL, return the token string."""
    token = _generate_reset_token()
    key = f"{_RESET_PREFIX}{token}"
    await redis.set(key, email, ex=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES * 60)
    return token


async def verify_password_reset_token(redis: Redis, token: str) -> str | None:
    """Verify a reset token. Returns the associated email or None if invalid/expired."""
    key = f"{_RESET_PREFIX}{token}"
    email = await redis.get(key)
    if email:
        await redis.delete(key)  # single use — delete after verification
    return email


# --------------- Registration Tokens (Redis-backed) ---------------

import json

_REGISTRATION_PREFIX = "registration_otp:"

def _generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)

async def create_registration_otp(redis: Redis, email: str, data: dict) -> str:
    """Create a 6-digit OTP, store registration data in Redis with TTL (15 mins), return the OTP."""
    otp = _generate_otp()
    key = f"{_REGISTRATION_PREFIX}{email}"
    # Store the payload and the OTP
    payload = {
        "otp": otp,
        "data": data,
    }
    await redis.set(key, json.dumps(payload), ex=15 * 60)
    return otp

async def get_pending_registration(redis: Redis, email: str) -> dict | None:
    """Fetch pending registration data, returning None if not found or expired."""
    key = f"{_REGISTRATION_PREFIX}{email}"
    raw = await redis.get(key)
    if not raw:
        return None
    return json.loads(raw)

async def verify_registration_otp(redis: Redis, email: str, otp: str) -> dict | None:
    """Verify a registration OTP for a given email. Returns the user data or None if invalid/expired."""
    key = f"{_REGISTRATION_PREFIX}{email}"
    raw = await redis.get(key)
    if not raw:
        return None
    
    payload = json.loads(raw)
    if payload.get("otp") == otp:
        await redis.delete(key)  # single use — delete after successful verification
        return payload.get("data")
    
    return None

