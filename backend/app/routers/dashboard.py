"""Dashboard summary endpoint -- the 7 stat cards on /dashboard, computed
in one call instead of the frontend deriving them from a full ticket list."""
import uuid

from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.schemas.dashboard import DashboardStats
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    admin_id: uuid.UUID | None = Query(default=None),
    db: PGConnection = Depends(get_db),
):
    return dashboard_service.get_dashboard_stats(db, admin_id)
