"""
Database seed script.

Inserts a default admin user if one doesn't already exist.
Run after the initial migration:
  make seed
  # or directly:
  docker compose exec web python scripts/seed.py

Default credentials (change immediately in any shared environment):
  Email:    admin@ists.local
  Password: Admin1234!
  Role:     admin
"""

import asyncio
import sys

import structlog
from sqlalchemy import select

# Ensure the app package is importable when run from /app inside the container
sys.path.insert(0, "/app")

from app.core.logging import setup_logging
from app.core.security import hash_password
from app.database import async_session_factory
from app.models.user import User, UserRole

setup_logging()
log = structlog.get_logger(__name__)

_SEED_EMAIL = "admin@ists.local"
_SEED_PASSWORD = "Admin1234!"
_SEED_USERNAME = "admin"


async def seed() -> None:
    log.info("seed_starting")

    async with async_session_factory() as session:
        # Check if admin already exists
        result = await session.execute(select(User).where(User.email == _SEED_EMAIL))
        existing = result.scalar_one_or_none()

        if existing is not None:
            log.info("seed_skipped", reason="Admin user already exists", email=_SEED_EMAIL)
            print(f"\n[seed] Admin user already exists: {_SEED_EMAIL}")
            return

        admin = User(
            email=_SEED_EMAIL,
            username=_SEED_USERNAME,
            hashed_password=hash_password(_SEED_PASSWORD),
            role=UserRole.admin,
            is_active=True,
        )
        session.add(admin)
        await session.commit()

        log.info("seed_complete", user_id=str(admin.id), email=admin.email)

    print("\n" + "=" * 50)
    print("  ISTS — Default admin user created")
    print("=" * 50)
    print(f"  Email:    {_SEED_EMAIL}")
    print(f"  Password: {_SEED_PASSWORD}")
    print(f"  Role:     admin")
    print("=" * 50)
    print("  !! Change this password before sharing access !!")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(seed())
