import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import bearer_scheme, get_current_user
from app.core.config import settings
from app.core.email import build_password_reset_email, build_verification_email, send_email
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    verify_password,
    verify_password_reset_token,
    create_registration_otp,
    verify_registration_otp,
    get_pending_registration,
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
    VerifyEmailRequest,
    ResendVerifyEmailRequest,
)

router = APIRouter()


# --------------- Endpoints ---------------

@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    """Register a new user and send an OTP to email."""
    # Check if already exists in DB
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    
    # Store pending data and get OTP
    data = {"email": body.email, "password": body.password, "full_name": body.full_name}
    otp = await create_registration_otp(redis, body.email, data)
    
    # Send email
    html = build_verification_email(otp)
    await send_email(to=body.email, subject="Verify Your DeltaView Email", html_body=html)
    
    return MessageResponse(message="OTP sent to your email. Please verify.")


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    """Verify email via OTP and log the user in."""
    data = await verify_registration_otp(redis, body.email, body.otp)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification code")
    
    # Create the user in DB now
    user = await create_user(db, email=data["email"], password=data["password"], full_name=data.get("full_name"))
    if not user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/resend-verify-email", response_model=MessageResponse)
async def resend_verify_email(body: ResendVerifyEmailRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    """Resend the verification code to the email."""
    # Check if already in DB
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified and registered")

    # Fetch pending data
    data = await get_pending_registration(redis, body.email)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending registration found for this email")
    
    # In get_pending_registration, it returns the whole dict containing 'otp' and 'data'
    user_data = data.get("data")
    if not user_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pending registration payload")
    
    # Generate new OTP and reset TTL
    otp = await create_registration_otp(redis, body.email, user_data)
    
    # Send email
    html = build_verification_email(otp)
    await send_email(to=body.email, subject="Verify Your DeltaView Email", html_body=html)
    
    return MessageResponse(message="A new verification code has been sent.")


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
