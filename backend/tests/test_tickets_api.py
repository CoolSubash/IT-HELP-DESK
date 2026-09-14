"""
Exercises ticket creation, FK validation, general updates, status-transition
validation (the approved state graph in app/services/ticket_service.py),
assignment, and related tickets.
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_user(email: str) -> dict:
    return client.post("/users", json={"email": email}).json()


def _create_ticket(user_id: str, **overrides) -> dict:
    payload = {
        "user_id": user_id,
        "subject": "VPN broken",
        "description": "Cannot connect",
        "category": "VPN",
    }
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_ticket_requires_an_existing_user():
    response = client.post(
        "/tickets",
        json={
            "user_id": str(uuid.uuid4()),
            "subject": "x",
            "description": "x",
            "category": "OTHER",
        },
    )
    assert response.status_code == 404


def test_create_ticket_validates_parent_ticket_id():
    user = _create_user("phase2-bad-parent@university.edu")
    response = client.post(
        "/tickets",
        json={
            "user_id": user["id"],
            "subject": "x",
            "description": "x",
            "category": "OTHER",
            "parent_ticket_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404


def test_create_and_get_ticket():
    user = _create_user("phase2-ticket-crud@university.edu")
    ticket = _create_ticket(user["id"])
    assert ticket["status"] == "NEW"

    fetched = client.get(f"/tickets/{ticket['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == ticket["id"]


def test_update_ticket_general_fields_only_changes_what_was_sent():
    user = _create_user("phase2-ticket-update@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.patch(f"/tickets/{ticket['id']}", json={"priority": "URGENT"})
    assert response.status_code == 200
    assert response.json()["priority"] == "URGENT"
    assert response.json()["subject"] == ticket["subject"]


def test_valid_status_transition_is_applied_and_logged():
    user = _create_user("phase2-status-valid@university.edu")
    ticket = _create_ticket(user["id"])  # status = NEW

    response = client.patch(f"/tickets/{ticket['id']}/status", json={"status": "AI_INVESTIGATING"})
    assert response.status_code == 200
    assert response.json()["status"] == "AI_INVESTIGATING"

    events = client.get(f"/tickets/{ticket['id']}/events").json()["items"]
    changed_event = next(e for e in events if e["event_type"] == "STATUS_CHANGED")
    assert changed_event["new_value"] == "AI_INVESTIGATING"
    # No changed_by_admin_id was sent -- falls back to SYSTEM, per
    # app/services/ticket_service.py.
    assert changed_event["actor_type"] == "SYSTEM"


def test_status_transition_with_admin_actor_is_attributed_to_that_admin(db):
    admin_id = uuid.uuid4()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO admins (id, name, email) VALUES (%s, %s, %s)",
        (admin_id, "Status Actor Admin", "status-actor-test@it.university.edu"),
    )
    db.commit()

    user = _create_user("phase3-status-actor@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.patch(
        f"/tickets/{ticket['id']}/status",
        json={"status": "AI_INVESTIGATING", "changed_by_admin_id": str(admin_id)},
    )
    assert response.status_code == 200

    events = client.get(f"/tickets/{ticket['id']}/events").json()["items"]
    changed_event = next(e for e in events if e["event_type"] == "STATUS_CHANGED")
    assert changed_event["actor_type"] == "ADMIN"
    assert changed_event["actor_id"] == str(admin_id)


def test_invalid_status_transition_is_rejected():
    user = _create_user("phase2-status-invalid@university.edu")
    ticket = _create_ticket(user["id"])  # status = NEW, cannot jump straight to CLOSED

    response = client.patch(f"/tickets/{ticket['id']}/status", json={"status": "CLOSED"})
    assert response.status_code == 409


def test_assign_ticket_logs_an_event(db):
    user = _create_user("phase2-assign@university.edu")
    ticket = _create_ticket(user["id"])

    admin_id = uuid.uuid4()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO admins (id, name, email) VALUES (%s, %s, %s)",
        (admin_id, "Test Admin", "test-admin-assign@it.university.edu"),
    )
    db.commit()

    response = client.patch(
        f"/tickets/{ticket['id']}/assign", json={"assigned_admin_id": str(admin_id)}
    )
    assert response.status_code == 200
    assert response.json()["assigned_admin_id"] == str(admin_id)

    events = client.get(f"/tickets/{ticket['id']}/events").json()["items"]
    assigned_event = next(e for e in events if e["event_type"] == "ASSIGNED")
    assert assigned_event["actor_type"] == "ADMIN"
    assert assigned_event["actor_id"] == str(admin_id)


def test_assign_ticket_requires_an_existing_admin():
    user = _create_user("phase3-assign-unknown-admin@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.patch(
        f"/tickets/{ticket['id']}/assign", json={"assigned_admin_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


def test_related_tickets_returns_parent_and_children():
    user = _create_user("phase2-related@university.edu")
    parent = _create_ticket(user["id"], subject="First VPN issue")
    child = _create_ticket(user["id"], subject="Recurring VPN issue", parent_ticket_id=parent["id"])

    related_from_child = client.get(f"/tickets/{child['id']}/related").json()
    assert related_from_child["parent"]["id"] == parent["id"]
    assert related_from_child["children"] == []

    related_from_parent = client.get(f"/tickets/{parent['id']}/related").json()
    assert related_from_parent["parent"] is None
    assert [c["id"] for c in related_from_parent["children"]] == [child["id"]]


def test_ticket_list_filters_by_status_category_and_search():
    user = _create_user("phase3-ticket-filters@university.edu")
    _create_ticket(
        user["id"], subject="Printer jammed again", category="HARDWARE", priority="LOW"
    )
    wifi_ticket = _create_ticket(
        user["id"], subject="Wifi dropping constantly", category="WIFI", priority="HIGH"
    )
    client.patch(f"/tickets/{wifi_ticket['id']}/status", json={"status": "AI_INVESTIGATING"})

    by_category = client.get("/tickets", params={"category": "WIFI"}).json()["items"]
    assert all(t["category"] == "WIFI" for t in by_category)
    assert any(t["id"] == wifi_ticket["id"] for t in by_category)

    by_status = client.get("/tickets", params={"status": "AI_INVESTIGATING"}).json()["items"]
    assert all(t["status"] == "AI_INVESTIGATING" for t in by_status)

    by_search = client.get("/tickets", params={"search": "jammed"}).json()["items"]
    assert all("jammed" in t["subject"].lower() for t in by_search)
    assert len(by_search) >= 1


def test_ticket_history_merges_messages_and_events_chronologically():
    user = _create_user("phase2-ticket-history@university.edu")
    ticket = _create_ticket(user["id"])
    client.patch(f"/tickets/{ticket['id']}/status", json={"status": "AI_INVESTIGATING"})
    client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "AI", "body": "Looking into this."},
    )

    history = client.get(f"/tickets/{ticket['id']}/history").json()
    types = [entry["type"] for entry in history]
    assert "event" in types
    assert "message" in types
    # chronological order
    assert all(history[i]["created_at"] <= history[i + 1]["created_at"] for i in range(len(history) - 1))


def test_ticket_list_is_paginated():
    response = client.get("/tickets", params={"limit": 1, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 1
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert body["total"] >= len(body["items"])
