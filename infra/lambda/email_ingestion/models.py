"""
The normalized shape this Lambda produces -- matches
backend/app/email/models.py:InboundEmail field-for-field, and
backend/app/schemas/email.py:EmailInboundPayload's wire format exactly
(phase5.md #3's example JSON).

This is a standalone copy, not an import from backend/: the Lambda is a
separate deployable unit with its own dependency zip, and doesn't share a
Python path with the FastAPI app. Duplicating this one small dataclass is
cheaper than trying to share a package between two independently deployed
codebases for a shape this small.
"""
from dataclasses import dataclass, field


@dataclass
class NormalizedEmail:
    from_email: str
    to_email: str
    subject: str
    body: str
    message_id: str
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    thread_id: str | None = None

    def to_json_dict(self) -> dict:
        """Matches backend/app/schemas/email.py:EmailInboundPayload's field
        names exactly (`from`/`to`, not `from_email`/`to_email` -- those are
        Python-side aliases on the FastAPI side for the same JSON keys)."""
        return {
            "from": self.from_email,
            "to": self.to_email,
            "subject": self.subject,
            "body": self.body,
            "message_id": self.message_id,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "thread_id": self.thread_id,
        }
