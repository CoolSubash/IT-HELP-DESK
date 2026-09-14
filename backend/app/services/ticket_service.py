"""
Raw SQL for the `tickets` table.

`get_ticket()` raises `NotFoundError` instead of returning `None` -- every
other function here (`update_ticket`, `update_ticket_status`,
`assign_ticket`, `get_related_tickets`, `get_ticket_history`) calls it first
to confirm the ticket exists, so "ticket not found" is handled in exactly
one place and always produces the same 404.
"""
import uuid
from enum import Enum

import psycopg2.errors
import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.enums import TicketStatus
from app.errors import ConflictError, NotFoundError
from app.services import ticket_event_service

# Which statuses a ticket can move to from its current one.
#
# CLOSED -> IN_PROGRESS and RESOLVED -> IN_PROGRESS are the two "reopen"
# edges (phase6.md Part 8, Cases D/E): a student replying to either kind
# of finished ticket should bring it back into active work, not get
# silently dropped or forced into a brand-new ticket. Both reopen to the
# same state (IN_PROGRESS, not back into AI_INVESTIGATING) for consistency
# -- app/email/service.py logs a dedicated REOPENED event on top of the
# usual STATUS_CHANGED one whenever either edge is taken, so "this ticket
# was reopened" is never just inferred from an old_value/new_value pair.
#
# This is a change from Phase 2/4: CLOSED used to have no outgoing edges
# at all ("a recurring issue becomes a new ticket via parent_ticket_id,
# not a reopened old one"). phase6.md explicitly asks for reopening
# instead, with the reasoning that a closed ticket isn't in anyone's
# active queue, so silently leaving it CLOSED means an admin never
# notices the student's reply.
TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW: {TicketStatus.AI_INVESTIGATING, TicketStatus.ESCALATED},
    TicketStatus.AI_INVESTIGATING: {
        TicketStatus.WAITING_FOR_USER,
        TicketStatus.WAITING_FOR_ADMIN,
        TicketStatus.RESOLVED,
        TicketStatus.ESCALATED,
    },
    TicketStatus.WAITING_FOR_USER: {TicketStatus.AI_INVESTIGATING, TicketStatus.IN_PROGRESS},
    TicketStatus.WAITING_FOR_ADMIN: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.ESCALATED,
    },
    TicketStatus.IN_PROGRESS: {
        TicketStatus.WAITING_FOR_USER,
        TicketStatus.WAITING_FOR_ADMIN,
        TicketStatus.RESOLVED,
    },
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
    TicketStatus.ESCALATED: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_FOR_ADMIN,
        TicketStatus.RESOLVED,
    },
    TicketStatus.CLOSED: {TicketStatus.IN_PROGRESS},
}


def format_ticket_number(ticket_number: int) -> str:
    """The one place "T-104"-style display formatting happens -- the
    database and every service function deal in the raw integer
    (tickets.ticket_number); only email subjects and the
    POST /email/inbound response (phase6.md Part 13) need the human
    "T-104" string."""
    return f"T-{ticket_number}"


def list_tickets(
    conn: PGConnection,
    limit: int,
    offset: int,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    assigned_admin_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Every filter is optional and ANDed together. `conditions` is always
    built from fixed, hardcoded SQL fragments -- only the *values* plugged
    into them (via `params`, using `%s` placeholders) come from the caller,
    so this stays safe from SQL injection despite building the WHERE clause
    dynamically."""
    conditions: list[str] = []
    params: list = []

    if status is not None:
        conditions.append("status = %s")
        params.append(status)
    if priority is not None:
        conditions.append("priority = %s")
        params.append(priority)
    if category is not None:
        conditions.append("category = %s")
        params.append(category)
    if assigned_admin_id is not None:
        conditions.append("assigned_admin_id = %s")
        params.append(assigned_admin_id)
    if search:
        conditions.append("(subject ILIKE %s OR description ILIKE %s)")
        like_pattern = f"%{search}%"
        params.extend([like_pattern, like_pattern])

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT count(*) AS count FROM tickets {where_sql}", params)
        total = cur.fetchone()["count"]
        cur.execute(
            f"SELECT * FROM tickets {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        return cur.fetchall(), total


def get_ticket(conn: PGConnection, ticket_id: uuid.UUID) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(f"ticket {ticket_id} not found")
    return row


def get_ticket_by_number(conn: PGConnection, ticket_number: int) -> dict | None:
    """Used only by app/email/service.py's subject-tag matching strategy
    (phase6.md #12's "Explicit Ticket ID in subject" fallback) -- an exact
    integer lookup, unlike Phase 4's old UUID-prefix approach which needed
    a `LIKE 'prefix%'` guess and an explicit "astronomically unlikely to
    collide" caveat. Returns None instead of raising, since "no ticket
    with that number" just means this matching strategy didn't find
    anything -- not that the caller did something wrong."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM tickets WHERE ticket_number = %s", (ticket_number,))
        return cur.fetchone()


def create_ticket(
    conn: PGConnection,
    user_id: uuid.UUID,
    subject: str,
    description: str,
    category: str,
    priority: str,
    parent_ticket_id: uuid.UUID | None = None,
    created_by_actor_type: str = "SYSTEM",
    created_by_actor_id: uuid.UUID | None = None,
) -> dict:
    """`created_by_actor_type`/`_id` default to SYSTEM/None, matching every
    Phase 2/3 caller (the dashboard's "create ticket" API). Phase 4's
    inbound-email path (app/email/service.py) is the one caller that
    passes STUDENT + the sender's user id instead, since a ticket created
    from an inbound email was, in truth, created by that student -- not
    logging a second TICKET_CREATED event for that case."""
    ticket_id = uuid.uuid4()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO tickets (id, user_id, subject, description, category, priority, parent_ticket_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (ticket_id, user_id, subject, description, category, priority, parent_ticket_id),
            )
            row = cur.fetchone()
    except psycopg2.errors.ForeignKeyViolation as exc:
        conn.rollback()
        # Postgres names the constraint after the column it's on
        # (tickets_user_id_fkey / tickets_parent_ticket_id_fkey by default),
        # so we can tell which FK failed and give a precise error instead
        # of guessing.
        constraint = exc.diag.constraint_name or ""
        if "parent_ticket_id" in constraint:
            raise NotFoundError(f"parent ticket {parent_ticket_id} not found") from exc
        raise NotFoundError(f"user {user_id} not found") from exc

    ticket_event_service.log_event(
        conn,
        ticket_id,
        event_type="TICKET_CREATED",
        new_value=TicketStatus.NEW.value,
        actor_type=created_by_actor_type,
        actor_id=created_by_actor_id,
    )
    return row


def update_ticket(conn: PGConnection, ticket_id: uuid.UUID, updates: dict) -> dict:
    """`updates` comes from `TicketUpdate.model_dump(exclude_unset=True)` in
    the router -- its keys are always a subset of that schema's declared
    fields, never arbitrary client input, so building the SQL column list
    from them is safe."""
    get_ticket(conn, ticket_id)  # raises NotFoundError if missing

    if not updates:
        return get_ticket(conn, ticket_id)

    set_clauses = [f"{field} = %s" for field in updates]
    values = [value.value if isinstance(value, Enum) else value for value in updates.values()]
    values.append(ticket_id)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"UPDATE tickets SET {', '.join(set_clauses)} WHERE id = %s RETURNING *", values
        )
        return cur.fetchone()


