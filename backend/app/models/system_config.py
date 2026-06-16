"""
ORM model: system_config table.

Schema:
  key   VARCHAR(100) PRIMARY KEY
  value JSONB NOT NULL
"""

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class SystemConfig(AsyncBase):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return f"<SystemConfig key={self.key}>"
