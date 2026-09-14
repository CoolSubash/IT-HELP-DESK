"""
Ticket endpoints. Status changes and admin assignment are split into their
own PATCH endpoints (rather than folded into the general update) because
they need different rules: status changes are checked against the
transition graph in app/services/ticket_service.py and logged to
ticket_events, and assignment is logged too -- a generic field edit isn't.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.enums import TicketCategory, TicketPriority, TicketStatus
from app.schemas.pagination import Page
from app.schemas.ticket import (
    TicketAssign,
    TicketCreate,
    TicketHistoryEntry,
    TicketRead,
    TicketRelated,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketRead, status_code=201)
def create_ticket(payload: TicketCreate, db: PGConnection = Depends(get_db)):
    return ticket_service.create_ticket(
        db,
        user_id=payload.user_id,
        subject=payload.subject,
        description=payload.description,
        category=payload.category.value,
        priority=payload.priority.value,
        parent_ticket_id=payload.parent_ticket_id,
    )


@router.get("", response_model=Page[TicketRead])
def list_tickets(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: TicketStatus | None = Query(default=None),
    priority: TicketPriority | None = Query(default=None),
    category: TicketCategory | None = Query(default=None),
    assigned_admin_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    db: PGConnection = Depends(get_db),
):
    items, total = ticket_service.list_tickets(
        db,
        limit,
        offset,
        status=status.value if status else None,
        priority=priority.value if priority else None,
        category=category.value if category else None,
        assigned_admin_id=assigned_admin_id,
        search=search,
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: uuid.UUID, db: PGConnection = Depends(get_db)):
    return ticket_service.get_ticket(db, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket(ticket_id: uuid.UUID, payload: TicketUpdate, db: PGConnection = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    return ticket_service.update_ticket(db, ticket_id, updates)


@router.patch("/{ticket_id}/status", response_model=TicketRead)
def update_ticket_status(
    ticket_id: uuid.UUID, payload: TicketStatusUpdate, db: PGConnection = Depends(get_db)
):
    return ticket_service.update_ticket_status(
        db, ticket_id, payload.status, changed_by_admin_id=payload.changed_by_admin_id
    )


@router.patch("/{ticket_id}/assign", response_model=TicketRead)
def assign_ticket(ticket_id: uuid.UUID, payload: TicketAssign, db: PGConnection = Depends(get_db)):
    return ticket_service.assign_ticket(db, ticket_id, payload.assigned_admin_id)


@router.get("/{ticket_id}/related", response_model=TicketRelated)
def get_related_tickets(ticket_id: uuid.UUID, db: PGConnection = Depends(get_db)):
    return ticket_service.get_related_tickets(db, ticket_id)


@router.get("/{ticket_id}/history", response_model=list[TicketHistoryEntry])
def get_ticket_history(ticket_id: uuid.UUID, db: PGConnection = Depends(get_db)):
    return ticket_service.get_ticket_history(db, ticket_id)
