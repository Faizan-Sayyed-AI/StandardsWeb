"""
Authentication service.

Handles:
  - User authentication (email + password)
  - JWT access token creation
  - Refresh token lifecycle (create, rotate, revoke)
  - Password reset token lifecycle (create, confirm)
  - Session revocation on user deactivation
"""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email import send_password_reset_email
from app.core.exceptions import AuthError, AppValidationError
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User

log = structlog.get_logger(__name__)


# ── User authentication ────────────────────────────────────────────────────────
async def authenticate_user(
    email: str, password: str, db: AsyncSession
) -> User:
    """
    Verify credentials and return the active User.

    Raises AuthError on invalid credentials or inactive account.
    Does NOT update last_login here — caller is responsible after full
    token creation to avoid partial DB writes.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password")

    if not user.is_active:
        raise AuthError("Account is deactivated. Contact your administrator.")

    return user


async def update_last_login(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Stamp the user's last_login timestamp."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(last_login=datetime.now(timezone.utc))
    )


# ── Token creation ─────────────────────────────────────────────────────────────
async def create_tokens(user: User, db: AsyncSession) -> tuple[str, str]:
    """
    Create an access token + refresh token pair for the given user.

    Returns:
        (raw_access_token, raw_refresh_token)

    Stores only the hashed refresh token in the DB.
    """
    access_token = create_access_token(str(user.id), user.role.value)
    raw_refresh, refresh_hash = generate_opaque_token()

    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_token)
    await db.flush()

    return access_token, raw_refresh


# ── Token refresh ──────────────────────────────────────────────────────────────
async def refresh_access_token(raw_refresh_token: str, db: AsyncSession) -> tuple[str, str]:
    """
    Validate the refresh token, revoke it, and issue a new pair (rotation).

    Returns:
        (new_access_token, new_raw_refresh_token)

    Raises AuthError if the token is invalid, expired, or revoked.
    """
    token_hash = hash_token(raw_refresh_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None or stored.is_revoked:
        raise AuthError("Invalid or already-used refresh token")

    if stored.expires_at < datetime.now(timezone.utc):
        raise AuthError("Refresh token has expired. Please log in again.")

    # Revoke the used token (single-use rotation)
    stored.is_revoked = True
    await db.flush()

    # Load the user for the new token
    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AuthError("User account not found or deactivated")

    return await create_tokens(user, db)


# ── Token revocation ───────────────────────────────────────────────────────────
async def revoke_refresh_token(raw_refresh_token: str, db: AsyncSession) -> None:
    """Mark a refresh token as revoked (logout)."""
    token_hash = hash_token(raw_refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored and not stored.is_revoked:
        stored.is_revoked = True
        await db.flush()


async def revoke_all_user_tokens(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Revoke all active refresh tokens for a user (called on deactivation)."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False)  # noqa: E712
        .values(is_revoked=True)
    )


# ── Password reset ─────────────────────────────────────────────────────────────
async def create_password_reset_token(email: str, db: AsyncSession) -> None:
    """
    Generate a single-use password reset token and send it via email.

    Does NOT reveal whether the email exists (returns None either way).
    In M1 the email is logged instead of sent — see core/email.py.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        # Deliberate no-op — do not reveal account existence
        log.info("password_reset_requested_unknown_email", email=email)
        return

    raw_token, token_hash = generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    await db.flush()

    # M1: email is logged; M5: replaced with real SMTP send
    await send_password_reset_email(to=email, reset_token=raw_token)
    log.info("password_reset_token_created", user_id=str(user.id))


async def confirm_password_reset(raw_token: str, new_password: str, db: AsyncSession) -> None:
    """
    Validate the reset token and update the user's password.

    Raises AuthError if the token is invalid, expired, or already used.
    """
    token_hash = hash_token(raw_token)

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None or stored.is_used:
        raise AuthError("Invalid or already-used password reset token")

    if stored.expires_at < datetime.now(timezone.utc):
        raise AuthError("Password reset token has expired. Please request a new one.")

    # Mark token as used (single-use)
    stored.is_used = True

    # Update the user's password
    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AuthError("User account not found or deactivated")

    user.hashed_password = hash_password(new_password)
    await db.flush()

    # Revoke all existing sessions (force re-login with new password)
    await revoke_all_user_tokens(user.id, db)

    log.info("password_reset_confirmed", user_id=str(user.id))
