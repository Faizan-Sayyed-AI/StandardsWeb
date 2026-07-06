"""
One-time backfill script: compute and store base_reference for all standards.

Run after applying migration 0007:
  docker compose exec web python scripts/backfill_base_reference.py
"""

import asyncio
import sys

import structlog
from sqlalchemy import select

# Ensure the app package is importable when run from /app inside the container
sys.path.insert(0, "/app")

from app.core.logging import setup_logging
from app.database import async_session_factory
from app.models.standard import Standard
from app.tasks.feeds import _extract_base_reference

setup_logging()
log = structlog.get_logger(__name__)


async def backfill() -> None:
    log.info("backfill_base_reference_starting")

    async with async_session_factory() as session:
        result = await session.execute(select(Standard))
        standards = result.scalars().all()

        for s in standards:
            s.base_reference = _extract_base_reference(s.iso_reference)

        await session.commit()
        print(f"Backfilled {len(standards)} standards")


if __name__ == "__main__":
    asyncio.run(backfill())
