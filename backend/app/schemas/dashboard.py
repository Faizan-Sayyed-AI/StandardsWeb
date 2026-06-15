"""
Pydantic schema for the dashboard stats endpoint (M3).

GET /dashboard/stats → DashboardStats
"""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_standards: int
    active_standards: int
    purchased_standards: int
    total_feeds: int
    enabled_feeds: int
    events_last_7_days: int
    unread_notifications: int
