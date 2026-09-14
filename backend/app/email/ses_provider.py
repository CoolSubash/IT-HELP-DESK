"""
Real AWS SES provider. Only instantiated when EMAIL_PROVIDER=ses (see
app/email/service.py's get_email_provider()) -- boto3 is a real dependency
of this project (requirements.txt), but nothing outside this file
constructs an SES client or imports boto3 directly.

Uses send_raw_email (a MIME message built by hand) rather than SES's
simpler send_email API, because send_email has no way to set the
In-Reply-To/References headers real threading depends on (phase4.md #7-8)
-- send_email only sets Subject/To/From/body.
"""
import email.mime.text
import email.utils

import boto3

from app.email.models import SentEmail
from app.email.provider import EmailProvider, EmailSendError


class AWSSESProvider(EmailProvider):
    def __init__(self, region: str, from_email: str):
        self._client = boto3.client("ses", region_name=region)
        self._from_email = from_email

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> SentEmail:
        message = email.mime.text.MIMEText(body)
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to_email
        message["Message-ID"] = email.utils.make_msgid()
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = " ".join(references)

        try:
            self._client.send_raw_email(
                Source=self._from_email,
                Destinations=[to_email],
                RawMessage={"Data": message.as_string()},
            )
        except Exception as exc:  # boto3/botocore raise provider-specific
            # exception types here; wrapping all of them into our own
            # EmailSendError is the entire point of this abstraction --
            # nothing outside app/email/ should need to know botocore
            # exists.
            raise EmailSendError(str(exc)) from exc

        return SentEmail(message_id=message["Message-ID"])
