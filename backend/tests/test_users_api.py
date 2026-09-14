"""
Exercises the user endpoints added in Phase 2: find-or-create idempotency,
get, ticket history, and devices. Uses FastAPI's TestClient, which runs
requests through the real app -- routers, services, and the real Postgres
underneath -- the same as test_health.py in Phase 1.
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_find_or_create_user_is_idempotent():
    payload = {"email": "phase2-find-or-create@university.edu", "name": "Phase Two"}

    first = client.post("/users", json=payload)
    assert first.status_code == 201
    user_id = first.json()["id"]

    second = client.post("/users", json=payload)
    assert second.status_code == 200
    assert second.json()["id"] == user_id


def test_get_user_returns_404_for_unknown_id():
    response = client.get(f"/users/{uuid.uuid4()}")
    assert response.status_code == 404


def test_user_ticket_history_and_devices():
    user = client.post("/users", json={"email": "phase2-history@university.edu"}).json()

    ticket = client.post(
        "/tickets",
        json={
            "user_id": user["id"],
            "subject": "Laptop won't boot",
            "description": "Blue screen on startup",
            "category": "HARDWARE",
        },
    ).json()

    history = client.get(f"/users/{user['id']}/tickets")
    assert history.status_code == 200
    body = history.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == ticket["id"]

    devices = client.get(f"/users/{user['id']}/devices")
    assert devices.status_code == 200
    assert devices.json() == []


def test_list_users_includes_ticket_count():
    user = client.post("/users", json={"email": "phase3-ticket-count@university.edu"}).json()
    client.post(
        "/tickets",
        json={
            "user_id": user["id"],
            "subject": "First issue",
            "description": "d",
            "category": "OTHER",
        },
    )
    client.post(
        "/tickets",
        json={
            "user_id": user["id"],
            "subject": "Second issue",
            "description": "d",
            "category": "OTHER",
        },
    )

    users = client.get("/users").json()
    this_user = next(u for u in users if u["id"] == user["id"])
    assert this_user["ticket_count"] == 2
