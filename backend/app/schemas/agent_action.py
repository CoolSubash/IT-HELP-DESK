"""Pydantic schema for `AgentAction` -- see app/schemas/user.py for how this
validates a raw row dict."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class AgentActionRead(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    action_type: str
    tool_name: str | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    reason: str | None
    confidence: Decimal | None
    status: str
    created_at: datetime
