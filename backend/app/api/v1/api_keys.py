"""
API keys router — /api/v1/api-keys/*

Manages the pool of rss2json.com API keys that RSS feeds are distributed
across. See app/services/api_key_service.py for the assignment logic.

Endpoints:
  GET    /api-keys                    — List all keys + assigned feed counts (admin)
  POST   /api-keys                    — Add a new key to the pool            (admin)
  PATCH  /api-keys/{id}                — Update label/capacity/status/rotate key (admin)
  DELETE /api-keys/{id}                — Remove a key (must have 0 feeds)    (admin, 204)
  POST   /api-keys/{id}/reassign-feeds — Move this key's feeds elsewhere     (admin)
"""

import uuid

from fastapi import APIRouter, status

from app.api.deps import AdminUser, DBSession
from app.models.api_key import ApiKey
from app.schemas.api_key import ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate, ReassignResponse
from app.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


def _to_response(key: ApiKey, assigned_feed_count: int) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        label=key.label,
        capacity=key.capacity,
        status=key.status,
        assigned_feed_count=assigned_feed_count,
        consecutive_failures=key.consecutive_failures,
        last_used_at=key.last_used_at,
        last_failure_at=key.last_failure_at,
        notes=key.notes,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


@router.get(
    "",
    response_model=list[ApiKeyResponse],
    summary="List API keys with their assigned feed counts (admin)",
)
async def list_api_keys(db: DBSession, _: AdminUser) -> list[ApiKeyResponse]:
    pairs = await api_key_service.list_api_keys(db)
    return [_to_response(key, count) for key, count in pairs]


@router.post(
    "",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new API key to the pool (admin)",
)
async def create_api_key(
    body: ApiKeyCreate,
    db: DBSession,
    current_user: AdminUser,
) -> ApiKeyResponse:
    """
    Add a key with 0 feeds assigned yet — new feeds will start being routed
    to it (along with any other active key with spare capacity) as soon as
    it exists. Returns 409 if the label is already taken.
    """
    key = await api_key_service.create_api_key(body, db, actor_id=current_user.id)
    await db.commit()
    return _to_response(key, 0)


@router.patch(
    "/{api_key_id}",
    response_model=ApiKeyResponse,
    summary="Update an API key (admin)",
)
async def update_api_key(
    api_key_id: uuid.UUID,
    body: ApiKeyUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> ApiKeyResponse:
    """
    Partially update a key (PATCH semantics). Set key_value to rotate the
    secret; set status to manually disable/re-enable a key. Returns 404 if
    not found; 409 on label conflict.
    """
    key = await api_key_service.update_api_key(api_key_id, body, db, actor_id=current_user.id)
    # Read the feed count BEFORE committing — this update never touches
    # rss_feeds, so the count can't change either way, and running another
    # query on this session after an explicit mid-handler commit crashes
    # under the real ASGI/middleware stack (MissingGreenlet), even though it
    # works fine calling the service functions directly.
    counts = await api_key_service.feed_counts_by_key(db)
    await db.commit()
    return _to_response(key, counts.get(key.id, 0))


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API key (admin)",
)
async def delete_api_key(
    api_key_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    """
    Delete a key. Returns 409 if it still has feeds assigned — call
    POST /api-keys/{id}/reassign-feeds first.
    """
    await api_key_service.delete_api_key(api_key_id, db, actor_id=current_user.id)
    await db.commit()


@router.post(
    "/{api_key_id}/reassign-feeds",
    response_model=ReassignResponse,
    summary="Move all feeds off this key onto other active keys (admin)",
)
async def reassign_feeds(
    api_key_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> ReassignResponse:
    """
    Moves every feed currently assigned to this key onto other active keys
    with spare capacity (least-loaded first). Use before disabling or
    deleting a key. Returns 422 if remaining active keys can't absorb all
    of this key's feeds.
    """
    moved = await api_key_service.reassign_feeds_off_key(api_key_id, db, actor_id=current_user.id)
    await db.commit()
    return ReassignResponse(source_api_key_id=api_key_id, feeds_moved=moved)
