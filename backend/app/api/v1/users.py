"""
Users router — /api/v1/users/*  (admin only)

Endpoints (PRD §7.2):
  GET    /users           — List all users (paginated)
  POST   /users           — Create a new user account
  GET    /users/{id}      — Get user detail
  PATCH  /users/{id}      — Update user (role, email, password, etc.)
  DELETE /users/{id}      — Deactivate user (soft-delete, 204)
"""

import uuid

from fastapi import APIRouter, Query, Request, status

from app.api.deps import AdminUser, DBSession
from app.schemas.pagination import Page, PaginationParams
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.get(
    "",
    response_model=Page[UserResponse],
    summary="List all users (admin only)",
)
async def list_users(
    db: DBSession,
    _: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[UserResponse]:
    """Return a paginated list of all user accounts."""
    users, total = await user_service.list_users(db, page=page, page_size=page_size)
    return Page[UserResponse](
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account (admin only)",
)
async def create_user(
    body: UserCreate,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> UserResponse:
    """Create a user account. Returns 409 if email or username is already taken."""
    user = await user_service.create_user(
        body, db, actor_id=current_user.id, ip_address=_client_ip(request)
    )
    return UserResponse.model_validate(user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user detail (admin only)",
)
async def get_user(
    user_id: uuid.UUID,
    db: DBSession,
    _: AdminUser,
) -> UserResponse:
    """Fetch a single user by UUID. Returns 404 if not found."""
    user = await user_service.get_user(user_id, db)
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user (admin only)",
)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> UserResponse:
    """
    Partially update a user account (PATCH semantics — only provided fields change).
    Returns 404 if the user doesn't exist; 409 on email/username conflicts.
    """
    user = await user_service.update_user(
        user_id, body, db, actor_id=current_user.id, ip_address=_client_ip(request)
    )
    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a user account (admin only)",
)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    """
    Soft-delete a user (sets is_active=False, revokes all sessions).
    The user record and audit logs are preserved. Returns 204 No Content.
    """
    await user_service.deactivate_user(
        user_id, db, actor_id=current_user.id, ip_address=_client_ip(request)
    )
