"""
Email orchestration: everything that turns an inbound email into database
rows, and everything that turns an admin's reply into an outbound email.
This is the only module that combines app/email/'s pieces (provider,
parser, threading) with the existing services (user_service, ticket_service,
message_service, ticket_event_service) -- those services still know
nothing about email.
"""
import uuid

import psycopg2.errors
import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.config import settings
from app.email.dev_provider import DevEmailProvider
from app.email.models import InboundEmail, InboundProcessResult, SentEmail
from app.email.parser import extract_ticket_number, normalize_email_address
from app.email.provider import EmailProvider, EmailSendError
from app.email.threading import build_references, build_reply_subject
from app.enums import TicketCategory, TicketPriority, TicketStatus
from app.services import message_service, ticket_event_service, ticket_service, user_service


def get_email_provider() -> EmailProvider:
    if settings.email_provider == "ses":
        # Imported lazily so boto3's client construction (and its own
        # credential lookup) only happens when SES is actually selected.
        from app.email.ses_provider import AWSSESProvider

        return AWSSESProvider(region=settings.aws_region, from_email=settings.it_support_email)
    return DevEmailProvider()


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------


def process_inbound_email(conn: PGConnection, email: InboundEmail) -> InboundProcessResult:
    """Implements phase4.md #10-14 / phase6.md's Main Objective: identify
    the user, find or create the ticket, store the message, log the event.
    Idempotency is checked first, before anything else runs, so a retried
    webhook call truly does nothing beyond confirming "already processed."
    """
    existing = _find_message_by_email_id(conn, email.message_id)
    if existing is not None:
        return _duplicate_result(conn, existing)

    from_email = normalize_email_address(email.from_email)
    user, _ = user_service.find_or_create_user(conn, from_email)

    ticket = _find_matching_ticket(conn, email, user["id"])
    created_ticket = ticket is None

    if created_ticket:
        ticket = ticket_service.create_ticket(
            conn,
            user_id=user["id"],
            subject=email.subject.strip() or "(no subject)",
            description=email.body,
            category=TicketCategory.OTHER.value,
            priority=TicketPriority.MEDIUM.value,
            created_by_actor_type="STUDENT",
            created_by_actor_id=user["id"],
        )
        thread_id = email.thread_id or email.message_id
    else:
        thread_id = _existing_thread_id(conn, ticket["id"]) or email.thread_id or email.message_id
        _apply_reply_status_transition(conn, ticket, user["id"])

    try:
        message = message_service.create_message_from_email(
            conn,
            ticket_id=ticket["id"],
            user_id=user["id"],
            body=email.body,
            email_message_id=email.message_id,
            in_reply_to=email.in_reply_to,
            email_thread_id=thread_id,
            subject=email.subject,
        )
    except psycopg2.errors.UniqueViolation:
        # A race with another request processing the exact same
        # email_message_id -- the UNIQUE constraint
        # (migrations/0004_messages_email_message_id_unique.sql) is the
        # authoritative backstop behind the check at the top of this
        # function. Treat it the same way: already processed.
        conn.rollback()
        existing = _find_message_by_email_id(conn, email.message_id)
        return _duplicate_result(conn, existing)

    # ticket_service.create_ticket() already logs the TICKET_CREATED event
    # itself (with the actor passed above) -- only the reply case needs an
    # event logged here.
    if not created_ticket:
        ticket_event_service.log_event(
            conn, ticket["id"], event_type="USER_REPLIED", actor_type="STUDENT", actor_id=user["id"]
        )

    return InboundProcessResult(
        status="processed",
        action="created_new_ticket" if created_ticket else "attached_to_existing_ticket",
        user_id=user["id"],
        ticket_id=ticket["id"],
        ticket_number=ticket["ticket_number"],
        message_id=message["id"],
    )


