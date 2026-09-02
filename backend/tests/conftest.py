"""
Shared test fixtures.

These tests talk to a real PostgreSQL, because what they pin is PostgreSQL
semantics: `substring(text, pattern)` in its regex form, the `~` match
operator, DISTINCT ON, and NULLS LAST ordering. A SQLite or a mock would
happily agree with an expression that Postgres rejects, which is the one
outcome that would make the suite worse than nothing.

Nothing here writes: the ordering tests evaluate their expressions against an
inline VALUES clause, so no table, fixture row or migration is involved and
the suite is safe to run against any environment — including a copy of
production.

Run inside the API container, which already has the env for settings:

    docker compose exec web pytest
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings


@pytest_asyncio.fixture
async def db():
    """
    A session on the configured database.

    The engine is built per test rather than reusing app.database.engine:
    pytest-asyncio runs each test in its own event loop, and a pooled asyncpg
    connection belongs to the loop that opened it, so a shared engine fails
    with "attached to a different loop" on the second test. NullPool plus a
    per-test engine keeps every connection inside one loop.

    Skips only on a genuine connection failure — anything else is a real error
    and must be allowed to fail the test rather than turn into a green skip.
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            try:
                await session.execute(text("SELECT 1"))
            except (OperationalError, InterfaceError, OSError) as exc:
                pytest.skip(f"no database reachable: {exc}")
            yield session
    finally:
        await engine.dispose()
