"""
Generic pagination schema.

All list endpoints return Page[T] to give the frontend consistent
metadata (total count, current page, page size, total pages).

Usage:
  return Page[UserResponse](
      items=users,
      total=total_count,
      page=params.page,
      page_size=params.page_size,
  )
"""

import math
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameter schema for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int = Field(description="Total number of matching items across all pages")
    page: int = Field(description="Current page number (1-indexed)")
    page_size: int = Field(description="Number of items per page")

    @computed_field  # type: ignore[misc]
    @property
    def pages(self) -> int:
        """Total number of pages."""
        if self.total == 0:
            return 1
        return math.ceil(self.total / self.page_size)

    model_config = {"from_attributes": True}
