"""
Inserts a small, realistic demo dataset so the API/dashboard can be
verified without building the email/AI pipeline yet (phase1.md's seed data
requirements, plus two admins added for Phase 3's dashboard):

- one user (John Smith)
- two admins (for the dashboard's "Acting as" picker and assignment)
- three tickets: one open (assigned to an admin), one closed, and one that
  links back to the open one via parent_ticket_id (the "recurring issue" case)
- a full STUDENT -> AI -> ADMIN -> STUDENT message thread on the open ticket
- ticket_events recording the status changes behind that thread
- agent_actions showing the AI searching the knowledge base and escalating

All plain parameterized SQL -- every %s is filled in by psycopg2, never by
string formatting, so this is safe from SQL injection even though the
values here happen to be hardcoded.

Run with: `python -m seed.seed_data` (see root README).
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from app.config import settings

psycopg2.extras.register_uuid()


def seed(conn=None) -> None:
    """Runs the seed. Accepts an existing connection (used by tests) so the
    logic isn't duplicated -- if none is given, opens and closes its own."""
    owns_connection = conn is None
    if conn is None:
        conn = psycopg2.connect(settings.database_url)

    try:
        now = datetime.now(timezone.utc)
        cur = conn.cursor()

        john_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO users (id, email, name, department, role, account_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (john_id, "john@university.edu", "John Smith", "Computer Science", "STUDENT", "ACTIVE"),
        )

        alice_id = uuid.uuid4()
        bob_id = uuid.uuid4()
        cur.executemany(
            "INSERT INTO admins (id, name, email) VALUES (%s, %s, %s)",
            [
                (alice_id, "Alice Nguyen", "alice.nguyen@it.university.edu"),
                (bob_id, "Bob Carter", "bob.carter@it.university.edu"),
            ],
        )

        cur.execute(
            """
            INSERT INTO devices (
                id, user_id, device_identifier, device_type, manufacturer,
                model, operating_system, os_version, status, last_seen_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), john_id, "JOHNSMITH-LAPTOP-01", "laptop", "Dell",
                "XPS 15", "Windows", "11", "ACTIVE", now,
            ),
        )

        # --- Ticket 1: OPEN, full STUDENT -> AI -> ADMIN -> STUDENT thread ---
        open_ticket_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO tickets (
                id, user_id, subject, description, category, priority, status, assigned_admin_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                open_ticket_id, john_id, "VPN not working",
                "My VPN has stopped connecting to the university network. "
                "It was working yesterday.",
                "VPN", "HIGH", "WAITING_FOR_ADMIN", alice_id,
            ),
        )

        cur.executemany(
            """
            INSERT INTO messages (id, ticket_id, sender_type, sender_id, body, direction, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    uuid.uuid4(), open_ticket_id, "STUDENT", john_id,
                    "My VPN has stopped connecting to the university network. "
                    "It was working yesterday.",
                    "INBOUND", now - timedelta(hours=3),
                ),
                (
                    uuid.uuid4(), open_ticket_id, "AI", None,
                    "Thanks for reaching out. I checked the VPN service and it's "
                    "currently operational. I found that your VPN certificate expired "
                    "yesterday, which matches when the issue started. Certificate renewal "
                    "requires IT administrator approval, so I've escalated this ticket.",
                    "OUTBOUND", now - timedelta(hours=2, minutes=45),
                ),
                (
                    uuid.uuid4(), open_ticket_id, "ADMIN", None,
                    "Hi John, I've renewed your VPN certificate. Please restart your "
                    "VPN client and try again.",
                    "OUTBOUND", now - timedelta(hours=1),
                ),
                (
                    uuid.uuid4(), open_ticket_id, "STUDENT", john_id,
                    "That worked, thank you!",
                    "INBOUND", now - timedelta(minutes=30),
                ),
            ],
        )

        cur.execute(
            """
            INSERT INTO ticket_events (id, ticket_id, event_type, actor_type, old_value, new_value, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (uuid.uuid4(), open_ticket_id, "STATUS_CHANGED", "SYSTEM", None, "NEW", now - timedelta(hours=3)),
        )
        cur.execute(
            """
            INSERT INTO ticket_events (id, ticket_id, event_type, actor_type, old_value, new_value, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), open_ticket_id, "STATUS_CHANGED", "AI", "NEW", "AI_INVESTIGATING",
                now - timedelta(hours=2, minutes=55),
            ),
        )
        cur.execute(
            """
            INSERT INTO ticket_events (
                id, ticket_id, event_type, actor_type, old_value, new_value, metadata, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), open_ticket_id, "STATUS_CHANGED", "AI",
                "AI_INVESTIGATING", "WAITING_FOR_ADMIN",
                psycopg2.extras.Json({"reason": "certificate renewal requires administrator approval"}),
                now - timedelta(hours=2, minutes=45),
            ),
        )
        cur.execute(
            """
            INSERT INTO ticket_events
                (id, ticket_id, event_type, actor_type, actor_id, old_value, new_value, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), open_ticket_id, "ASSIGNED", "ADMIN", alice_id,
                None, str(alice_id), now - timedelta(hours=2, minutes=40),
            ),
        )

        cur.execute(
            """
            INSERT INTO agent_actions (
                id, ticket_id, action_type, tool_name, input, output, reason, confidence,
                status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), open_ticket_id, "KNOWLEDGE_SEARCH", "search_knowledge_base",
                psycopg2.extras.Json({"query": "VPN not connecting"}),
                psycopg2.extras.Json(
                    {"documents": ["VPN Troubleshooting Guide", "VPN Certificate Policy"]}
                ),
                "Looking for documented causes of VPN connection failures.",
                0.82, "executed", now - timedelta(hours=2, minutes=50),
            ),
        )
        cur.execute(
            """
            INSERT INTO agent_actions (
                id, ticket_id, action_type, tool_name, input, output, reason, confidence,
                status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), open_ticket_id, "ESCALATION", "assign_ticket",
                psycopg2.extras.Json({"reason": "certificate_renewal_requires_admin_approval"}),
                psycopg2.extras.Json({"escalated_to": "admin_queue"}),
                "Certificate renewal is a sensitive action that requires administrator approval.",
                0.91, "executed", now - timedelta(hours=2, minutes=45),
            ),
        )

        # --- Ticket 2: CLOSED ---
        closed_ticket_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO tickets (
                id, user_id, subject, description, category, priority, status,
                resolution, resolution_source, resolution_confirmed, resolved_at, closed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                closed_ticket_id, john_id, "Cannot connect to campus Wi-Fi",
                "My laptop won't connect to the eduroam network in the library.",
                "WIFI", "MEDIUM", "CLOSED",
                "Reset the saved network profile and reconnected with updated credentials.",
                "ADMIN", True, now - timedelta(days=10), now - timedelta(days=9),
            ),
        )
        cur.execute(
            """
            INSERT INTO ticket_events (id, ticket_id, event_type, actor_type, old_value, new_value, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), closed_ticket_id, "STATUS_CHANGED", "ADMIN", "RESOLVED", "CLOSED",
                now - timedelta(days=9),
            ),
        )

        # --- Ticket 3: related to Ticket 1 (recurring VPN issue) ---
        related_ticket_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO tickets (
                id, user_id, subject, description, category, priority, status, parent_ticket_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                related_ticket_id, john_id, "VPN certificate expired again",
                "Getting the same VPN error as last month.",
                "VPN", "MEDIUM", "NEW", open_ticket_id,
            ),
        )

        conn.commit()
        print(
            f"Seeded user john@university.edu and 2 admins (alice={alice_id}, bob={bob_id}) "
            f"with 3 tickets (open={open_ticket_id}, closed={closed_ticket_id}, "
            f"related={related_ticket_id})."
        )
    finally:
        if owns_connection:
            conn.close()


if __name__ == "__main__":
    seed()
