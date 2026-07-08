"""
Pydantic schemas for the standards API (M3 read endpoints).

GET /standards           → Page[StandardListItem]
GET /standards/{id}      → StandardDetail
GET /standards/{id}/history → Page[StandardHistoryItem]
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.standard import StandardStatus
from app.models.standard_history import EventSource, EventType


class StandardCreate(BaseModel):
    """Payload for manually adding a standard (manager+), not via RSS discovery."""

    iso_reference: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1)
    standards_body: str = Field(..., min_length=1, max_length=50)
    edition: str | None = Field(default=None, max_length=50)
    tc_committee: str | None = Field(default=None, max_length=100)
    status: StandardStatus = StandardStatus.active
    published_date: date | None = None
    external_url: str | None = None


class StandardListItem(BaseModel):
    """Lightweight projection used in the standards list table."""

    id: uuid.UUID
    iso_reference: str
    title: str
    edition: str | None
    tc_committee: str | None
    standards_body: str | None = None
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
    standards_body: str | None = None
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


class StandardVersion(BaseModel):
    """Lightweight projection of one non-primary version within a base-reference group."""

    id: uuid.UUID
    iso_reference: str
    stage_code: str | None
    stage_name: str | None
    status: str
    published_date: date | None
    edition: str | None
    is_purchased: bool

    model_config = ConfigDict(from_attributes=True)


class StandardGrouped(StandardListItem):
    """StandardListItem extended with all versions of the same base reference."""

    base_reference: str | None = None
    versions: list[StandardVersion] = []
    versions_count: int = 0


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
