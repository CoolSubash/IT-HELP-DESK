"""
Raw SQL for the `agent_actions` table. Read-only in Phase 2 -- nothing
creates these rows yet since the AI agent that would (project.md #9-11)
doesn't exist until a later phase. The seed data (seed/seed_data.py) is the
only source of agent_actions rows for now.
"""
import uuid

import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.services import ticket_service


def list_agent_actions_for_ticket(
    conn: PGConnection, ticket_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[dict], int]:
    ticket_service.get_ticket(conn, ticket_id)  # raises NotFoundError if missing
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM agent_actions WHERE ticket_id = %s", (ticket_id,))
        total = cur.fetchone()["count"]
        cur.execute(
            "SELECT * FROM agent_actions WHERE ticket_id = %s ORDER BY created_at LIMIT %s OFFSET %s",
            (ticket_id, limit, offset),
        )
        return cur.fetchall(), total
