"""
Async SQLAlchemy database setup.

Exports:
  - AsyncBase  — declarative base for all ORM models
  - engine     — async engine instance
  - async_session_factory — session maker
  - get_db     — FastAPI dependency that yields an AsyncSession per request
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # verify connection is alive before using it
    pool_size=10,
    max_overflow=20,
    echo=settings.is_development,  # log SQL in dev only
)

# ── Session factory ───────────────────────────────────────────────────────────
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keep objects usable after commit
)


# ── Declarative base ──────────────────────────────────────────────────────────
class AsyncBase(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── FastAPI dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session per HTTP request.
    Commits on success, rolls back on any unhandled exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
