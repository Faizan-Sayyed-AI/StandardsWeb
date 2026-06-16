import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class DistributionListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class DistributionListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class DistributionListMemberCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class DistributionListMemberResponse(BaseModel):
    id: uuid.UUID
    list_id: uuid.UUID
    email: str
    name: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class DistributionListResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}
