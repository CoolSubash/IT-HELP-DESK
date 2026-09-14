"""Liveness/readiness check -- confirms the API process is up and can reach
Postgres. Use this first when verifying the Phase 1 setup (see root README)."""
from fastapi import APIRouter, Depends
from psycopg2.extensions import connection as PGConnection

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: PGConnection = Depends(get_db)) -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT 1")
    return {"status": "ok", "database": "connected"}
