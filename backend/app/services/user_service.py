"""
User management service.

Handles all user CRUD operations called by the /users API router.
Every mutating operation writes an audit log entry.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import write_audit_log
from app.services.auth_service import revoke_all_user_tokens

log = structlog.get_logger(__name__)


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[User], int]:
    """
    Return a paginated list of all users and the total count.

    Returns:
        (users, total)
    """
    offset = (page - 1) * page_size

    count_result = await db.execute(select(func.count(User.id)))
    total: int = count_result.scalar_one()

    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = list(result.scalars().all())
    return users, total


async def get_user(user_id: uuid.UUID, db: AsyncSession) -> User:
    """Fetch a single user by UUID. Raises NotFoundError if missing."""
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User")
    return user


async def get_user_by_email(email: str, db: AsyncSession) -> User | None:
    """Fetch a user by email address, or None if not found."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(
    payload: UserCreate,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> User:
    """
    Create a new user account.

    Raises ConflictError if the email or username is already taken.
    """
    # Check uniqueness
    existing_email = await db.execute(select(User).where(User.email == payload.email))
    if existing_email.scalar_one_or_none():
        raise ConflictError(f"Email '{payload.email}' is already registered")

    existing_username = await db.execute(
        select(User).where(User.username == payload.username)
    )
    if existing_username.scalar_one_or_none():
        raise ConflictError(f"Username '{payload.username}' is already taken")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # assign UUID before audit log
    await db.refresh(user)  # load server-default timestamps

    await write_audit_log(
        db,
        action="user.created",
        resource_type="user",
        actor_id=actor_id,
        resource_id=user.id,
        payload={"email": user.email, "username": user.username, "role": user.role.value},
        ip_address=ip_address,
    )

    log.info("user_created", user_id=str(user.id), email=user.email, role=user.role.value)
    return user


async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> User:
    """
    Apply a partial update to a user.

    Raises NotFoundError if the user doesn't exist.
    Raises ConflictError on email/username uniqueness violations.
    """
    user = await get_user(user_id, db)

    changes: dict[str, Any] = {}

    if payload.email is not None and payload.email != user.email:
        collision = await db.execute(select(User).where(User.email == payload.email))
        if collision.scalar_one_or_none():
            raise ConflictError(f"Email '{payload.email}' is already in use")
        changes["email"] = {"from": user.email, "to": payload.email}
        user.email = payload.email

    if payload.username is not None and payload.username != user.username:
        collision = await db.execute(select(User).where(User.username == payload.username))
        if collision.scalar_one_or_none():
            raise ConflictError(f"Username '{payload.username}' is already taken")
        changes["username"] = {"from": user.username, "to": payload.username}
        user.username = payload.username

    if payload.role is not None and payload.role != user.role:
        changes["role"] = {"from": user.role.value, "to": payload.role.value}
        user.role = payload.role

    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = {"from": user.is_active, "to": payload.is_active}
        user.is_active = payload.is_active

    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
        changes["password"] = "updated"

    if changes:
        await db.flush()
        await db.refresh(user)
        await write_audit_log(
            db,
            action="user.updated",
            resource_type="user",
            actor_id=actor_id,
            resource_id=user.id,
            payload=changes,
            ip_address=ip_address,
        )
        log.info("user_updated", user_id=str(user.id), changes=list(changes.keys()))

    return user


async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Soft-delete a user (set is_active=False) and revoke all their sessions.

    The user record and all their audit logs are preserved.
    Raises NotFoundError if the user doesn't exist.
    """
    user = await get_user(user_id, db)

    user.is_active = False
    await db.flush()

    # Immediately invalidate all active sessions
    await revoke_all_user_tokens(user_id, db)

    await write_audit_log(
        db,
        action="user.deactivated",
        resource_type="user",
        actor_id=actor_id,
        resource_id=user.id,
        payload={"email": user.email},
        ip_address=ip_address,
    )

    log.info("user_deactivated", user_id=str(user.id), email=user.email)