def _duplicate_result(conn: PGConnection, existing_message: dict) -> InboundProcessResult:
    ticket = ticket_service.get_ticket(conn, existing_message["ticket_id"])
    return InboundProcessResult(
        status="already_processed",
        action="duplicate",
        user_id=ticket["user_id"],
        ticket_id=ticket["id"],
        ticket_number=ticket["ticket_number"],
        message_id=existing_message["id"],
    )


def _apply_reply_status_transition(conn: PGConnection, ticket: dict, user_id: uuid.UUID) -> None:
    """phase6.md Part 8's student-reply rules:
      - Case A/B (OPEN-ish / IN_PROGRESS): no status change -- falls
        through to the final `return` below.
      - Case C (WAITING_FOR_USER): the ticket was specifically waiting on
        this reply, so it moves forward to IN_PROGRESS. Not a "reopen" --
        no REOPENED event, just the usual STATUS_CHANGED
        update_ticket_status() already logs.
      - Case D/E (RESOLVED / CLOSED): reopened to IN_PROGRESS, with an
        additional REOPENED event on top of STATUS_CHANGED, so "this
        ticket came back from being finished" is never just inferred from
        an old_value/new_value pair on a generic event.

    CLOSED reopening is a deliberate change from Phase 2/4, where CLOSED
    was terminal ("a recurring issue becomes a new ticket via
    parent_ticket_id"). phase6.md's reasoning is followed instead: a
    closed ticket isn't in anyone's active queue, so leaving it CLOSED
    when a student replies means an admin likely never notices."""
    current = TicketStatus(ticket["status"])

    if current == TicketStatus.WAITING_FOR_USER:
        ticket_service.update_ticket_status(conn, ticket["id"], TicketStatus.IN_PROGRESS)
        return

    if current in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        ticket_service.update_ticket_status(conn, ticket["id"], TicketStatus.IN_PROGRESS)
        ticket_event_service.log_event(
            conn,
            ticket["id"],
            event_type="REOPENED",
            actor_type="STUDENT",
            actor_id=user_id,
            old_value=current.value,
            new_value=TicketStatus.IN_PROGRESS.value,
        )
        return

    # Every other status (NEW, AI_INVESTIGATING, WAITING_FOR_ADMIN,
    # IN_PROGRESS, ESCALATED): no automatic change -- Cases A/B.


def _find_matching_ticket(conn: PGConnection, email: InboundEmail, user_id: uuid.UUID) -> dict | None:
    """Implements phase6.md Part 6's 5-strategy priority order verbatim
    (the 5th strategy, "create a new ticket," is simply this function
    returning None -- the caller creates one):
      1. duplicate message_id -- handled earlier, in process_inbound_email
      2. In-Reply-To
      3. References
      4. explicit ticket number in the subject
      5. otherwise, no match

    A found candidate is only used if it actually belongs to the sender
    (`ticket["user_id"] == user_id`). This isn't explicitly asked for in
    phase4.md/phase6.md, but not checking it would let a forged
    In-Reply-To / subject tag attach a message to a stranger's ticket --
    so a mismatch is treated exactly like "no match" and falls through to
    creating a new ticket for this user instead of ever cross-attaching."""
    candidate_ticket_id = None

    if email.in_reply_to:
        candidate_ticket_id = _ticket_id_for_email_message_id(conn, email.in_reply_to)

    if candidate_ticket_id is None:
        for reference in email.references:
            candidate_ticket_id = _ticket_id_for_email_message_id(conn, reference)
            if candidate_ticket_id is not None:
                break

    if candidate_ticket_id is None and email.thread_id:
        candidate_ticket_id = _ticket_id_for_thread_id(conn, email.thread_id)

    if candidate_ticket_id is None:
        ticket_number = extract_ticket_number(email.subject)
        if ticket_number is not None:
            by_number = ticket_service.get_ticket_by_number(conn, ticket_number)
            candidate_ticket_id = by_number["id"] if by_number else None

    if candidate_ticket_id is None:
        return None

    ticket = ticket_service.get_ticket(conn, candidate_ticket_id)
    if ticket["user_id"] != user_id:
        return None
    return ticket


