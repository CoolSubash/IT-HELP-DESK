"""
Shared enums for fields with a fixed, small set of valid values.

These mirror CHECK constraints written directly in
migrations/0001_initial_schema.sql (e.g.
`CHECK (role IN ('STUDENT','STAFF','FACULTY','ADMIN'))`). The database is
what actually enforces valid values -- these Python enums exist so
application code gets autocomplete and a typo like `UserRole.STUDET` fails
at import time instead of silently inserting a bad row.

Services return raw dicts straight from the database (see app/services/*.py)
-- a column like `role` comes back as a plain string, not one of these enum
members. The conversion into an actual `UserRole` happens later, at the API
boundary: Pydantic validates the string against the schema's declared enum
type (app/schemas/user.py's `role: UserRole`) and coerces it automatically.
These enums exist purely for that validation plus editor autocomplete when
writing a SQL query's parameters by hand.

Fields that describe an open-ended, fast-growing taxonomy --
`ticket_events.event_type`, `agent_actions.action_type`, `agent_actions.tool_name`,
`agent_actions.status` -- are intentionally left as plain strings with no
CHECK constraint and no enum here. Later phases will add new AI tools and
event types continuously; we don't want a migration every time one is
added, and the approval-workflow states for `agent_actions.status` aren't
final until the human-in-the-loop feature (project.md #10) is actually built.
"""
from enum import Enum


class UserRole(str, Enum):
    STUDENT = "STUDENT"
    STAFF = "STAFF"
    FACULTY = "FACULTY"
    ADMIN = "ADMIN"


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class TicketCategory(str, Enum):
    VPN = "VPN"
    WIFI = "WIFI"
    PASSWORD = "PASSWORD"
    SOFTWARE = "SOFTWARE"
    HARDWARE = "HARDWARE"
    ACCOUNT = "ACCOUNT"
    EMAIL = "EMAIL"
    NETWORK = "NETWORK"
    OTHER = "OTHER"


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TicketStatus(str, Enum):
    NEW = "NEW"
    AI_INVESTIGATING = "AI_INVESTIGATING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    WAITING_FOR_ADMIN = "WAITING_FOR_ADMIN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


class ResolutionSource(str, Enum):
    AI = "AI"
    ADMIN = "ADMIN"


class ClosedReason(str, Enum):
    RESOLVED = "RESOLVED"
    USER_INACTIVE = "USER_INACTIVE"
    DUPLICATE = "DUPLICATE"
    WITHDRAWN = "WITHDRAWN"
    OTHER = "OTHER"


class SenderType(str, Enum):
    STUDENT = "STUDENT"
    AI = "AI"
    ADMIN = "ADMIN"


class MessageDirection(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class EventActorType(str, Enum):
    STUDENT = "STUDENT"
    AI = "AI"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class DeviceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    FLAGGED = "FLAGGED"
    RETIRED = "RETIRED"


class KnowledgeDocumentStatus(str, Enum):
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"
