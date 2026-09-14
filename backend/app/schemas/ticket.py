"""Pydantic schema for `Ticket` -- see app/schemas/user.py for how this
validates the raw dict app/services/ticket_service.py returns."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.enums import (
    ClosedReason,
    ResolutionSource,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)


class TicketCreate(BaseModel):
    """Input for POST /tickets. Deliberately excludes `status` (always
    starts at NEW -- see the DB default) and `assigned_admin_id`: those
    change through their own dedicated endpoints later in a ticket's life,
    not at creation time.

    `parent_ticket_id` is the exception -- it's optional but set-at-creation
    only (no PATCH for it). Linking "this is the same issue as an earlier
    ticket" is naturally a decision made when the new ticket is filed (by a
    human today; by the AI's history search in a later phase, per
    project.md #7-8), not something that changes afterward."""

    user_id: uuid.UUID
    subject: str
    description: str
    category: TicketCategory
    priority: TicketPriority = TicketPriority.MEDIUM
    parent_ticket_id: uuid.UUID | None = None


class TicketUpdate(BaseModel):
    """Input for PATCH /tickets/{id} -- general field edits. Every field is
    optional so a caller only sends what's changing. Status changes go
    through PATCH /tickets/{id}/status instead, since those need transition
    validation and an audit log entry that a generic field update doesn't."""

    subject: str | None = None
    description: str | None = None
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    resolution: str | None = None
    resolution_source: ResolutionSource | None = None
    resolution_confirmed: bool | None = None
    closed_reason: ClosedReason | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    # Optional: which admin (from the dashboard's "Acting as" picker, see
    # frontend/src/lib/api/*) made this change. When given, the logged
    # ticket_event records actor_type=ADMIN/actor_id=<this>; when omitted
    # (e.g. an automated caller), it falls back to actor_type=SYSTEM.
    changed_by_admin_id: uuid.UUID | None = None


class TicketAssign(BaseModel):
    """No FK to validate this UUID against yet -- there's still no `admins`
    table in Phase 2 (see the root README). This just records whatever
    admin id the caller provides."""

    assigned_admin_id: uuid.UUID


class TicketRead(BaseModel):
    id: uuid.UUID
    # Raw integer -- "T-104"-style display formatting happens only where
    # it's actually needed (email subjects, the /email/inbound response;
    # see app/services/ticket_service.py:format_ticket_number), not baked
    # into every API response.
    ticket_number: int
    user_id: uuid.UUID
    subject: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    resolution: str | None
    resolution_source: ResolutionSource | None
    resolution_confirmed: bool
    assigned_admin_id: uuid.UUID | None
    parent_ticket_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    waiting_since: datetime | None
    follow_up_sent_at: datetime | None
    auto_close_at: datetime | None
    closed_reason: ClosedReason | None


class TicketRelated(BaseModel):
    """Output for GET /tickets/{id}/related. `parent` is the ticket this
    one was raised against (via parent_ticket_id); `children` are tickets
    that named *this* one as their parent -- i.e. the same issue recurring
    (project.md #7-8, "recognize this user has had this issue before")."""

    parent: TicketRead | None
    children: list[TicketRead]


class TicketHistoryEntry(BaseModel):
    """One entry in GET /tickets/{id}/history's combined timeline. `data`
    is deliberately a loose dict rather than a union of MessageRead |
    TicketEventRead | AgentActionRead -- three different shapes merged and
    sorted by `created_at` don't need a strict schema, just enough
    structure for a UI to render each one differently based on `type`."""

    type: str  # "message" | "event" | "agent_action"
    created_at: datetime
    data: dict[str, Any]
