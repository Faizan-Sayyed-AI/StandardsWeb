"""
Pydantic schemas for user management endpoints.

GET  /users           → Page[UserResponse]
POST /users           → UserCreate → UserResponse (201)
GET  /users/{id}      → UserResponse
PATCH /users/{id}     → UserUpdate → UserResponse
DELETE /users/{id}    → 204 No Content
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, description="Plain-text password (hashed server-side)")
    role: UserRole = Field(default=UserRole.viewer)


class UserUpdate(BaseModel):
    """All fields are optional — only provided fields are updated (PATCH semantics)."""

    email: str | None = Field(default=None, min_length=3, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, description="New plain-text password")


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    role: UserRole
    is_active: bool
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