def _find_message_by_email_id(conn: PGConnection, email_message_id: str) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, ticket_id FROM messages WHERE email_message_id = %s", (email_message_id,)
        )
        return cur.fetchone()


def _ticket_id_for_email_message_id(conn: PGConnection, email_message_id: str) -> uuid.UUID | None:
    with conn.cursor() as cur:
        cur.execute("SELECT ticket_id FROM messages WHERE email_message_id = %s", (email_message_id,))
        row = cur.fetchone()
        return row[0] if row else None


def _ticket_id_for_thread_id(conn: PGConnection, thread_id: str) -> uuid.UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticket_id FROM messages WHERE email_thread_id = %s ORDER BY created_at LIMIT 1",
            (thread_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _existing_thread_id(conn: PGConnection, ticket_id: uuid.UUID) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT email_thread_id FROM messages
            WHERE ticket_id = %s AND email_thread_id IS NOT NULL
            ORDER BY created_at LIMIT 1
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------


def send_admin_reply(conn: PGConnection, ticket: dict, message: dict) -> tuple[bool, str | None, dict]:
    """Called right after an ADMIN message is created with
    `send_email=True` (see app/routers/messages.py). Threads against the
    most recent email-bearing message already on this ticket, sends, and
    -- on success -- returns the message with its email fields filled in.

    On failure, the message row this was called with is returned
    unchanged (email_message_id stays NULL) and this function still
    returns normally rather than raising: the ADMIN message the admin
    wrote was already committed before this was ever called, and a failed
    send must never make that disappear (phase4.md #18 -- "do not silently
    lose the error," and separately, never lose what was already saved).
    A ticket_events row records the failure for the History timeline; the
    router surfaces `email_sent`/`email_error` in its response so the
    dashboard shows it immediately too."""
    user = user_service.get_user(conn, ticket["user_id"])
    prior_message_ids = _prior_email_message_ids(conn, ticket["id"], before=message["created_at"])
    in_reply_to = prior_message_ids[-1] if prior_message_ids else None
    subject = build_reply_subject(ticket["subject"], ticket["ticket_number"])

    provider = get_email_provider()
    try:
        sent: SentEmail = provider.send_email(
            to_email=user["email"],
            subject=subject,
            body=message["body"],
            in_reply_to=in_reply_to,
            references=build_references(prior_message_ids),
        )
    except EmailSendError as exc:
        ticket_event_service.log_event(
            conn,
            ticket["id"],
            event_type="EMAIL_SEND_FAILED",
            actor_type="SYSTEM",
            metadata={"error": str(exc), "message_id": str(message["id"])},
        )
        return False, str(exc), message

    thread_id = _existing_thread_id(conn, ticket["id"]) or sent.message_id
    _stamp_outbound_email(conn, message["id"], sent.message_id, in_reply_to, thread_id)
    updated_message = {
        **message,
        "email_message_id": sent.message_id,
        "in_reply_to": in_reply_to,
        "email_thread_id": thread_id,
    }
    return True, None, updated_message


def _prior_email_message_ids(conn: PGConnection, ticket_id: uuid.UUID, before) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT email_message_id FROM messages
            WHERE ticket_id = %s AND email_message_id IS NOT NULL AND created_at < %s
            ORDER BY created_at
            """,
            (ticket_id, before),
        )
        return [row[0] for row in cur.fetchall()]


def _stamp_outbound_email(
    conn: PGConnection,
    message_id: uuid.UUID,
    email_message_id: str,
    in_reply_to: str | None,
    email_thread_id: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE messages
            SET email_message_id = %s, in_reply_to = %s, email_thread_id = %s
            WHERE id = %s
            """,
            (email_message_id, in_reply_to, email_thread_id, message_id),
        )
