"""
API v1 router assembly.

Imports all resource routers and includes them under the /api/v1 prefix.
Additional routers (feeds, standards, documents, notifications, admin)
are added here in their respective milestones (M2–M6).
"""

from fastapi import APIRouter

from app.api.v1 import auth, users

router = APIRouter(prefix="/api/v1")

# ── M1: Foundation ────────────────────────────────────────────────────────────
router.include_router(auth.router)
router.include_router(users.router)

# ── M2: Feed Engine (added in M2) ─────────────────────────────────────────────
# from app.api.v1 import feeds
# router.include_router(feeds.router)

# ── M3–M6: remaining routers added in later milestones ────────────────────────
