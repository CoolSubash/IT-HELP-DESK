"""
Exercises app/email/service.py directly (not through HTTP) -- the
5-strategy ticket matching (phase6.md Part 6), the cross-user ownership
check, idempotency, and the student-reply status transitions (phase6.md
Part 8, including the Phase 6 policy change: CLOSED now reopens instead of
staying terminal).
"""
import uuid

from app.email import service as email_service
from app.email.models import InboundEmail
from app.email.parser import extract_ticket_number, normalize_email_address
from app.email.threading import build_reply_subject
from app.enums import TicketStatus
from app.services import message_service, ticket_event_service, ticket_service, user_service


def _make_email(**overrides) -> InboundEmail:
    defaults = dict(
        from_email="student@university.edu",
        to_email="it-support@university.edu",
        subject="Something is broken",
        body="Please help.",
        message_id=f"<{uuid.uuid4()}@gmail.com>",
    )
    defaults.update(overrides)
    return InboundEmail(**defaults)


def _event_types(db, ticket_id) -> list[str]:
    events, _total = ticket_event_service.list_events_for_ticket(db, ticket_id, limit=50, offset=0)
    return [e["event_type"] for e in events]


def test_normalize_email_address_trims_and_lowercases():
    assert normalize_email_address("  John@University.EDU ") == "john@university.edu"


def test_extract_ticket_number_finds_the_tag():
    assert extract_ticket_number("Re: VPN issue [Ticket T-104]") == 104
    assert extract_ticket_number("No tag here") is None


def test_build_reply_subject_adds_re_prefix_once():
    assert build_reply_subject("VPN issue", 104) == "Re: VPN issue [Ticket T-104]"
    assert build_reply_subject("Re: VPN issue", 104) == "Re: VPN issue [Ticket T-104]"


def test_unknown_sender_creates_a_new_user_and_ticket(db):
    email = _make_email(from_email="brand-new-student@university.edu")
    result = email_service.process_inbound_email(db, email)

    assert result.status == "processed"
    assert result.action == "created_new_ticket"
    user = user_service.get_user(db, result.user_id)
    assert user["email"] == "brand-new-student@university.edu"
    assert user["role"] == "STUDENT"

    ticket = ticket_service.get_ticket(db, result.ticket_id)
    assert ticket["ticket_number"] == result.ticket_number


def test_existing_sender_reuses_the_existing_user(db):
    user, _ = user_service.find_or_create_user(db, "existing-email-test@university.edu")

    email = _make_email(from_email="existing-email-test@university.edu")
    result = email_service.process_inbound_email(db, email)

    assert result.user_id == user["id"]
    ticket = ticket_service.get_ticket(db, result.ticket_id)
    assert ticket["user_id"] == user["id"]


def test_existing_user_with_a_new_problem_gets_a_separate_ticket(db):
    """phase6.md Part 15: "Existing student + new email = existing user +
    new ticket" -- distinct from a reply, which must NOT create a second
    ticket."""
    first = _make_email(from_email="two-tickets-test@university.edu", subject="VPN broken")
    first_result = email_service.process_inbound_email(db, first)

    second = _make_email(
        from_email="two-tickets-test@university.edu",
        subject="Printer not working",
        # No in_reply_to/references/matching subject tag -- a genuinely
        # unrelated new problem from the same student.
    )
    second_result = email_service.process_inbound_email(db, second)

    assert second_result.action == "created_new_ticket"
    assert second_result.ticket_id != first_result.ticket_id
    assert second_result.user_id == first_result.user_id


def test_matches_existing_ticket_via_in_reply_to(db):
    first = _make_email(from_email="thread-test-1@university.edu")
    first_result = email_service.process_inbound_email(db, first)

    reply = _make_email(from_email="thread-test-1@university.edu", in_reply_to=first.message_id)
    reply_result = email_service.process_inbound_email(db, reply)

    assert reply_result.action == "attached_to_existing_ticket"
    assert reply_result.ticket_id == first_result.ticket_id


def test_matches_existing_ticket_via_references_when_in_reply_to_is_absent(db):
    first = _make_email(from_email="thread-test-2@university.edu")
    first_result = email_service.process_inbound_email(db, first)

    reply = _make_email(from_email="thread-test-2@university.edu", references=[first.message_id])
    reply_result = email_service.process_inbound_email(db, reply)

    assert reply_result.action == "attached_to_existing_ticket"
    assert reply_result.ticket_id == first_result.ticket_id


def test_matches_existing_ticket_via_provider_thread_id(db):
    first = _make_email(from_email="thread-test-3@university.edu", thread_id="provider-thread-xyz")
    first_result = email_service.process_inbound_email(db, first)

    reply = _make_email(from_email="thread-test-3@university.edu", thread_id="provider-thread-xyz")
    reply_result = email_service.process_inbound_email(db, reply)

    assert reply_result.action == "attached_to_existing_ticket"
    assert reply_result.ticket_id == first_result.ticket_id


