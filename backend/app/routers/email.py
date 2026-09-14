"""
Inbound email webhook. This is the one endpoint in the app with no
existing-caller identity to lean on (every other write endpoint is called
by the dashboard, which at least has the "acting as" convention) -- a real
deployment would front this with SES/SNS signature verification, which
this project doesn't implement (there's no real SES/SNS configured
anywhere here). `_verify_webhook_secret` is an explicit, documented
stand-in for that, not a replacement for it in production (see
app/config.py's email_webhook_dev_mode/email_webhook_secret and the root
README's security notes).
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from psycopg2.extensions import connection as PGConnection

from app.config import settings
from app.database import get_db
from app.email.models import InboundEmail
from app.email.service import process_inbound_email
from app.schemas.email import EmailInboundPayload, EmailInboundResult
from app.services.ticket_service import format_ticket_number

router = APIRouter(prefix="/email", tags=["email"])


def _verify_webhook_secret(x_webhook_secret: str | None = Header(default=None)) -> None:
    if settings.email_webhook_dev_mode:
        return
    if not settings.email_webhook_secret or x_webhook_secret != settings.email_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid or missing webhook secret")


@router.post(
    "/inbound",
    response_model=EmailInboundResult,
    dependencies=[Depends(_verify_webhook_secret)],
)
def receive_inbound_email(payload: EmailInboundPayload, db: PGConnection = Depends(get_db)):
    email = InboundEmail(
        from_email=payload.from_email,
        to_email=payload.to_email,
        subject=payload.subject,
        body=payload.body,
        message_id=payload.message_id,
        in_reply_to=payload.in_reply_to,
        references=payload.references,
        thread_id=payload.thread_id,
    )
    result = process_inbound_email(db, email)
    return EmailInboundResult(
        status=result.status,
        action=result.action,
        message_id=result.message_id,
        user_id=result.user_id,
        ticket_id=result.ticket_id,
        ticket_number=format_ticket_number(result.ticket_number),
    )