def update_ticket_status(
    conn: PGConnection,
    ticket_id: uuid.UUID,
    new_status: TicketStatus,
    changed_by_admin_id: uuid.UUID | None = None,
) -> dict:
    ticket = get_ticket(conn, ticket_id)
    current_status = TicketStatus(ticket["status"])

    if new_status not in TRANSITIONS[current_status]:
        raise ConflictError(
            f"cannot transition ticket from {current_status.value} to {new_status.value}"
        )

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE tickets SET status = %s WHERE id = %s RETURNING *",
            (new_status.value, ticket_id),
        )
        row = cur.fetchone()

    ticket_event_service.log_event(
        conn,
        ticket_id,
        event_type="STATUS_CHANGED",
        old_value=current_status.value,
        new_value=new_status.value,
        actor_type="ADMIN" if changed_by_admin_id else "SYSTEM",
        actor_id=changed_by_admin_id,
    )
    return row


def assign_ticket(conn: PGConnection, ticket_id: uuid.UUID, assigned_admin_id: uuid.UUID) -> dict:
    ticket = get_ticket(conn, ticket_id)
    previous_admin_id = ticket["assigned_admin_id"]

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE tickets SET assigned_admin_id = %s WHERE id = %s RETURNING *",
                (assigned_admin_id, ticket_id),
            )
            row = cur.fetchone()
    except psycopg2.errors.ForeignKeyViolation as exc:
        conn.rollback()
        raise NotFoundError(f"admin {assigned_admin_id} not found") from exc

    # This endpoint is only ever called by an admin acting through the
    # dashboard (no other caller exists yet), so actor_type=ADMIN is safe
    # to hardcode -- unlike status changes, which automated callers/tests
    # also trigger without an admin identity.
    ticket_event_service.log_event(
        conn,
        ticket_id,
        event_type="ASSIGNED",
        old_value=str(previous_admin_id) if previous_admin_id else None,
        new_value=str(assigned_admin_id),
        actor_type="ADMIN",
        actor_id=assigned_admin_id,
    )
    return row


def get_related_tickets(conn: PGConnection, ticket_id: uuid.UUID) -> dict:
    ticket = get_ticket(conn, ticket_id)

    parent = None
    if ticket["parent_ticket_id"] is not None:
        parent = get_ticket(conn, ticket["parent_ticket_id"])

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM tickets WHERE parent_ticket_id = %s ORDER BY created_at", (ticket_id,)
        )
        children = cur.fetchall()

    return {"parent": parent, "children": children}


def get_ticket_history(conn: PGConnection, ticket_id: uuid.UUID) -> list[dict]:
    """Combined chronological feed of messages + ticket_events + agent_actions
    for one ticket -- the "complete conversation history" + "AI activity"
    view project.md #14 describes for the admin ticket page. Three separate
    queries (one per table) merged and sorted in Python, since a single SQL
    query can't cleanly UNION three tables with different columns."""
    get_ticket(conn, ticket_id)  # raises NotFoundError if missing

    entries: list[dict] = []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM messages WHERE ticket_id = %s", (ticket_id,))
        entries += [{"type": "message", "created_at": row["created_at"], "data": row} for row in cur.fetchall()]

        cur.execute("SELECT * FROM ticket_events WHERE ticket_id = %s", (ticket_id,))
        entries += [{"type": "event", "created_at": row["created_at"], "data": row} for row in cur.fetchall()]

        cur.execute("SELECT * FROM agent_actions WHERE ticket_id = %s", (ticket_id,))
        entries += [
            {"type": "agent_action", "created_at": row["created_at"], "data": row} for row in cur.fetchall()
        ]

    entries.sort(key=lambda entry: entry["created_at"])
    return entries
