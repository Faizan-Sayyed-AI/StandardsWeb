"""
Dashboard router — /api/v1/dashboard/*

Endpoints:
  GET /dashboard/stats  — Aggregate counts for the dashboard summary cards (viewer+)
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.dashboard import DashboardStats
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Dashboard summary statistics (viewer+)",
)
async def get_stats(db: DBSession, current_user: CurrentUser) -> DashboardStats:
    """
    Return aggregate counts for the dashboard:
    total/active/purchased standards, total/enabled feeds,
    events in last 7 days, unread notifications for the current user.
    """
    return await dashboard_service.get_dashboard_stats(current_user.id, db)
