"""
Pydantic schema for `User` -- the shape of data returned by the API.

app/services/user_service.py returns plain dicts straight from the
database (via psycopg2's RealDictCursor). This schema validates and
serializes that dict when a route's `response_model=UserRead` -- e.g.
turning the raw string `"STUDENT"` in the `role` column into the actual
`UserRole.STUDENT` enum member, and rejecting the response if a required
field is somehow missing.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.enums import AccountStatus, UserRole


class UserCreate(BaseModel):
    """Input for find-or-create (POST /users). Only `email` is required --
    everything else is optional context that's filled in if/when it's known
    (a real deployment would get `name`/`department` from a directory
    lookup in a later phase, not from the request body)."""

    email: str
    name: str | None = None
    department: str | None = None
    employee_or_student_id: str | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    department: str | None
    employee_or_student_id: str | None
    role: UserRole
    account_status: AccountStatus
    created_at: datetime
    updated_at: datetime


class UserWithTicketCount(UserRead):
    """Used only by GET /users (the Phase 3 Users table needs a "Number of
    Tickets" column) -- GET /users/{id} still returns plain UserRead, since
    a single user's own ticket count isn't useful on that page (its ticket
    history is fetched in full via GET /users/{id}/tickets instead)."""

    ticket_count: int
