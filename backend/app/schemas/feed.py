"""
Pydantic schemas for RSS feed endpoints.

POST /feeds         → FeedCreate → FeedResponse (201)
GET  /feeds         → Page[FeedResponse]
GET  /feeds/{id}    → FeedResponse
PATCH /feeds/{id}   → FeedUpdate → FeedResponse
DELETE /feeds/{id}  → 204
POST /feeds/{id}/poll → PollTriggerResponse
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.rss_feed import PollStatus, ScheduleType


class FeedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Display name for the feed")
    # str (not AnyHttpUrl) — avoids pydantic URL normalisation surprises with
    # internal test URLs and preserves the exact URL stored in the database.
    url: str = Field(min_length=1, description="RSS endpoint URL")
    tc_committee: str | None = Field(
        default=None, max_length=100, description="ISO TC committee tag, e.g. 'TC 176'"
    )
    schedule_type: ScheduleType = Field(
        default=ScheduleType.daily, description="Run daily or weekly"
    )
    schedule_hour: int = Field(
        default=6, ge=0, le=23, description="UTC hour to poll (0–23)"
    )
    schedule_day_of_week: int | None = Field(
        default=None, ge=0, le=6, description="For weekly schedules: 0=Mon … 6=Sun"
    )
    is_enabled: bool = Field(default=True, description="Whether the feed is actively polled")


class FeedUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1)
    tc_committee: str | None = None
    schedule_type: ScheduleType | None = None
    schedule_hour: int | None = Field(default=None, ge=0, le=23)
    schedule_day_of_week: int | None = Field(default=None, ge=0, le=6)
    is_enabled: bool | None = None


class FeedResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    tc_committee: str | None
    schedule_type: ScheduleType
    schedule_hour: int
    schedule_day_of_week: int | None
    is_enabled: bool
    last_polled_at: datetime | None
    last_poll_status: PollStatus
    failure_count: int
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PollTriggerResponse(BaseModel):
    """Response for POST /feeds/{id}/poll."""

    message: str
    task_id: str
    feed_id: uuid.UUID
