"""
Pydantic schemas for the inbound email webhook. See app/email/models.py
for the internal `InboundEmail` dataclass this gets converted into --
kept separate so the wire format (what a provider or a local test sends)
and the internal shape (what app/email/service.py operates on) can diverge
later without one change forcing the other, e.g. if a real provider's raw
payload ever needs extra normalization before it matches this shape.
"""
import uuid

from pydantic import BaseModel, Field


class EmailInboundPayload(BaseModel):
    """Matches phase4.md's normalized example payload exactly. `from`/`to`
    are Python keywords, hence the aliases -- `populate_by_name` lets tests
    construct this with `from_email=`/`to_email=` too, not just the raw
    JSON alias."""

    model_config = {"populate_by_name": True}

    from_email: str = Field(alias="from")
    to_email: str = Field(alias="to")
    subject: str
    body: str
    message_id: str
    in_reply_to: str | None = None
    references: list[str] = []
    thread_id: str | None = None


class EmailInboundResult(BaseModel):
    """Matches phase6.md Part 13's exact response examples: `status` is
    "processed" (new ticket or matched reply) or "already_processed"
    (duplicate); `action` distinguishes "created_new_ticket" /
    "attached_to_existing_ticket" / "duplicate". `ticket_number` is the
    formatted "T-104" string (see
    app/services/ticket_service.py:format_ticket_number) -- the router is
    the one place that formats it; app/email/service.py deals in the raw
    integer throughout."""

    status: str
    action: str
    message_id: uuid.UUID
    user_id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_number: str
