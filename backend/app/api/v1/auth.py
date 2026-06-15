"""
Auth router — /api/v1/auth/*

Endpoints (PRD §7.2):
  POST /auth/login                  — Exchange credentials for JWT + sets httpOnly refresh cookie
  POST /auth/refresh                — Rotate refresh token from cookie, issue new access token
  POST /auth/logout                 — Revoke refresh token (reads from cookie or body)
  POST /auth/password-reset/request — Send password reset email (M1: logged only)
  POST /auth/password-reset/confirm — Validate token, set new password

M3 change: refresh_token is now delivered via httpOnly cookie (SameSite=Lax, Path=/api/v1/auth)
in addition to the response body for backwards compatibility with API clients.
The cookie approach is required by the React frontend (PRD M3 security requirement).
"""

from fastapi import APIRouter, Request, Response, status

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

# Refresh token cookie config
_COOKIE_NAME = "ists_refresh_token"
_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds
_COOKIE_PATH = "/api/v1/auth"        # scope cookie to auth endpoints only


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the httpOnly refresh token cookie on a response."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        path=_COOKIE_PATH,
        max_age=_COOKIE_MAX_AGE,
        secure=False,  # set True in production (HTTPS only)
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie (logout)."""
    response.delete_cookie(key=_COOKIE_NAME, path=_COOKIE_PATH)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login — returns access token, sets httpOnly refresh cookie",
)
async def login(
    body: LoginRequest, request: Request, response: Response, db: DBSession
) -> TokenResponse:
    """
    Authenticate with email + password.
    Returns:
      - Body: JWT access token (8h) + refresh token (for API client compatibility).
      - Cookie: httpOnly refresh token (7d) used by the React frontend.
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

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue a new access token",
)
async def refresh(
    response: Response,
    request: Request,
    db: DBSession,
    body: RefreshRequest | None = None,
) -> AccessTokenResponse:
    """
    Exchange a valid refresh token for a new access token + new refresh token.
    Token is read from the httpOnly cookie first; falls back to the request body
    for backwards-compatible API client use.
    The old refresh token is immediately revoked (single-use rotation).
    """
    # Prefer cookie; fall back to body for API clients
    raw_token = request.cookies.get(_COOKIE_NAME)
    if not raw_token and body:
        raw_token = body.refresh_token

    if not raw_token:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Refresh token missing", "code": "refresh_token_missing"},
        )

    access_token, new_refresh_token = await auth_service.refresh_access_token(raw_token, db)
    _set_refresh_cookie(response, new_refresh_token)
    return AccessTokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token and clear cookie (logout)",
)
async def logout(
    response: Response,
    request: Request,
    db: DBSession,
    body: LogoutRequest | None = None,
) -> None:
    """
    Revoke the refresh token (from cookie or body) and clear the cookie.
    The associated access token expires naturally within 8h.
    """
    raw_token = request.cookies.get(_COOKIE_NAME)
    if not raw_token and body:
        raw_token = body.refresh_token

    if raw_token:
        await auth_service.revoke_refresh_token(raw_token, db)

    _clear_refresh_cookie(response)


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
