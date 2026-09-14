"""Read-only endpoint for a ticket's AI action log. No create endpoint --
nothing writes agent_actions until the AI agent exists in a later phase."""
import uuid

from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.schemas.agent_action import AgentActionRead
from app.schemas.pagination import Page
from app.services import agent_action_service

router = APIRouter(prefix="/tickets/{ticket_id}/agent-actions", tags=["agent-actions"])


@router.get("", response_model=Page[AgentActionRead])
def list_agent_actions(
    ticket_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: PGConnection = Depends(get_db),
):
    items, total = agent_action_service.list_agent_actions_for_ticket(db, ticket_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
