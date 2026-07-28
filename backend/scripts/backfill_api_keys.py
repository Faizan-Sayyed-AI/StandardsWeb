"""
One-time backfill script: seed the api_keys pool and assign existing feeds.

Run after applying migration 0013:
  docker compose exec web python scripts/backfill_api_keys.py

What it does:
  1. If no api_keys rows exist yet, creates one ("key-1") from the
     RSS2JSON_API_KEY env var this app used to read directly (if set).
  2. Assigns every rss_feeds row with api_key_id IS NULL to the
     least-loaded active key with spare capacity.

Add the other API keys (e.g. key-2, key-3) via POST /api-keys before or
after running this — feeds only get spread across whatever keys exist at
the time this runs. Re-run it any time to sweep up newly-unassigned feeds.
"""

import asyncio
import os
import sys

import structlog
from sqlalchemy import select

# Ensure the app package is importable when run from /app inside the container
sys.path.insert(0, "/app")

from app.core.logging import setup_logging
from app.database import async_session_factory
from app.models.api_key import ApiKey
from app.models.rss_feed import RssFeed
from app.services.api_key_service import create_api_key, pick_key_with_spare_capacity
from app.schemas.api_key import ApiKeyCreate

setup_logging()
log = structlog.get_logger(__name__)


async def backfill() -> None:
    log.info("backfill_api_keys_starting")

    async with async_session_factory() as session:
        existing = await session.execute(select(ApiKey))
        if existing.scalars().first() is None:
            legacy_key = os.environ.get("RSS2JSON_API_KEY", "").strip()
            if legacy_key:
                await create_api_key(
                    ApiKeyCreate(label="key-1", key_value=legacy_key, capacity=25),
                    session,
                )
                await session.commit()
                print("Created initial API key 'key-1' from RSS2JSON_API_KEY env var")
            else:
                print(
                    "No api_keys rows exist and RSS2JSON_API_KEY is not set — "
                    "add at least one key via POST /api-keys before assigning feeds."
                )
                return

        result = await session.execute(select(RssFeed).where(RssFeed.api_key_id.is_(None)))
        unassigned = result.scalars().all()

        assigned_count = 0
        for feed in unassigned:
            key = await pick_key_with_spare_capacity(session)
            feed.api_key_id = key.id
            assigned_count += 1

        await session.commit()
        print(f"Assigned {assigned_count} feed(s) to API keys")


if __name__ == "__main__":
    asyncio.run(backfill())
