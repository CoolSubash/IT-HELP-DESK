"""
Exercises POST /email/inbound over real HTTP -- the wire format (aliased
from/to fields, defaults), the phase6.md Part 13 response shape, the
dev-mode webhook security bypass, and the "handle gracefully" /
"safe validation error" cases from Part 15, on top of what
tests/test_email_service.py already covers at the service level.
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload(from_email: str = "api-test-student@university.edu", **overrides) -> dict:
    """`from_email` is a real parameter (not folded into **overrides) since
    the wire format's key is the Python keyword `from` -- this maps the
    friendly name callers use to that JSON key."""
    payload = {
        "from": from_email,
        "to": "it-support@university.edu",
        "subject": "Cannot connect to WiFi",
        "body": "My laptop won't connect to the campus wifi.",
        "message_id": f"<{uuid.uuid4()}@gmail.com>",
    }
    payload.update(overrides)
    return payload


def test_inbound_email_creates_a_ticket_end_to_end():
    response = client.post("/email/inbound", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["action"] == "created_new_ticket"
    assert body["ticket_number"].startswith("T-")
    assert body["user_id"]

    ticket = client.get(f"/tickets/{body['ticket_id']}").json()
    assert ticket["subject"] == "Cannot connect to WiFi"
    assert ticket["category"] == "OTHER"
    assert f"T-{ticket['ticket_number']}" == body["ticket_number"]


def test_inbound_email_reply_attaches_to_the_same_ticket():
    first_body = _payload(from_email="api-thread-test@university.edu")
    first_response = client.post("/email/inbound", json=first_body)
    ticket_id = first_response.json()["ticket_id"]

    reply = client.post(
        "/email/inbound",
        json=_payload(from_email="api-thread-test@university.edu", in_reply_to=first_body["message_id"]),
    )
    assert reply.json()["status"] == "processed"
    assert reply.json()["action"] == "attached_to_existing_ticket"
    assert reply.json()["ticket_id"] == ticket_id


def test_duplicate_webhook_delivery_is_idempotent():
    payload = _payload(from_email="api-dup-test@university.edu")
    first = client.post("/email/inbound", json=payload)
    second = client.post("/email/inbound", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "already_processed"
    assert second.json()["action"] == "duplicate"
    assert second.json()["message_id"] == first.json()["message_id"]

    messages = client.get(f"/tickets/{first.json()['ticket_id']}/messages").json()
    assert messages["total"] == 1


def test_inbound_webhook_is_open_in_dev_mode_with_no_secret_header():
    # app/config.py defaults email_webhook_dev_mode=True, matching this
    # project's .env.example -- no X-Webhook-Secret header is sent here,
    # and it still succeeds.
    response = client.post("/email/inbound", json=_payload())
    assert response.status_code == 200


def test_missing_message_id_is_handled_gracefully():
    payload = _payload()
    del payload["message_id"]
    response = client.post("/email/inbound", json=payload)
    # A clean 422 (FastAPI/Pydantic's own required-field validation), not
    # a 500 -- phase6.md Part 15: "Missing Message-ID: Handle gracefully."
    assert response.status_code == 422


def test_malformed_payload_returns_a_safe_validation_error():
    # Missing every required field -- phase6.md Part 15: "Malformed email
    # data: Return a safe validation error."
    response = client.post("/email/inbound", json={"not": "a valid inbound email payload"})
    assert response.status_code == 422
    assert "detail" in response.json()
