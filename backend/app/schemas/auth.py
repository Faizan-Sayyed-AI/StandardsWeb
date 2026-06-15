"""
Pydantic schemas for authentication endpoints.

POST /auth/login          → LoginRequest → TokenResponse
POST /auth/refresh        → RefreshRequest → TokenResponse
POST /auth/logout         → LogoutRequest (no response body)
POST /auth/password-reset/request  → PasswordResetRequest
POST /auth/password-reset/confirm  → PasswordResetConfirm
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(description="User's email address")
    password: str = Field(min_length=1, description="User's plain-text password")


class TokenResponse(BaseModel):
    access_token: str = Field(description="JWT access token (8-hour expiry)")
    refresh_token: str = Field(description="Opaque refresh token (7-day expiry)")
    token_type: str = Field(default="bearer")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(description="Valid, non-revoked refresh token")


class AccessTokenResponse(BaseModel):
    """Returned after a successful token refresh — refresh token is also rotated."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str = Field(description="Refresh token to revoke")


class PasswordResetRequest(BaseModel):
    email: str = Field(description="Email of the account to reset")


class PasswordResetConfirm(BaseModel):
    token: str = Field(description="Raw reset token received via email link")
    new_password: str = Field(
        min_length=8,
        description="New password — minimum 8 characters",
    )

