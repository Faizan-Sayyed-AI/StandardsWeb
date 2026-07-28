"""
API key pool management service.

Owns the mapping of rss_feeds → api_keys: which key a feed is assigned to,
how a key is picked for a new feed, and how feeds get moved off a key that's
being retired or has failed.

All mutating operations write an audit log entry.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret
from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.models.api_key import ApiKey, ApiKeyStatus
from app.models.rss_feed import RssFeed
from app.schemas.api_key import ApiKeyCreate, ApiKeyUpdate
from app.services.audit_service import write_audit_log

log = structlog.get_logger(__name__)


async def feed_counts_by_key(db: AsyncSession) -> dict[uuid.UUID, int]:
    """Return {api_key_id: assigned_feed_count} for every key that has feeds."""
    result = await db.execute(
        select(RssFeed.api_key_id, func.count(RssFeed.id))
        .where(RssFeed.api_key_id.isnot(None))
        .group_by(RssFeed.api_key_id)
    )
    return {row[0]: row[1] for row in result.all()}


async def pick_key_with_spare_capacity(
    db: AsyncSession,
    *,
    exclude_key_id: uuid.UUID | None = None,
) -> ApiKey:
    """
    Return the active key with the most spare capacity (least-loaded first).

    This is the single point that decides "which key does this feed belong
    to" — used both for new feed creation and for moving feeds off a
    retired/unhealthy key, so the two paths can't drift apart.

    Raises AppValidationError if no active key has room.
    """
    counts = await feed_counts_by_key(db)

    result = await db.execute(
        select(ApiKey).where(ApiKey.status == ApiKeyStatus.active)
    )
    candidates = [k for k in result.scalars().all() if k.id != exclude_key_id]

    best: ApiKey | None = None
    best_spare = -1
    for key in candidates:
        spare = key.capacity - counts.get(key.id, 0)
        if spare > 0 and spare > best_spare:
            best = key
            best_spare = spare

    if best is None:
        raise AppValidationError(
            "All active API keys are at capacity. Add a new API key before "
            "creating more feeds."
        )
    return best


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def list_api_keys(db: AsyncSession) -> list[tuple[ApiKey, int]]:
    """Return every API key paired with its current assigned-feed count."""
    counts = await feed_counts_by_key(db)
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.asc()))
    return [(key, counts.get(key.id, 0)) for key in result.scalars().all()]


async def get_api_key(api_key_id: uuid.UUID, db: AsyncSession) -> ApiKey:
    key = await db.get(ApiKey, api_key_id)
    if key is None:
        raise NotFoundError("ApiKey")
    return key


async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
) -> ApiKey:
    existing = await db.execute(select(ApiKey).where(ApiKey.label == payload.label))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"An API key with label '{payload.label}' already exists")

    key = ApiKey(
        label=payload.label,
        key_value=encrypt_secret(payload.key_value),
        capacity=payload.capacity,
        notes=payload.notes,
    )
    db.add(key)
    await db.flush()

    await write_audit_log(
        db,
        action="api_key.created",
        resource_type="api_key",
        actor_id=actor_id,
        resource_id=key.id,
        payload={"label": key.label, "capacity": key.capacity},
    )
    log.info("api_key_created", api_key_id=str(key.id), label=key.label)
    return key


async def update_api_key(
    api_key_id: uuid.UUID,
    payload: ApiKeyUpdate,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
) -> ApiKey:
    key = await get_api_key(api_key_id, db)
    changes: dict = {}

    if payload.label is not None and payload.label != key.label:
        existing = await db.execute(
            select(ApiKey).where(ApiKey.label == payload.label, ApiKey.id != api_key_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"An API key with label '{payload.label}' already exists")
        changes["label"] = {"from": key.label, "to": payload.label}
        key.label = payload.label

    if payload.key_value is not None:
        changes["key_value"] = "rotated"
        key.key_value = encrypt_secret(payload.key_value)

    if payload.capacity is not None and payload.capacity != key.capacity:
        changes["capacity"] = {"from": key.capacity, "to": payload.capacity}
        key.capacity = payload.capacity

    if payload.status is not None and payload.status != key.status:
        changes["status"] = {"from": key.status.value, "to": payload.status.value}
        key.status = payload.status

    if payload.notes is not None:
        changes["notes"] = {"from": key.notes, "to": payload.notes}
        key.notes = payload.notes

    if changes:
        await db.flush()
        await write_audit_log(
            db,
            action="api_key.updated",
            resource_type="api_key",
            actor_id=actor_id,
            resource_id=key.id,
            payload=changes,
        )
        log.info("api_key_updated", api_key_id=str(key.id), changes=list(changes.keys()))

    return key


async def delete_api_key(
    api_key_id: uuid.UUID,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    """
    Delete an API key. Raises ConflictError if feeds are still assigned to it
    — reassign them first via reassign_feeds_off_key().
    """
    key = await get_api_key(api_key_id, db)

    count_result = await db.execute(
        select(func.count(RssFeed.id)).where(RssFeed.api_key_id == api_key_id)
    )
    if count_result.scalar_one() > 0:
        raise ConflictError(
            "This API key still has feeds assigned to it. "
            "Reassign them before deleting the key."
        )

    await write_audit_log(
        db,
        action="api_key.deleted",
        resource_type="api_key",
        actor_id=actor_id,
        resource_id=key.id,
        payload={"label": key.label},
    )
    await db.delete(key)
    log.info("api_key_deleted", api_key_id=str(api_key_id), label=key.label)


async def reassign_feeds_off_key(
    source_key_id: uuid.UUID,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
) -> int:
    """
    Move every feed currently on source_key_id onto other active keys with
    spare capacity (least-loaded first). Used before retiring/disabling a key.

    Raises AppValidationError if remaining active keys don't have enough
    combined spare capacity to absorb all of this key's feeds.
    """
    source_key = await get_api_key(source_key_id, db)

    result = await db.execute(select(RssFeed).where(RssFeed.api_key_id == source_key_id))
    feeds = list(result.scalars().all())

    moved = 0
    for feed in feeds:
        target = await pick_key_with_spare_capacity(db, exclude_key_id=source_key_id)
        feed.api_key_id = target.id
        moved += 1

    if moved:
        await db.flush()
        await write_audit_log(
            db,
            action="api_key.feeds_reassigned",
            resource_type="api_key",
            actor_id=actor_id,
            resource_id=source_key_id,
            payload={"from_label": source_key.label, "feed_count": moved},
        )
        log.info("api_key_feeds_reassigned", source_key_id=str(source_key_id), count=moved)

    return moved


# ── Health tracking (called from tasks/feeds.py) ─────────────────────────────
async def record_key_success(api_key_id: uuid.UUID, db: AsyncSession) -> None:
    """Mark a successful call: reset failure streak and self-heal from rate_limited."""
    key = await db.get(ApiKey, api_key_id)
    if key is None:
        return
    key.last_used_at = datetime.now(timezone.utc)
    key.consecutive_failures = 0
    if key.status == ApiKeyStatus.rate_limited:
        key.status = ApiKeyStatus.active


async def record_key_failure(
    api_key_id: uuid.UUID,
    db: AsyncSession,
    *,
    new_status: ApiKeyStatus | None = None,
) -> bool:
    """
    Record a failed call. If new_status is given (rate_limited/expired) and
    the key isn't already in a non-active state, transition it.

    Returns True if this call caused a status transition (i.e. an alert
    should be raised), False otherwise.
    """
    key = await db.get(ApiKey, api_key_id)
    if key is None:
        return False

    key.last_failure_at = datetime.now(timezone.utc)
    key.consecutive_failures += 1

    if new_status is not None and key.status == ApiKeyStatus.active:
        key.status = new_status
        return True
    return False
