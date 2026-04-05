import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import bearer_scheme, get_current_user
from app.core.config import settings
from app.core.email import build_password_reset_email, send_email
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    verify_password,
    verify_password_reset_token,
)
from app.database import get_db
from app.db.tokens import revoked_tokens
from app.db.users import create_user, get_user_by_email, get_user_by_id, update_user_password
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


# --------------- Endpoints ---------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and immediately return tokens."""
    user = await create_user(db, email=body.email, password=body.password, full_name=body.full_name)
    if user is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT tokens."""
    user = await get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Invalidate the current access token."""
    revoked_tokens.add(creds.credentials)
    return {"message": "Successfully logged out"}


@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Issue a new access/refresh token pair. Old refresh token is revoked (rotation)."""
    if body.refresh_token in revoked_tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError
        user = await get_user_by_id(db, uuid.UUID(payload["sub"]))
        if not user:
            raise ValueError
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    revoked_tokens.add(body.refresh_token)
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
    )


# --------------- Password Reset ---------------

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Request a password reset link. Always returns 200 to prevent email enumeration."""
    user = await get_user_by_email(db, body.email)
    if user:
        token = await create_password_reset_token(redis, user.email)
        reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?token={token}"
        html = build_password_reset_email(reset_link)
        await send_email(to=user.email, subject="Reset Your DeltaView Password", html_body=html)

    # Always return success to prevent email enumeration
    return MessageResponse(message="If that email is registered, a password reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Reset the user's password using a valid reset token."""
    email = await verify_password_reset_token(redis, body.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    await update_user_password(db, user, body.new_password)
    return MessageResponse(message="Your password has been reset successfully. You can now log in.")
