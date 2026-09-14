"""Pydantic schema for the dashboard's summary card counts
(GET /dashboard/stats)."""
from pydantic import BaseModel


class DashboardStats(BaseModel):
    open: int
    in_progress: int
    waiting_for_user: int
    resolved: int
    closed: int
    high_priority: int
    assigned_to_me: int | None
