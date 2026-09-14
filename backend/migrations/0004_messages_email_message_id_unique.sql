-- Makes duplicate-webhook protection an actual database guarantee instead
-- of "best effort" application logic. Email providers/webhooks can retry
-- delivery of the same inbound email; without this, a retried webhook call
-- could slip through and create two message rows for the same email.
--
-- Nullable columns in Postgres are exempt from UNIQUE conflicts with each
-- other (multiple NULLs are allowed), so this doesn't affect any message
-- that never had an email_message_id in the first place -- e.g. a
-- portal-only admin note that wasn't sent by email.
ALTER TABLE messages
    ADD CONSTRAINT messages_email_message_id_key UNIQUE (email_message_id);
