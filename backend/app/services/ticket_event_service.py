"""
Raw SQL for the `ticket_events` table -- the append-only audit trail of
what changed on a ticket and why.

`log_event()` is called by app/services/ticket_service.py whenever a ticket
mutates (status change, assignment), so every kind of change is recorded
the same way in one place, instead of each caller building its own INSERT.

There's still no real authentication (Phase 3 scope): `actor_id` is only
ever populated when a caller explicitly says who they are -- e.g. the
dashboard's "Acting as" picker passed through as
`TicketStatusUpdate.changed_by_admin_id` (see app/services/ticket_service.py).
Anything that doesn't specify an actor logs as `actor_type="SYSTEM"`.
"""
import uuid
from typing import Any

import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.services import ticket_service


def list_events_for_ticket(
    conn: PGConnection, ticket_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[dict], int]:
    ticket_service.get_ticket(conn, ticket_id)  # raises NotFoundError if missing
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM ticket_events WHERE ticket_id = %s", (ticket_id,))
        total = cur.fetchone()["count"]
        cur.execute(
            "SELECT * FROM ticket_events WHERE ticket_id = %s ORDER BY created_at LIMIT %s OFFSET %s",
            (ticket_id, limit, offset),
        )
        return cur.fetchall(), total


def log_event(
    conn: PGConnection,
    ticket_id: uuid.UUID,
    event_type: str,
    old_value: str | None = None,
    new_value: str | None = None,
    metadata: dict[str, Any] | None = None,
    actor_type: str = "SYSTEM",
    actor_id: uuid.UUID | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ticket_events
                (id, ticket_id, event_type, actor_type, actor_id, old_value, new_value, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(),
                ticket_id,
                event_type,
                actor_type,
                actor_id,
                old_value,
                new_value,
                psycopg2.extras.Json(metadata) if metadata is not None else None,
            ),
        )
