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
from sqlalchemy import func, select

# Ensure the app package is importable when run from /app inside the container
sys.path.insert(0, "/app")

from app.core.exceptions import AppValidationError
from app.core.logging import setup_logging
from app.database import async_session_factory
from app.models.api_key import ApiKey, ApiKeyStatus
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
        unassigned = list(result.scalars().all())

        if not unassigned:
            print("Nothing to do — every feed already has an API key assigned.")
            return

        # Assign as far as the pool's capacity allows, then COMMIT what we
        # managed to do. Letting the capacity error propagate would roll back
        # every assignment made in this run, so a pool too small for the feed
        # count would leave the whole table unassigned and make repeated runs
        # look like no-ops.
        assigned_count = 0
        for feed in unassigned:
            try:
                key = await pick_key_with_spare_capacity(session)
            except AppValidationError:
                break
            feed.api_key_id = key.id
            assigned_count += 1

        await session.commit()

        remaining = len(unassigned) - assigned_count
        print(f"Assigned {assigned_count} of {len(unassigned)} unassigned feed(s).")

        if remaining:
            # Tell the operator exactly how much more capacity to provision,
            # rather than just reporting that the pool is full.
            cap_result = await session.execute(
                select(func.coalesce(func.sum(ApiKey.capacity), 0)).where(
                    ApiKey.status == ApiKeyStatus.active
                )
            )
            active_capacity = cap_result.scalar_one()
            total_feeds = await session.execute(select(func.count(RssFeed.id)))
            total_feeds = total_feeds.scalar_one()
            shortfall = total_feeds - active_capacity
            typical = 25
            keys_needed = -(-shortfall // typical) if shortfall > 0 else 0

            print(
                f"\n{remaining} feed(s) still have no API key — the active pool is full.\n"
                f"  feeds total .......... {total_feeds}\n"
                f"  active key capacity .. {active_capacity}\n"
                f"  shortfall ............ {shortfall}\n"
                f"\nAdd {keys_needed} more API key(s) (POST /api-keys), then re-run this "
                f"script — already-assigned feeds are kept, so it resumes where it stopped."
            )
        else:
            print("All feeds now have an API key assigned.")


if __name__ == "__main__":
    asyncio.run(backfill())
