"""
One-time backfill: populate standards_body for standards created before this field existed.

Run after applying migration 0012:
  docker compose exec web python scripts/backfill_standards_body.py
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
from app.tasks.feeds import _REFERENCE_RE

setup_logging()
log = structlog.get_logger(__name__)


def _derive_standards_body(iso_reference: str) -> str | None:
    """Same extraction _process_entry() applies to newly-parsed feed entries."""
    match = _REFERENCE_RE.match(iso_reference)
    if not match:
        return None
    return match.group(1).split("/")[0].strip()


async def backfill() -> None:
    log.info("backfill_standards_body_starting")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Standard).where(Standard.standards_body.is_(None))
        )
        standards = result.scalars().all()

        updated = 0
        for s in standards:
            body = _derive_standards_body(s.iso_reference)
            if body:
                s.standards_body = body
                updated += 1

        await session.commit()
        print(f"Backfilled {updated} of {len(standards)} standards without a standards_body")


if __name__ == "__main__":
    asyncio.run(backfill())
