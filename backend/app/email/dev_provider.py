"""
Local-development email provider. Does not contact any real email service
-- it prints the email and fabricates a Message-ID, which is enough to
exercise the entire threading/matching/idempotency loop without needing
AWS credentials. Selected by EMAIL_PROVIDER=dev, the default (see
app/config.py) -- this is what this project actually runs against; see
the root README for why AWSSESProvider can't be live-tested here.
"""
import uuid

from app.email.models import SentEmail
from app.email.provider import EmailProvider


class DevEmailProvider(EmailProvider):
    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> SentEmail:
        message_id = f"<dev-{uuid.uuid4()}@localhost>"
        # A plain print(), not the logging module: this project has no
        # logging configuration set up anywhere (see root README), and
        # Python's default log level (WARNING) would silently swallow a
        # logger.info() call -- defeating the entire point of a provider
        # whose job is to let a developer see what would have been sent.
        print(
            f"--- DEV EMAIL ---\n"
            f"To: {to_email}\n"
            f"Subject: {subject}\n"
            f"In-Reply-To: {in_reply_to}\n"
            f"References: {references}\n"
            f"Message-ID: {message_id}\n\n"
            f"{body}\n"
            f"-----------------"
        )
        return SentEmail(message_id=message_id)
