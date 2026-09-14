"""
Exercises the read-only events and agent-actions endpoints. Agent actions
have no create endpoint in Phase 2 (nothing writes them until the AI agent
exists), so the agent-actions test inserts its own rows directly with SQL
-- standing in for what a future AI agent service will eventually do --
rather than depending on seed/seed_data.py, which isn't safe to call more
than once per test session (it always inserts the same fixed email).
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_user(email: str) -> dict:
    return client.post("/users", json={"email": email}).json()


def _create_ticket(user_id: str) -> dict:
    return client.post(
        "/tickets",
        json={
            "user_id": user_id,
            "subject": "VPN broken",
            "description": "Cannot connect",
            "category": "VPN",
        },
    ).json()


def test_events_endpoint_requires_an_existing_ticket():
    response = client.get(f"/tickets/{uuid.uuid4()}/events")
    assert response.status_code == 404


def test_agent_actions_endpoint_requires_an_existing_ticket():
    response = client.get(f"/tickets/{uuid.uuid4()}/agent-actions")
    assert response.status_code == 404


def test_fresh_ticket_has_a_ticket_created_event_and_no_agent_actions():
    user = _create_user("phase2-fresh-events@university.edu")
    ticket = _create_ticket(user["id"])

    events = client.get(f"/tickets/{ticket['id']}/events").json()["items"]
    assert any(e["event_type"] == "TICKET_CREATED" for e in events)

    actions = client.get(f"/tickets/{ticket['id']}/agent-actions").json()["items"]
    assert actions == []


def test_agent_actions_list_reflects_directly_inserted_rows(db):
    user = _create_user("phase2-agent-actions@university.edu")
    ticket = _create_ticket(user["id"])

    cur = db.cursor()
    cur.executemany(
        """
        INSERT INTO agent_actions (id, ticket_id, action_type, tool_name, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [
            (uuid.uuid4(), ticket["id"], "KNOWLEDGE_SEARCH", "search_knowledge_base", "executed"),
            (uuid.uuid4(), ticket["id"], "ESCALATION", "assign_ticket", "executed"),
        ],
    )
    db.commit()

    response = client.get(f"/tickets/{ticket['id']}/agent-actions")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {a["action_type"] for a in body["items"]} == {"KNOWLEDGE_SEARCH", "ESCALATION"}
