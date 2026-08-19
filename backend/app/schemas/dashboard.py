"""
Pydantic schema for the dashboard stats endpoint (M3).

GET /dashboard/stats → DashboardStats
"""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    # total_standards / active_standards count the library as the Standards page
    # shows it: one row per version group, keeping parents that carry an edition
    # or are purchased.
    total_standards: int
    active_standards: int
    # Every purchased row, including superseded editions and standards with no
    # edition — this is "what we have bought", not "what is current".
    purchased_standards: int
    total_feeds: int
    enabled_feeds: int
    events_last_7_days: int
    unread_notifications: int
