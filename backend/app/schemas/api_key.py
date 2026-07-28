"""
Pydantic schemas for API key pool management endpoints.

POST   /api-keys                    → ApiKeyCreate → ApiKeyResponse (201)
GET    /api-keys                    → list[ApiKeyResponse]
PATCH  /api-keys/{id}                → ApiKeyUpdate → ApiKeyResponse
DELETE /api-keys/{id}                → 204
POST   /api-keys/{id}/reassign-feeds → ReassignResponse

key_value is write-only — it is never included in any response, matching
the masked-secret convention used for SMTP/document-tagging config
(app/core/smtp_config.py, app/core/document_tagging_config.py).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.api_key import ApiKeyStatus


class ApiKeyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255, description="Human-readable name, e.g. 'rss2json-key-2'")
    key_value: str = Field(min_length=1, description="The real rss2json.com API key (encrypted at rest)")
    capacity: int = Field(default=25, ge=1, description="Max feeds this key may be assigned")
    notes: str | None = Field(default=None, description="Free-text notes, e.g. rotation history")


class ApiKeyUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    label: str | None = Field(default=None, min_length=1, max_length=255)
    key_value: str | None = Field(default=None, min_length=1, description="Provide to rotate the key")
    capacity: int | None = Field(default=None, ge=1)
    status: ApiKeyStatus | None = None
    notes: str | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    label: str
    capacity: int
    status: ApiKeyStatus
    assigned_feed_count: int
    consecutive_failures: int
    last_used_at: datetime | None
    last_failure_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReassignResponse(BaseModel):
    source_api_key_id: uuid.UUID
    feeds_moved: int
