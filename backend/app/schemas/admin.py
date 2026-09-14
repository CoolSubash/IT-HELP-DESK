"""Pydantic schema for `Admin` -- see app/schemas/user.py for how this
validates a raw row dict."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class AdminRead(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    created_at: datetime
