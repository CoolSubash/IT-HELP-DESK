-- Two additive columns for Phase 6 ("Phase 5B" internally) --
-- ticket/email-thread processing polish.

-- A human-friendly sequential ticket number, displayed as "T-104" --
-- phase6.md's email-subject and API-response examples call for this
-- ("Re: ... [Ticket T-104]", {"ticket_number": "T-104"}) rather than the
-- UUID-prefix short id used elsewhere in the app up to this phase. The
-- UUID `id` column remains the actual primary key and every foreign key
-- target; this column exists purely for human-facing display and for a
-- more reliable subject-tag fallback match (an exact integer lookup
-- instead of a "hope an 8-hex-char UUID prefix doesn't collide" guess).
ALTER TABLE tickets
    ADD COLUMN ticket_number INTEGER GENERATED ALWAYS AS IDENTITY;

ALTER TABLE tickets
    ADD CONSTRAINT tickets_ticket_number_key UNIQUE (ticket_number);

-- Every inbound email's own subject line, preserved as part of the
-- historical record (phase6.md Part 9/10: "every communication is
-- historical data" -- a message's own subject line, which can literally
-- change across a thread's replies, wasn't being kept anywhere before
-- this). Nullable: only emails have a subject line to preserve; a
-- dashboard-composed ADMIN message has none until it's actually sent as
-- an email, and even then the generated subject isn't written back onto
-- the message row (see app/email/threading.py).
ALTER TABLE messages ADD COLUMN subject VARCHAR(998);
