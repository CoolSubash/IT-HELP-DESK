"""
Builds the outbound pieces of an email that describe how it threads -- the
subject line and the References header -- kept separate from service.py so
"what does a reply's subject/References look like" has one obvious place
to answer, independent of how the message actually gets sent.
"""


def build_reply_subject(ticket_subject: str, ticket_number: int) -> str:
    """`ticket_number` is the human-friendly sequential number
    (tickets.ticket_number, migrations/0005), formatted "T-104" -- Phase 4
    used an 8-character UUID prefix here instead; phase6.md's examples
    call for this format specifically. This is a fallback identifier only
    (phase6.md Part 3/6) -- headers remain the primary way a reply gets
    matched back to its ticket; see
    app/email/parser.py:extract_ticket_number for where this gets read
    back out, and app/email/service.py for why headers are always checked
    first."""
    tag = f"T-{ticket_number}"
    if ticket_subject.strip().lower().startswith("re:"):
        return f"{ticket_subject} [Ticket {tag}]"
    return f"Re: {ticket_subject} [Ticket {tag}]"


def build_references(prior_email_message_ids: list[str]) -> list[str]:
    """The References header is every Message-ID in the thread so far, in
    order. Not stored as its own column (messages has no `references`
    field -- only `in_reply_to` and `email_thread_id`, per
    migrations/0001_initial_schema.sql) -- it's assembled at send time from
    every email_message_id already recorded against the ticket instead."""
    return prior_email_message_ids
