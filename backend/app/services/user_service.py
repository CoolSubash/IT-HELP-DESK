"""
Raw SQL for the `users` table.

`get_user()` raises `NotFoundError` (rather than returning `None`) so
`list_tickets_for_user`/`list_devices_for_user` can call it first to
confirm the user exists, and every 404 in this file is produced the same
way.
"""
import uuid

import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.errors import NotFoundError


def list_users_with_ticket_count(conn: PGConnection) -> list[dict]:
    """Used only by GET /users, for the Users page's "Number of Tickets"
    column (phase3.md #6) -- a LEFT JOIN so a user with zero tickets still
    shows up with ticket_count=0 rather than being silently excluded."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT u.*, count(t.id) AS ticket_count
            FROM users u
            LEFT JOIN tickets t ON t.user_id = u.id
            GROUP BY u.id
            ORDER BY u.created_at
            """
        )
        return cur.fetchall()


def get_user(conn: PGConnection, user_id: uuid.UUID) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(f"user {user_id} not found")
    return row


def find_or_create_user(
    conn: PGConnection,
    email: str,
    name: str | None = None,
    department: str | None = None,
    employee_or_student_id: str | None = None,
) -> tuple[dict, bool]:
    """Returns (user, created). `created=True` only when a new row was
    inserted -- the router uses this to return 201 vs 200. This is the
    piece the future email-ingestion pipeline will call first: "identify
    the user from their email address" (project.md #2), creating a
    bare-minimum row the first time a never-seen address emails in."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing = cur.fetchone()
        if existing is not None:
            return existing, False

        cur.execute(
            """
            INSERT INTO users (id, email, name, department, employee_or_student_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (uuid.uuid4(), email, name, department, employee_or_student_id),
        )
        return cur.fetchone(), True


def list_tickets_for_user(
    conn: PGConnection, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[dict], int]:
    get_user(conn, user_id)  # raises NotFoundError if missing
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM tickets WHERE user_id = %s", (user_id,))
        total = cur.fetchone()["count"]
        cur.execute(
            "SELECT * FROM tickets WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (user_id, limit, offset),
        )
        return cur.fetchall(), total


def list_devices_for_user(conn: PGConnection, user_id: uuid.UUID) -> list[dict]:
    get_user(conn, user_id)  # raises NotFoundError if missing
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM devices WHERE user_id = %s ORDER BY created_at", (user_id,))
        return cur.fetchall()
