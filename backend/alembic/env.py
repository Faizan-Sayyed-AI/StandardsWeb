"""
Alembic migration environment.

Uses the async SQLAlchemy engine so migrations run the same driver (asyncpg)
as the application. DATABASE_URL is read from the environment — not from
alembic.ini — to avoid committing credentials.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import all models so Alembic sees the full metadata graph
import app.models  # noqa: F401
from app.config import settings
from app.database import AsyncBase

# --------------------------------------------------------------------------- #
# Alembic config object — gives access to .ini values                         #
# --------------------------------------------------------------------------- #
config = context.config

# Configure Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that autogenerate will compare against the live DB
target_metadata = AsyncBase.metadata


# --------------------------------------------------------------------------- #
# Offline mode (no live DB connection — just emit SQL to stdout/file)          #
# --------------------------------------------------------------------------- #
def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# --------------------------------------------------------------------------- #
# Online mode (connects to PostgreSQL, applies migrations)                     #
# --------------------------------------------------------------------------- #
def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with async_engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await async_engine.dispose()


# --------------------------------------------------------------------------- #
# Entry point                                                                   #
# --------------------------------------------------------------------------- #
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
