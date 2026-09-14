-- Adds the `admins` table Phase 1 deliberately deferred (see
-- migrations/0001_initial_schema.sql's comment on tickets.assigned_admin_id).
-- No password/login column -- there is still no authentication in this
-- project. This table exists purely so a ticket can be assigned to a real,
-- named person instead of an opaque UUID, and so the dashboard has
-- something to populate an "Acting as" picker from (Phase 3's stand-in for
-- a logged-in identity).
CREATE TABLE admins (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Now that admins exist, tickets.assigned_admin_id can finally get a real
-- foreign key. Every existing row has this column NULL (nothing outside
-- the seed script has ever set it), so this ALTER is safe to run as-is.
ALTER TABLE tickets
    ADD CONSTRAINT tickets_assigned_admin_id_fkey
    FOREIGN KEY (assigned_admin_id) REFERENCES admins(id) ON DELETE SET NULL;
