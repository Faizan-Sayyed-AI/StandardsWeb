"""
Pydantic schemas for the standards API (M3 read endpoints).

GET /standards           → Page[StandardListItem]
GET /standards/{id}      → StandardDetail
GET /standards/{id}/history → Page[StandardHistoryItem]
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.standard import StandardStatus
from app.models.standard_history import EventSource, EventType


class StandardListItem(BaseModel):
    """Lightweight projection used in the standards list table."""

    id: uuid.UUID
    iso_reference: str
    title: str
    edition: str | None
    tc_committee: str | None
    status: StandardStatus
    is_purchased: bool
    stage_code: str | None = None
    stage_name: str | None = None
    published_date: date | None = None
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class StandardDetail(BaseModel):
    """Full standard record returned on the detail page."""

    id: uuid.UUID
    iso_reference: str
    title: str
    edition: str | None
    tc_committee: str | None
    status: StandardStatus
    is_purchased: bool
    purchased_at: datetime | None
    purchase_notes: str | None
    external_url: str | None
    source_feed_id: uuid.UUID | None
    stage_code: str | None = None
    stage_name: str | None = None
    published_date: date | None = None
    parent_standard_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StandardDetailWithAmendments(StandardDetail):
    """StandardDetail extended with linked amendment records."""

    amendments: list[StandardListItem] = []


class StandardHistoryItem(BaseModel):
    """Single event in the standard's change history timeline."""

    id: uuid.UUID
    standard_id: uuid.UUID
    event_type: EventType
    source: EventSource
    old_value: dict | None
    new_value: dict
    triggered_by: uuid.UUID | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
