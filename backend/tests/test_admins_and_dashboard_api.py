"""
Exercises the two Phase 3 additions that exist purely to feed the
dashboard: the read-only admin directory, and the summary stats endpoint.
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
        "subject": "Something broke",
        "description": "Details",
        "category": "OTHER",
    }
    payload.update(overrides)
    return client.post("/tickets", json=payload).json()


def test_list_admins_returns_seeded_style_rows(db):
    admin_id = uuid.uuid4()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO admins (id, name, email) VALUES (%s, %s, %s)",
        (admin_id, "Dana Admin", "dana-admin-list-test@it.university.edu"),
    )
    db.commit()

    response = client.get("/admins")
    assert response.status_code == 200
    assert any(a["id"] == str(admin_id) for a in response.json())


def test_dashboard_stats_reflects_ticket_counts():
    user = _create_user("phase3-dashboard-stats@university.edu")
    ticket = _create_ticket(user["id"], priority="URGENT")

    before = client.get("/dashboard/stats").json()
    assert before["high_priority"] >= 1
    assert before["open"] >= 1

    client.patch(f"/tickets/{ticket['id']}/status", json={"status": "AI_INVESTIGATING"})
    client.patch(f"/tickets/{ticket['id']}/status", json={"status": "WAITING_FOR_USER"})

    after = client.get("/dashboard/stats").json()
    assert after["assigned_to_me"] is None  # no admin_id was passed


def test_dashboard_stats_assigned_to_me_requires_admin_id(db):
    admin_id = uuid.uuid4()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO admins (id, name, email) VALUES (%s, %s, %s)",
        (admin_id, "Assigned To Me Admin", "assigned-to-me-test@it.university.edu"),
    )
    db.commit()

    user = _create_user("phase3-assigned-to-me@university.edu")
    ticket = _create_ticket(user["id"])
    client.patch(
        f"/tickets/{ticket['id']}/assign", json={"assigned_admin_id": str(admin_id)}
    )

    stats = client.get("/dashboard/stats", params={"admin_id": str(admin_id)}).json()
    assert stats["assigned_to_me"] == 1
