import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, EmailStr, Field

from app.core.smtp_config import MASKED_PASSWORD_PLACEHOLDER

# Mirrors the DB's event_type_enum (see migrations 0001, 0003) — kept as an
# explicit Literal here (rather than reusing app.models.standard_history.EventType,
# which is missing "document_uploaded") so an invalid event_type is rejected
# with a clean 422 instead of reaching the DB as a raw enum-constraint 500.
NotificationEventType = Literal[
    "new", "updated", "amended", "withdrawn", "replaced",
    "purchased", "status_change", "document_uploaded",
]


class SMTPConfigResponse(BaseModel):
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_USE_TLS: bool
    SMTP_FROM_ADDRESS: str

    @classmethod
    def from_dict_masked(cls, data: dict) -> "SMTPConfigResponse":
        # Mask password for security
        pwd = data.get("SMTP_PASSWORD", "")
        masked_pwd = MASKED_PASSWORD_PLACEHOLDER if pwd else ""
        return cls(
            SMTP_HOST=data.get("SMTP_HOST", ""),
            SMTP_PORT=data.get("SMTP_PORT", 1025),
            SMTP_USER=data.get("SMTP_USER", ""),
            SMTP_PASSWORD=masked_pwd,
            SMTP_USE_TLS=data.get("SMTP_USE_TLS", False),
            SMTP_FROM_ADDRESS=data.get("SMTP_FROM_ADDRESS", ""),
        )


class SMTPConfigUpdate(BaseModel):
    SMTP_HOST: str = Field(..., min_length=1)
    SMTP_PORT: int = Field(..., ge=1, le=65535)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_USE_TLS: bool = Field(default=False)
    SMTP_FROM_ADDRESS: str = Field(..., min_length=1)


class DocumentTaggingConfigResponse(BaseModel):
    DOCUMENT_TAGGING_URL: str
    DOCUMENT_TAGGING_API_KEY: str

    @classmethod
    def from_dict_masked(cls, data: dict) -> "DocumentTaggingConfigResponse":
        key = data.get("DOCUMENT_TAGGING_API_KEY", "")
        masked_key = MASKED_PASSWORD_PLACEHOLDER if key else ""
        return cls(
            DOCUMENT_TAGGING_URL=data.get("DOCUMENT_TAGGING_URL", ""),
            DOCUMENT_TAGGING_API_KEY=masked_key,
        )


class DocumentTaggingConfigUpdate(BaseModel):
    DOCUMENT_TAGGING_URL: str = Field(..., min_length=1)
    DOCUMENT_TAGGING_API_KEY: str = Field(default="")


class NotificationTriggerMappingResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    list_id: uuid.UUID
    notify_all_users: bool
    # Include list name for convenient frontend display
    list_name: str | None = None

    model_config = {"from_attributes": True}


class NotificationTriggerMappingCreate(BaseModel):
    event_type: NotificationEventType
    list_id: uuid.UUID
    notify_all_users: bool = False


class AuditLogResponse(BaseModel):
    id: int
    actor_id: uuid.UUID | None
    actor_username: str | None = None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None = None
    payload: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QueueDepths(BaseModel):
    feeds: int
    notifications: int
    maintenance: int


class WorkerStatusResponse(BaseModel):
    status: str
    queues: QueueDepths

