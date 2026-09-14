"""
Raw SQL for the dashboard's summary stat cards. One small query per card
rather than a single query with CASE WHEN columns -- simpler to read, and
this endpoint is only called once per dashboard page load, not in a hot
loop, so the extra round trips don't matter.
"""
import uuid

from psycopg2.extensions import connection as PGConnection


def _count(conn: PGConnection, where_sql: str, params: tuple = ()) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM tickets WHERE {where_sql}", params)
        return cur.fetchone()[0]


def get_dashboard_stats(conn: PGConnection, admin_id: uuid.UUID | None) -> dict:
    assigned_to_me = (
        _count(conn, "assigned_admin_id = %s", (admin_id,)) if admin_id is not None else None
    )
    return {
        "open": _count(conn, "status NOT IN ('RESOLVED', 'CLOSED')"),
        "in_progress": _count(conn, "status = 'IN_PROGRESS'"),
        "waiting_for_user": _count(conn, "status = 'WAITING_FOR_USER'"),
        "resolved": _count(conn, "status = 'RESOLVED'"),
        "closed": _count(conn, "status = 'CLOSED'"),
        "high_priority": _count(
            conn, "priority IN ('HIGH', 'URGENT') AND status NOT IN ('RESOLVED', 'CLOSED')"
        ),
        "assigned_to_me": assigned_to_me,
    }
