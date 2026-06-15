"""
Feeds router — /api/v1/feeds/*

Endpoints (PRD §7.2):
  GET    /feeds              — List all feeds             (manager+)
  POST   /feeds              — Create new feed            (admin)
  GET    /feeds/{id}         — Feed detail                (manager+)
  PATCH  /feeds/{id}         — Update feed / schedule     (admin)
  DELETE /feeds/{id}         — Delete feed                (admin, 204)
  POST   /feeds/{id}/poll    — Trigger immediate poll     (admin)
"""

import uuid

from fastapi import APIRouter, Query, Request, status

from app.api.deps import AdminUser, DBSession, ManagerOrAdminUser
from app.schemas.feed import FeedCreate, FeedResponse, FeedUpdate, PollTriggerResponse
from app.schemas.pagination import Page
from app.services import feed_service

router = APIRouter(prefix="/feeds", tags=["Feeds"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.get(
    "",
    response_model=Page[FeedResponse],
    summary="List RSS feeds (manager+)",
)
async def list_feeds(
    db: DBSession,
    _: ManagerOrAdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[FeedResponse]:
    """Return a paginated list of all configured RSS feeds."""
    feeds, total = await feed_service.list_feeds(db, page=page, page_size=page_size)
    return Page[FeedResponse](
        items=[FeedResponse.model_validate(f) for f in feeds],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=FeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create RSS feed (admin)",
)
async def create_feed(
    body: FeedCreate,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> FeedResponse:
    """
    Create a new RSS feed.
    Returns 409 if the feed URL already exists.
    A `celery_schedules` metadata row is created automatically.
    """
    feed = await feed_service.create_feed(
        body, db, actor_id=current_user.id, ip_address=_client_ip(request)
    )
    return FeedResponse.model_validate(feed)


@router.get(
    "/{feed_id}",
    response_model=FeedResponse,
    summary="Get feed detail (manager+)",
)
async def get_feed(
    feed_id: uuid.UUID,
    db: DBSession,
    _: ManagerOrAdminUser,
) -> FeedResponse:
    """Fetch a single RSS feed by UUID. Returns 404 if not found."""
    feed = await feed_service.get_feed(feed_id, db)
    return FeedResponse.model_validate(feed)


@router.patch(
    "/{feed_id}",
    response_model=FeedResponse,
    summary="Update feed (admin)",
)
async def update_feed(
    feed_id: uuid.UUID,
    body: FeedUpdate,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> FeedResponse:
    """
    Partially update a feed (PATCH semantics — only provided fields change).
    Schedule changes are propagated to the `celery_schedules` table.
    Returns 404 if not found; 409 on URL conflict.
    """
    feed = await feed_service.update_feed(
        feed_id, body, db, actor_id=current_user.id, ip_address=_client_ip(request)
    )
    return FeedResponse.model_validate(feed)


@router.delete(
    "/{feed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete feed (admin)",
)
async def delete_feed(
    feed_id: uuid.UUID,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    """
    Hard-delete an RSS feed.
    The associated `celery_schedules` row is removed via CASCADE.
    Returns 204 No Content.
    """
    await feed_service.delete_feed(
        feed_id, db, actor_id=current_user.id, ip_address=_client_ip(request)
    )


@router.post(
    "/{feed_id}/poll",
    response_model=PollTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger immediate feed poll (admin)",
)
async def trigger_poll(
    feed_id: uuid.UUID,
    db: DBSession,
    _: AdminUser,
) -> PollTriggerResponse:
    """
    Immediately dispatch the `poll_feed` Celery task for the given feed.
    Returns 202 Accepted with the Celery task ID for tracking.
    The task runs asynchronously — check task result via Celery result backend.
    Returns 404 if the feed does not exist.
    """
    task_id = await feed_service.trigger_manual_poll(feed_id, db)
    return PollTriggerResponse(
        message="Poll task queued successfully",
        task_id=task_id,
        feed_id=feed_id,
    )
