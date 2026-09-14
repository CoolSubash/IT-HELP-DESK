"""Message endpoints, nested under a ticket -- messages don't make sense
without the ticket they belong to, so there's no top-level /messages route."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.email import service as email_service
from app.enums import SenderType
from app.schemas.message import MessageCreate, MessageRead, SendMessageResult
from app.schemas.pagination import Page
from app.services import message_service, ticket_service

router = APIRouter(prefix="/tickets/{ticket_id}/messages", tags=["messages"])


@router.get("", response_model=Page[MessageRead])
def list_messages(
    ticket_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: PGConnection = Depends(get_db),
):
    items, total = message_service.list_messages_for_ticket(db, ticket_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=SendMessageResult, status_code=201)
def create_message(ticket_id: uuid.UUID, payload: MessageCreate, db: PGConnection = Depends(get_db)):
    if payload.send_email and payload.sender_type != SenderType.ADMIN:
        # phase4.md #5: "Do not allow arbitrary users to send emails
        # through this endpoint. For now, only ADMIN messages should
        # trigger outbound email."
        raise HTTPException(
            status_code=400, detail="send_email is only supported for sender_type=ADMIN"
        )

    message = message_service.create_message(
        db, ticket_id, payload.sender_type, payload.sender_id, payload.body
    )

    email_sent = False
    email_error = None
    if payload.send_email:
        ticket = ticket_service.get_ticket(db, ticket_id)
        email_sent, email_error, message = email_service.send_admin_reply(db, ticket, message)

    return SendMessageResult(message=message, email_sent=email_sent, email_error=email_error)
