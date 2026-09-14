-- Creates all seven Phase 1 tables, their constraints, and indexes.
-- Applied by `python -m migrations.run_migrations` (see that file).

-- Postgres has no built-in "ON UPDATE CURRENT_TIMESTAMP" the way MySQL
-- does, so a trigger function is the standard way to keep `updated_at`
-- current automatically. Attached to every table below that has an
-- updated_at column.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- users: students/employees who email IT support. No login -- identified
-- by email only (see project.md #2, phase1.md "no authentication yet").
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    department VARCHAR(255),
    employee_or_student_id VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'STUDENT'
        CHECK (role IN ('STUDENT', 'STAFF', 'FACULTY', 'ADMIN')),
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (account_status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_users_email ON users (email);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- tickets: the central object. One ticket per IT issue per user.
--
-- assigned_admin_id is a plain UUID column with NO foreign key: Phase 1
-- explicitly excludes an admins table (phase1.md requirement #10). Kept as
-- a real column now so the table's shape doesn't change later -- once an
-- `admins` table exists, a migration adds `REFERENCES admins(id)` onto this
-- same column without renaming anything.
CREATE TABLE tickets (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(20) NOT NULL
        CHECK (category IN (
            'VPN', 'WIFI', 'PASSWORD', 'SOFTWARE', 'HARDWARE',
            'ACCOUNT', 'EMAIL', 'NETWORK', 'OTHER'
        )),
    priority VARCHAR(10) NOT NULL DEFAULT 'MEDIUM'
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')),
    status VARCHAR(20) NOT NULL DEFAULT 'NEW'
        CHECK (status IN (
            'NEW', 'AI_INVESTIGATING', 'WAITING_FOR_USER', 'WAITING_FOR_ADMIN',
            'IN_PROGRESS', 'RESOLVED', 'ESCALATED', 'CLOSED'
        )),
    resolution TEXT,
    resolution_source VARCHAR(10)
        CHECK (resolution_source IN ('AI', 'ADMIN')),
    resolution_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_admin_id UUID,  -- no FK yet -- see comment above
    parent_ticket_id UUID REFERENCES tickets(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    waiting_since TIMESTAMPTZ,
    follow_up_sent_at TIMESTAMPTZ,
    auto_close_at TIMESTAMPTZ,
    closed_reason VARCHAR(20)
        CHECK (closed_reason IN ('RESOLVED', 'USER_INACTIVE', 'DUPLICATE', 'WITHDRAWN', 'OTHER'))
);
CREATE INDEX ix_tickets_user_id ON tickets (user_id);
CREATE INDEX ix_tickets_status ON tickets (status);
CREATE INDEX ix_tickets_created_at ON tickets (created_at);

CREATE TRIGGER trg_tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- messages: every inbound/outbound piece of a ticket's conversation, plus
-- the email threading headers a later phase uses to match a reply to its
-- existing ticket (project.md #4). No updated_at -- a message is an
-- immutable record of something that was sent, not an editable entity.
--
-- sender_id is polymorphic: points at users.id only when sender_type =
-- 'STUDENT'; NULL for AI/ADMIN senders, since neither is a row in any
-- table. No foreign key, for the same reason as assigned_admin_id above.
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender_type VARCHAR(10) NOT NULL
        CHECK (sender_type IN ('STUDENT', 'AI', 'ADMIN')),
    sender_id UUID,
    body TEXT NOT NULL,
    email_message_id VARCHAR(500),
    in_reply_to VARCHAR(500),
    email_thread_id VARCHAR(500),
    direction VARCHAR(10) NOT NULL
        CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_messages_ticket_id ON messages (ticket_id);
CREATE INDEX ix_messages_email_thread_id ON messages (email_thread_id);
CREATE INDEX ix_messages_email_message_id ON messages (email_message_id);

-- ticket_events: append-only audit trail of what changed on a ticket and
-- why (e.g. status NEW -> AI_INVESTIGATING). event_type has no CHECK
-- constraint -- it's an open-ended, growing taxonomy (see
-- app/enums.py). actor_id is polymorphic like messages.sender_id.
CREATE TABLE ticket_events (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    actor_type VARCHAR(10) NOT NULL
        CHECK (actor_type IN ('STUDENT', 'AI', 'ADMIN', 'SYSTEM')),
    actor_id UUID,
    old_value VARCHAR(255),
    new_value VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ticket_events_ticket_id ON ticket_events (ticket_id);
CREATE INDEX ix_ticket_events_event_type ON ticket_events (event_type);

-- agent_actions: the AI's audit trail (project.md #11). action_type,
-- tool_name, and status have no CHECK constraint -- the tool registry
-- (project.md #9) and the approval workflow (project.md #10) don't exist
-- yet, so we don't lock in their values at the database level.
CREATE TABLE agent_actions (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    action_type VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100),
    input JSONB,
    output JSONB,
    reason TEXT,
    confidence NUMERIC(3, 2),
    status VARCHAR(50) NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_actions_ticket_id ON agent_actions (ticket_id);
CREATE INDEX ix_agent_actions_action_type ON agent_actions (action_type);

-- knowledge_documents: metadata for IT documentation a later RAG phase
-- will chunk and embed (project.md #6). No chunks/embeddings table yet.
-- uploaded_by has no FK, same reason as tickets.assigned_admin_id.
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    storage_location VARCHAR(1000) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING'
        CHECK (status IN ('PROCESSING', 'READY', 'FAILED', 'ARCHIVED')),
    uploaded_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_knowledge_documents_category ON knowledge_documents (category);

CREATE TRIGGER trg_knowledge_documents_updated_at
    BEFORE UPDATE ON knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- devices: hardware associated with a user, for the AI to check during
-- investigation in a later phase (project.md #16).
CREATE TABLE devices (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_identifier VARCHAR(255) NOT NULL UNIQUE,
    device_type VARCHAR(50),
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    operating_system VARCHAR(100),
    os_version VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'FLAGGED', 'RETIRED')),
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_devices_user_id ON devices (user_id);

CREATE TRIGGER trg_devices_updated_at
    BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
