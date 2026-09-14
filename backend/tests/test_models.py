"""
Exercises the constraints phase1.md calls out explicitly: unique email,
foreign keys, and the self-referencing parent_ticket_id relationship.

Note: Postgres checks UNIQUE/FOREIGN KEY constraints immediately, at the
`cur.execute()` that violates them -- not later at `conn.commit()`. Once a
statement raises, the connection is left in an aborted-transaction state,
so every test below calls `db.rollback()` right after the expected error to
reset it.
"""
import uuid

import psycopg2.errors
import pytest


def test_user_email_must_be_unique(db):
    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (id, email, name) VALUES (%s, %s, %s)",
        (uuid.uuid4(), "dup-email-test@university.edu", "A"),
    )
    db.commit()

    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO users (id, email, name) VALUES (%s, %s, %s)",
            (uuid.uuid4(), "dup-email-test@university.edu", "B"),
        )
    db.rollback()


def test_ticket_requires_an_existing_user(db):
    cur = db.cursor()
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute(
            """
            INSERT INTO tickets (id, user_id, subject, description, category)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (uuid.uuid4(), uuid.uuid4(), "x", "x", "OTHER"),  # no such user
        )
    db.rollback()


def test_ticket_can_reference_a_parent_ticket(db):
    cur = db.cursor()
    user_id = uuid.uuid4()
    cur.execute(
        "INSERT INTO users (id, email, name) VALUES (%s, %s, %s)",
        (user_id, "parent-ticket-test@university.edu", "A"),
    )

    parent_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO tickets (id, user_id, subject, description, category)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (parent_id, user_id, "first", "d", "VPN"),
    )

    child_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO tickets (id, user_id, subject, description, category, parent_ticket_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (child_id, user_id, "second", "d", "VPN", parent_id),
    )
    db.commit()

    cur.execute("SELECT parent_ticket_id FROM tickets WHERE id = %s", (child_id,))
    assert cur.fetchone()[0] == parent_id


def test_deleting_a_user_with_tickets_is_blocked(db):
    """Locks in migrations/0003_restrict_user_deletion.sql: a user with
    ticket history must never be hard-deletable, since the AI depends on
    that history surviving indefinitely (see root README). The correct way
    to remove a user from active use is to deactivate them
    (account_status = 'DISABLED'), not delete the row."""
    cur = db.cursor()
    user_id = uuid.uuid4()
    cur.execute(
        "INSERT INTO users (id, email, name) VALUES (%s, %s, %s)",
        (user_id, "restrict-delete-test@university.edu", "A"),
    )
    cur.execute(
        "INSERT INTO tickets (id, user_id, subject, description, category) VALUES (%s, %s, %s, %s, %s)",
        (uuid.uuid4(), user_id, "x", "x", "OTHER"),
    )
    db.commit()

    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.rollback()
