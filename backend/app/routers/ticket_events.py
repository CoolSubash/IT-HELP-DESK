"""Read-only endpoint for a ticket's audit trail. Nothing creates events
through the API directly -- they're always a side effect of a ticket
mutation (see app/services/ticket_service.py calling
ticket_event_service.log_event)."""
import uuid

from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.schemas.pagination import Page
from app.schemas.ticket_event import TicketEventRead
from app.services import ticket_event_service

router = APIRouter(prefix="/tickets/{ticket_id}/events", tags=["ticket-events"])


@router.get("", response_model=Page[TicketEventRead])
def list_ticket_events(
    ticket_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: PGConnection = Depends(get_db),
):
    items, total = ticket_event_service.list_events_for_ticket(db, ticket_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
