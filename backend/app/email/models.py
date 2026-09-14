"""
Normalized email shapes -- the rest of the application (service.py,
routers/email.py) only ever deals with these, never with a specific
provider's raw payload format (a real SES/SNS notification, a SendGrid
webhook, etc). Converting a specific provider's format into `InboundEmail`
is the only place that provider's shape needs to be known; this project's
inbound endpoint already receives the normalized shape directly (per
phase4.md's own example payload), so that conversion step doesn't exist
yet -- it's the seam a real inbound-SES setup would plug into later.
"""
import uuid
from dataclasses import dataclass, field


@dataclass
class InboundEmail:
    from_email: str
    to_email: str
    subject: str
    body: str
    message_id: str
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    thread_id: str | None = None


@dataclass
class SentEmail:
    """What a successful EmailProvider.send_email() call returns."""

    message_id: str


@dataclass
class InboundProcessResult:
    """`status`/`action` match phase6.md Part 13's exact response shape:
    `status` is "processed" for both a new ticket and a matched reply, or
    "already_processed" for a duplicate -- `action` is what actually
    distinguishes "created_new_ticket" / "attached_to_existing_ticket" /
    "duplicate". `user_id` and `ticket_number` are populated even for a
    duplicate result, so the response is equally useful whichever branch
    was taken."""

    status: str  # "processed" | "already_processed"
    action: str  # "created_new_ticket" | "attached_to_existing_ticket" | "duplicate"
    user_id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_number: int
    message_id: uuid.UUID
