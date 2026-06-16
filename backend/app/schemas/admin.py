import uuid
from pydantic import BaseModel, EmailStr, Field


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
        masked_pwd = "*" * 8 if pwd else ""
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


class NotificationTriggerMappingResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    list_id: uuid.UUID
    notify_all_users: bool
    # Include list name for convenient frontend display
    list_name: str | None = None

    model_config = {"from_attributes": True}


class NotificationTriggerMappingCreate(BaseModel):
    event_type: str = Field(..., min_length=1)
    list_id: uuid.UUID
    notify_all_users: bool = False
