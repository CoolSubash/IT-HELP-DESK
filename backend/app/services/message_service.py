"""
Raw SQL for the `messages` table.
"""
import uuid

import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.enums import MessageDirection, SenderType
from app.services import admin_service, ticket_event_service, ticket_service, user_service


def list_messages_for_ticket(
    conn: PGConnection, ticket_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[dict], int]:
    ticket_service.get_ticket(conn, ticket_id)  # raises NotFoundError if missing
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM messages WHERE ticket_id = %s", (ticket_id,))
        total = cur.fetchone()["count"]
        cur.execute(
            "SELECT * FROM messages WHERE ticket_id = %s ORDER BY created_at LIMIT %s OFFSET %s",
            (ticket_id, limit, offset),
        )
        return cur.fetchall(), total


def create_message(
    conn: PGConnection,
    ticket_id: uuid.UUID,
    sender_type: SenderType,
    sender_id: uuid.UUID | None,
    body: str,
) -> dict:
    ticket_service.get_ticket(conn, ticket_id)  # raises NotFoundError if ticket missing

    # The schema-level validator (app/schemas/message.py) only checked
    # *shape* (present for STUDENT, absent for AI) -- confirming a given id
    # actually refers to a real row is the database's job, so it happens
    # here. Raises NotFoundError if not.
    if sender_type == SenderType.STUDENT:
        user_service.get_user(conn, sender_id)
    elif sender_type == SenderType.ADMIN and sender_id is not None:
        admin_service.get_admin(conn, sender_id)

    direction = (
        MessageDirection.INBOUND if sender_type == SenderType.STUDENT else MessageDirection.OUTBOUND
    )

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO messages (id, ticket_id, sender_type, sender_id, body, direction)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (uuid.uuid4(), ticket_id, sender_type.value, sender_id, body, direction.value),
        )
        message = cur.fetchone()

    # phase4.md #17: every admin reply is a ticket_events entry, so the
    # History timeline reflects it -- regardless of whether it was also
    # emailed (app/email/service.py separately logs EMAIL_SEND_FAILED only
    # on a failed send; this is the "an admin replied at all" record).
    if sender_type == SenderType.ADMIN:
        ticket_event_service.log_event(
            conn, ticket_id, event_type="ADMIN_REPLIED", actor_type="ADMIN", actor_id=sender_id
        )

    return message


def create_message_from_email(
    conn: PGConnection,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    body: str,
    email_message_id: str,
    in_reply_to: str | None,
    email_thread_id: str | None,
    subject: str | None = None,
) -> dict:
    """Inbound-email counterpart to create_message() -- used only by
    app/email/service.py. Always sender_type=STUDENT/direction=INBOUND: an
    inbound email is always from the student, and by the time this is
    called, app/email/service.py has already confirmed the ticket belongs
    to this user (see its _find_matching_ticket), so there's nothing left
    to validate here beyond what the UNIQUE constraint on
    email_message_id enforces (duplicate webhook protection --
    migrations/0004_messages_email_message_id_unique.sql).

    `subject` is the *email's own* subject line (which can literally
    change across a thread's replies, e.g. "VPN broken" ->
    "Re: VPN broken") -- preserved as historical data
    (migrations/0005_ticket_number_and_message_subject.sql), separate from
    the ticket's own `subject` (set once, at creation)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO messages
                (id, ticket_id, sender_type, sender_id, body, direction,
                 email_message_id, in_reply_to, email_thread_id, subject)
            VALUES (%s, %s, 'STUDENT', %s, %s, 'INBOUND', %s, %s, %s, %s)
            RETURNING *
            """,
            (
                uuid.uuid4(),
                ticket_id,
                user_id,
                body,
                email_message_id,
                in_reply_to,
                email_thread_id,
                subject,
            ),
        )
        return cur.fetchone()
