"""Pydantic schema for `TicketEvent` -- see app/schemas/user.py for how this
validates a raw row dict."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.enums import EventActorType


class TicketEventRead(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    event_type: str
    actor_type: EventActorType
    actor_id: uuid.UUID | None
    old_value: str | None
    new_value: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
