"""
Shared FastAPI dependencies.

Imported in every router with:
  from app.api.deps import CurrentUser, AdminUser, ManagerOrAdminUser, DBSession

All dependencies are type-annotated for FastAPI's dependency injection system.
"""

from typing import Annotated

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User, UserRole

log = structlog.get_logger(__name__)

# ── HTTP Bearer scheme ────────────────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)

# ── Type aliases ──────────────────────────────────────────────────────────────
DBSession = Annotated[AsyncSession, Depends(get_db)]


# ── Core user dependency ───────────────────────────────────────────────────────
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: DBSession,
) -> User:
    """
    Extract and validate the JWT from the Authorization header.
    Returns the active User ORM instance.

    Raises AuthError (401) on missing/invalid/expired token.
    Raises AuthError (401) if the user is deactivated.
    """
    if credentials is None:
        raise AuthError("Missing Authorization header. Expected: Bearer <token>")

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise AuthError(f"Invalid or expired token: {exc}") from exc

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise AuthError("Token payload missing 'sub' claim")

    user = await db.get(User, user_id)
    if user is None:
        raise AuthError("User not found")
    if not user.is_active:
        raise AuthError("Account is deactivated")

    # Bind user context to all log lines in this request
    structlog.contextvars.bind_contextvars(
        user_id=str(user.id),
        user_role=user.role.value,
    )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Role-gated dependencies ───────────────────────────────────────────────────
async def require_admin(current_user: CurrentUser) -> User:
    """Allow only admin-role users. Raises ForbiddenError (403) otherwise."""
    if current_user.role != UserRole.admin:
        raise ForbiddenError("This action requires administrator privileges")
    return current_user


async def require_manager_or_admin(current_user: CurrentUser) -> User:
    """Allow manager or admin roles. Raises ForbiddenError (403) for viewers."""
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise ForbiddenError("This action requires manager or administrator privileges")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
ManagerOrAdminUser = Annotated[User, Depends(require_manager_or_admin)]
