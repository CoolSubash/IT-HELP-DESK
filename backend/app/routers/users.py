"""
User endpoints. `POST /users` is find-or-create (idempotent by email) --
there's still no login, so this is the closest thing to "registration":
call it with an email and get back the same user row every time, created
the first time. This is the shape a later phase's email-ingestion pipeline
will call to identify the sender of an inbound email.
"""
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.schemas.device import DeviceRead
from app.schemas.pagination import Page
from app.schemas.ticket import TicketRead
from app.schemas.user import UserCreate, UserRead, UserWithTicketCount
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead)
def find_or_create_user(
    payload: UserCreate, response: Response, db: PGConnection = Depends(get_db)
):
    user, created = user_service.find_or_create_user(
        db, payload.email, payload.name, payload.department, payload.employee_or_student_id
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return user


@router.get("", response_model=list[UserWithTicketCount])
def list_users(db: PGConnection = Depends(get_db)):
    return user_service.list_users_with_ticket_count(db)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: uuid.UUID, db: PGConnection = Depends(get_db)):
    return user_service.get_user(db, user_id)


@router.get("/{user_id}/tickets", response_model=Page[TicketRead])
def get_user_tickets(
    user_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: PGConnection = Depends(get_db),
):
    items, total = user_service.list_tickets_for_user(db, user_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/devices", response_model=list[DeviceRead])
def get_user_devices(user_id: uuid.UUID, db: PGConnection = Depends(get_db)):
    return user_service.list_devices_for_user(db, user_id)
