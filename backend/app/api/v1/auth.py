"""
Auth router — /api/v1/auth/*

Endpoints (PRD §7.2):
  POST /auth/login                  — Exchange credentials for JWT + refresh token
  POST /auth/refresh                — Rotate refresh token, issue new access token
  POST /auth/logout                 — Revoke refresh token
  POST /auth/password-reset/request — Send password reset email (M1: logged only)
  POST /auth/password-reset/confirm — Validate token, set new password
"""

from fastapi import APIRouter, Request, status

from app.api.deps import DBSession
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services import auth_service
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain access + refresh tokens",
)
async def login(body: LoginRequest, request: Request, db: DBSession) -> TokenResponse:
    """
    Authenticate with email + password.
    Returns a JWT access token (8h) and an opaque refresh token (7d).
    """
    user = await auth_service.authenticate_user(body.email, body.password, db)
    access_token, refresh_token = await auth_service.create_tokens(user, db)
    await auth_service.update_last_login(user.id, db)

    await write_audit_log(
        db,
        action="user.login",
        resource_type="user",
        actor_id=user.id,
        resource_id=user.id,
        payload={"outcome": "success"},
        ip_address=_client_ip(request),
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue a new access token",
)
async def refresh(body: RefreshRequest, db: DBSession) -> AccessTokenResponse:
    """
    Exchange a valid refresh token for a new access token + new refresh token.
    The old refresh token is immediately revoked (single-use rotation).
    """
    access_token, new_refresh_token = await auth_service.refresh_access_token(
        body.refresh_token, db
    )
    return AccessTokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token (logout)",
)
async def logout(body: LogoutRequest, db: DBSession) -> None:
    """
    Revoke the provided refresh token.
    The associated access token will expire naturally (max 8h).
    """
    await auth_service.revoke_refresh_token(body.refresh_token, db)


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email",
)
async def password_reset_request(body: PasswordResetRequest, db: DBSession) -> dict:
    """
    Trigger a password reset email for the given address.
    Always returns 202 Accepted regardless of whether the email exists
    (prevents account enumeration).
    In M1: the reset token is logged to stdout instead of emailed.
    """
    await auth_service.create_password_reset_token(body.email, db)
    return {"detail": "If this email is registered, a reset link has been sent."}


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
    summary="Confirm password reset with token",
)
async def password_reset_confirm(body: PasswordResetConfirm, db: DBSession) -> dict:
    """
    Validate the reset token and set a new password.
    All existing sessions for the user are immediately revoked.
    """
    await auth_service.confirm_password_reset(body.token, body.new_password, db)
    return {"detail": "Password updated successfully. Please log in with your new password."}
