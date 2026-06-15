"""
Pydantic schemas for the notifications API (M3).

GET /notifications          → Page[NotificationResponse]
PATCH /notifications/{id}/read → NotificationResponse
POST /notifications/mark-all-read → {"marked": N}
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.notification import NotificationSeverity


class NotificationResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    severity: NotificationSeverity
    title: str
    body: str
    related_standard_id: uuid.UUID | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationCountResponse(BaseModel):
    unread: int
