"""
Raw SQL for the `admins` table. Read-only in Phase 3 -- there's still no
login, so admins only ever come from the seed script (or, in a real
deployment, whoever operates the database). This powers the dashboard's
"Acting as" picker and the assigned-admin filter/display.
"""
import uuid

import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.errors import NotFoundError


def list_admins(conn: PGConnection) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM admins ORDER BY name")
        return cur.fetchall()


def get_admin(conn: PGConnection, admin_id: uuid.UUID) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM admins WHERE id = %s", (admin_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(f"admin {admin_id} not found")
    return row
