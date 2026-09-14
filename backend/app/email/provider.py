"""
The abstraction phase4.md calls out as the most important separation in
this phase: nothing outside app/email/ should know whether email is being
sent through AWS SES, logged locally for development, or (later) some
other provider. app/email/service.py depends only on this interface,
never on a concrete provider class directly.
"""
from abc import ABC, abstractmethod

from app.email.models import SentEmail


class EmailProvider(ABC):
    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> SentEmail:
        """Sends one email. Must raise EmailSendError if the provider
        rejects or fails to send it -- never return a "sort of succeeded"
        result. Callers (see app/email/service.py's send_admin_reply) rely
        on "no exception" meaning "actually sent"."""
        raise NotImplementedError


class EmailSendError(Exception):
    """Raised by an EmailProvider when sending fails. Caught by
    app/email/service.py's send_admin_reply, which decides what a failure
    means for the ticket -- the message a student would have received is
    never lost from the record even when this happens (see that
    function's docstring)."""
