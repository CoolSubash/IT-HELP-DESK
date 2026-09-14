"""
Runs the seed script against the test database and checks the demo data
matches phase1.md's requirements: one user, an open/closed/related ticket
trio, a 4-message thread, ticket events, and agent actions.
"""
from seed.seed_data import seed


def test_seed_creates_expected_demo_data(db):
    seed(db)

    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", ("john@university.edu",))
    john_id = cur.fetchone()[0]

    cur.execute(
        "SELECT id, status, parent_ticket_id FROM tickets WHERE user_id = %s", (john_id,)
    )
    tickets = cur.fetchall()
    assert len(tickets) == 3
    assert any(status == "CLOSED" for _, status, _ in tickets)
    assert any(parent is not None for _, _, parent in tickets)

    open_ticket_id = next(
        tid for tid, status, parent in tickets if status != "CLOSED" and parent is None
    )

    cur.execute(
        "SELECT sender_type FROM messages WHERE ticket_id = %s ORDER BY created_at",
        (open_ticket_id,),
    )
    sender_types = [row[0] for row in cur.fetchall()]
    assert sender_types == ["STUDENT", "AI", "ADMIN", "STUDENT"]

    cur.execute("SELECT count(*) FROM ticket_events WHERE ticket_id = %s", (open_ticket_id,))
    assert cur.fetchone()[0] >= 2

    cur.execute("SELECT count(*) FROM agent_actions WHERE ticket_id = %s", (open_ticket_id,))
    assert cur.fetchone()[0] == 2
