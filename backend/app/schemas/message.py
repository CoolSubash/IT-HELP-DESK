"""Pydantic schema for `Message` -- see app/schemas/user.py for how this
validates a raw row dict. No router uses this yet in Phase 1 (messages
aren't exposed over HTTP until a later phase), but it's here so the schema
exists alongside the table."""
import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.enums import MessageDirection, SenderType


class MessageCreate(BaseModel):
    """Input for POST /tickets/{id}/messages. No `direction` field --
    app/services/message_service.py derives it from `sender_type`
    (STUDENT -> INBOUND, AI/ADMIN -> OUTBOUND) so a caller can't create an
    inconsistent combination like `sender_type=STUDENT, direction=OUTBOUND`.

    `sender_id` points at `users.id` when `sender_type` is STUDENT, and (as
    of Phase 3's admins table) at `admins.id` when `sender_type` is ADMIN --
    see migrations/0001_initial_schema.sql's comment on `messages.sender_id`
    for why it's polymorphic with no single DB-level FK. It's required for
    STUDENT (an inbound message always has a known sender), optional for
    ADMIN (an admin reply can be attributed to whoever is "acting" on the
    dashboard, but doesn't have to be), and forbidden for AI (there's no
    row anywhere that "is" the AI). Whether a given `sender_id` actually
    refers to a real row is checked in app/services/message_service.py,
    since only the database knows what currently exists."""

    sender_type: SenderType
    sender_id: uuid.UUID | None = None
    body: str
    # Phase 4: when true, app/routers/messages.py also sends this message
    # out as an email (app/email/service.py:send_admin_reply). Only ever
    # honored for sender_type=ADMIN -- see that router for the explicit
    # rejection otherwise (phase4.md #5: "only ADMIN messages should
    # trigger outbound email").
    send_email: bool = False

    @model_validator(mode="after")
    def _check_sender_id_matches_sender_type(self) -> "MessageCreate":
        if self.sender_type == SenderType.STUDENT and self.sender_id is None:
            raise ValueError("sender_id is required when sender_type is STUDENT")
        if self.sender_type == SenderType.AI and self.sender_id is not None:
            raise ValueError("sender_id must be omitted when sender_type is AI")
        return self


class MessageRead(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_type: SenderType
    sender_id: uuid.UUID | None
    body: str
    subject: str | None
    email_message_id: str | None
    in_reply_to: str | None
    email_thread_id: str | None
    direction: MessageDirection
    created_at: datetime


class SendMessageResult(BaseModel):
    """Response for POST /tickets/{id}/messages. A message can be created
    successfully even when send_email was requested and the send itself
    failed -- those are two different facts (phase4.md #18), so the
    response carries both instead of only ever returning the message and
    leaving a failed send silently indistinguishable from one that was
    never attempted."""

    message: MessageRead
    email_sent: bool
    email_error: str | None = None