def test_matches_existing_ticket_via_subject_ticket_number_fallback(db):
    first = _make_email(from_email="thread-test-4@university.edu", subject="VPN broken")
    first_result = email_service.process_inbound_email(db, first)
    tag = build_reply_subject("VPN broken", first_result.ticket_number)

    reply = _make_email(from_email="thread-test-4@university.edu", subject=tag)
    reply_result = email_service.process_inbound_email(db, reply)

    assert reply_result.action == "attached_to_existing_ticket"
    assert reply_result.ticket_id == first_result.ticket_id


def test_unrelated_email_with_the_same_subject_text_does_not_merge(db):
    """phase6.md Part 6: two tickets can share a subject like "VPN
    Problem" -- subject *text* similarity alone must never attach a new
    email to either one without header/tag evidence."""
    first = _make_email(from_email="same-subject-1@university.edu", subject="VPN Problem")
    first_result = email_service.process_inbound_email(db, first)

    second = _make_email(from_email="same-subject-2@university.edu", subject="VPN Problem")
    second_result = email_service.process_inbound_email(db, second)

    assert second_result.action == "created_new_ticket"
    assert second_result.ticket_id != first_result.ticket_id


def test_does_not_cross_attach_a_spoofed_ticket_reference(db):
    victim = _make_email(from_email="victim@university.edu")
    victim_result = email_service.process_inbound_email(db, victim)

    spoofed = _make_email(from_email="attacker@university.edu", in_reply_to=victim.message_id)
    spoofed_result = email_service.process_inbound_email(db, spoofed)

    assert spoofed_result.action == "created_new_ticket"
    assert spoofed_result.ticket_id != victim_result.ticket_id


def test_no_match_creates_a_new_ticket(db):
    email = _make_email(from_email="no-match-test@university.edu", subject="Totally new issue")
    result = email_service.process_inbound_email(db, email)
    assert result.action == "created_new_ticket"


def test_duplicate_message_id_is_a_no_op(db):
    email = _make_email(from_email="dup-test@university.edu")
    first = email_service.process_inbound_email(db, email)

    duplicate = email_service.process_inbound_email(db, email)

    assert duplicate.status == "already_processed"
    assert duplicate.action == "duplicate"
    assert duplicate.ticket_id == first.ticket_id
    assert duplicate.message_id == first.message_id

    _messages, total = message_service.list_messages_for_ticket(db, first.ticket_id, limit=10, offset=0)
    assert total == 1


def test_reply_to_waiting_for_user_ticket_moves_to_in_progress_without_reopening(db):
    first = _make_email(from_email="status-waiting-test@university.edu")
    first_result = email_service.process_inbound_email(db, first)
    ticket_service.update_ticket_status(db, first_result.ticket_id, TicketStatus.AI_INVESTIGATING)
    ticket_service.update_ticket_status(db, first_result.ticket_id, TicketStatus.WAITING_FOR_USER)

    reply = _make_email(from_email="status-waiting-test@university.edu", in_reply_to=first.message_id)
    email_service.process_inbound_email(db, reply)

    ticket = ticket_service.get_ticket(db, first_result.ticket_id)
    assert ticket["status"] == "IN_PROGRESS"
    # Case C is "the student provided what we were waiting for," not a
    # reopen -- no REOPENED event should be logged for it.
    assert "REOPENED" not in _event_types(db, first_result.ticket_id)


def test_reply_to_resolved_ticket_reopens_to_in_progress(db):
    first = _make_email(from_email="status-resolved-test@university.edu")
    first_result = email_service.process_inbound_email(db, first)
    ticket_service.update_ticket_status(db, first_result.ticket_id, TicketStatus.AI_INVESTIGATING)
    ticket_service.update_ticket_status(db, first_result.ticket_id, TicketStatus.RESOLVED)

    reply = _make_email(from_email="status-resolved-test@university.edu", in_reply_to=first.message_id)
    email_service.process_inbound_email(db, reply)

    ticket = ticket_service.get_ticket(db, first_result.ticket_id)
    assert ticket["status"] == "IN_PROGRESS"
    assert "REOPENED" in _event_types(db, first_result.ticket_id)


def test_reply_to_closed_ticket_reopens_to_in_progress(db):
    """Phase 6 policy change from Phase 4: a reply to a CLOSED ticket now
    reopens it (see the root README's design decisions) instead of
    leaving it CLOSED."""
    first = _make_email(from_email="status-closed-test@university.edu")
    first_result = email_service.process_inbound_email(db, first)
    for status in (TicketStatus.AI_INVESTIGATING, TicketStatus.RESOLVED, TicketStatus.CLOSED):
        ticket_service.update_ticket_status(db, first_result.ticket_id, status)

    reply = _make_email(from_email="status-closed-test@university.edu", in_reply_to=first.message_id)
    reply_result = email_service.process_inbound_email(db, reply)

    assert reply_result.action == "attached_to_existing_ticket"
    ticket = ticket_service.get_ticket(db, first_result.ticket_id)
    assert ticket["status"] == "IN_PROGRESS"
    assert "REOPENED" in _event_types(db, first_result.ticket_id)
