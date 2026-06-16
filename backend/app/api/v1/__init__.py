"""
API v1 router assembly.

Imports all resource routers and includes them under the /api/v1 prefix.
Additional routers (feeds, standards, documents, notifications, admin)
are added here in their respective milestones (M2–M6).
"""

from fastapi import APIRouter

from app.api.v1 import admin, auth, dashboard, documents, distribution_lists, feeds, notifications, standards, users

router = APIRouter(prefix="/api/v1")

# ── M1: Foundation ────────────────────────────────────────────────────────────
router.include_router(auth.router)
router.include_router(users.router)

# ── M2: Feed Engine ───────────────────────────────────────────────────────────
router.include_router(feeds.router)

# ── M3: Core UI API endpoints ─────────────────────────────────────────────────
router.include_router(standards.router)
router.include_router(notifications.router)
router.include_router(dashboard.router)

# ── M4: Document Management ──────────────────────────────────────────────────
router.include_router(documents.router)

# ── M5: Notifications Settings & Distribution Lists CRUD ──────────────────────
router.include_router(distribution_lists.router)
router.include_router(admin.router)


