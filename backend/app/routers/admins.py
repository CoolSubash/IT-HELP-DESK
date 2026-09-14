"""Read-only admin directory -- powers the dashboard's "Acting as" picker
and the assigned-admin filter/display. No create/update endpoints: there's
still no login, so admins are only ever added via the seed script or
directly in the database."""
from fastapi import APIRouter, Depends
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.schemas.admin import AdminRead
from app.services import admin_service

router = APIRouter(prefix="/admins", tags=["admins"])


@router.get("", response_model=list[AdminRead])
def list_admins(db: PGConnection = Depends(get_db)):
    return admin_service.list_admins(db)
