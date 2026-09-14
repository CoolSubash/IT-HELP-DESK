-- Changes tickets.user_id and devices.user_id from ON DELETE CASCADE to
-- ON DELETE RESTRICT.
--
-- Why: a user should never actually be hard-deleted in this system -- the
-- AI depends on historical ticket data surviving indefinitely (project.md
-- #7-8: "recognize this user has had this issue before" / "search similar
-- historical incidents"). Nothing in the API deletes users today, so
-- CASCADE has never actually fired in practice -- but that safety only
-- held "by accident," dependent on nobody ever adding a delete endpoint.
-- RESTRICT makes it a real guarantee instead: Postgres will now refuse to
-- delete a user who still has tickets or devices, rather than silently
-- wiping out their entire history.
--
-- The correct way to remove a user from active use is to deactivate them
-- (UPDATE users SET account_status = 'DISABLED' ...), which touches
-- nothing else -- not to delete the row. If a real privacy/retention
-- policy ever requires erasing personal data, the right operation is to
-- anonymize the PII columns on the users row in place (email, name,
-- department, employee_or_student_id) while keeping the row itself, so
-- every tickets.user_id / devices.user_id foreign key still resolves and
-- ticket history stays intact for the AI to learn from. Neither of those
-- operations exists yet -- see the root README -- since nothing in the
-- app calls for them until real admin user-management is built.
ALTER TABLE tickets
    DROP CONSTRAINT tickets_user_id_fkey,
    ADD CONSTRAINT tickets_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;

ALTER TABLE devices
    DROP CONSTRAINT devices_user_id_fkey,
    ADD CONSTRAINT devices_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
