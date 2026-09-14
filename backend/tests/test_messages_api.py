"""
Exercises message creation: direction auto-derivation from sender_type, the
STUDENT-requires-sender_id validation, sender_id must refer to a real user,
and (Phase 4) the send_email option on ADMIN messages.

POST /tickets/{id}/messages returns {"message": ..., "email_sent": ...,
"email_error": ...} (see app/schemas/message.py:SendMessageResult) rather
than the message directly, since a message can be created successfully
even when an attempted email send fails -- every test below reads the
created message from response.json()["message"].
"""
import uuid

from fastapi.testclient import TestClient

from app.email.provider import EmailSendError
from app.main import app
from app.services import message_service, user_service

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


def test_student_message_requires_sender_id_and_is_inbound():
    user = _create_user("phase2-message-student@university.edu")
    ticket = _create_ticket(user["id"])

    missing_sender_id = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "STUDENT", "body": "Still broken"},
    )
    assert missing_sender_id.status_code == 422

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "STUDENT", "sender_id": user["id"], "body": "Still broken"},
    )
    assert response.status_code == 201
    assert response.json()["message"]["direction"] == "INBOUND"
    assert response.json()["email_sent"] is False


def test_student_message_rejects_unknown_sender_id():
    user = _create_user("phase2-message-unknown-sender@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "STUDENT", "sender_id": str(uuid.uuid4()), "body": "Hi"},
    )
    assert response.status_code == 404


def test_ai_message_rejects_a_sender_id_and_is_outbound():
    user = _create_user("phase2-message-ai@university.edu")
    ticket = _create_ticket(user["id"])

    rejected = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "AI", "sender_id": user["id"], "body": "Investigating."},
    )
    assert rejected.status_code == 422

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "AI", "body": "Investigating."},
    )
    assert response.status_code == 201
    assert response.json()["message"]["direction"] == "OUTBOUND"
    assert response.json()["message"]["sender_id"] is None


def test_list_messages_is_paginated_and_ticket_must_exist():
    user = _create_user("phase2-message-list@university.edu")
    ticket = _create_ticket(user["id"])
    client.post(f"/tickets/{ticket['id']}/messages", json={"sender_type": "AI", "body": "one"})
    client.post(f"/tickets/{ticket['id']}/messages", json={"sender_type": "AI", "body": "two"})

    page = client.get(f"/tickets/{ticket['id']}/messages", params={"limit": 1}).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1

    missing_ticket = client.get(f"/tickets/{uuid.uuid4()}/messages")
    assert missing_ticket.status_code == 404


# --- Phase 4: send_email ---------------------------------------------------


def test_send_email_is_rejected_for_non_admin_senders():
    user = _create_user("phase4-send-email-student@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "STUDENT", "sender_id": user["id"], "body": "hi", "send_email": True},
    )
    assert response.status_code == 400


def test_admin_message_with_send_email_stores_email_metadata():
    user = _create_user("phase4-send-email-admin@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "ADMIN", "body": "Please restart your laptop.", "send_email": True},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email_sent"] is True
    assert body["email_error"] is None
    assert body["message"]["email_message_id"] is not None
    assert body["message"]["email_thread_id"] is not None


def test_admin_message_without_send_email_does_not_touch_email_fields():
    user = _create_user("phase4-no-send-email-admin@university.edu")
    ticket = _create_ticket(user["id"])

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "ADMIN", "body": "Internal note only."},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email_sent"] is False
    assert body["email_error"] is None
    assert body["message"]["email_message_id"] is None


def test_admin_message_logs_an_admin_replied_event():
    """phase4.md #17 explicitly calls out ADMIN_REPLIED as a required
    ticket_events entry -- this was missing initially (message creation
    logged nothing), caught when the History timeline on a real ticket
    showed no admin activity at all."""
    user = _create_user("phase4-admin-replied-event@university.edu")
    ticket = _create_ticket(user["id"])

    client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "ADMIN", "body": "Internal note only."},
    )

    events = client.get(f"/tickets/{ticket['id']}/events").json()["items"]
    admin_replied = next(e for e in events if e["event_type"] == "ADMIN_REPLIED")
    assert admin_replied["actor_type"] == "ADMIN"


def test_admin_reply_threads_against_the_students_last_email(db):
    user, _ = user_service.find_or_create_user(db, "phase4-threading-test@university.edu")
    db.commit()  # _create_ticket below runs on a *different* connection
    # (from the app's pool), which can't see this row until it's committed.
    ticket = _create_ticket(str(user["id"]))  # user["id"] is a uuid.UUID
    # object here (unlike _create_user()'s, which round-tripped through
    # JSON) -- json.dumps can't serialize that directly.

    message_service.create_message_from_email(
        db,
        ticket_id=uuid.UUID(ticket["id"]),
        user_id=user["id"],
        body="My VPN is broken",
        email_message_id="<student-1@gmail.com>",
        in_reply_to=None,
        email_thread_id="<student-1@gmail.com>",
    )
    db.commit()

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "ADMIN", "body": "Try this fix.", "send_email": True},
    )
    body = response.json()["message"]
    assert body["in_reply_to"] == "<student-1@gmail.com>"
    assert body["email_thread_id"] == "<student-1@gmail.com>"


def test_email_send_failure_is_recorded_but_message_is_kept(monkeypatch):
    user = _create_user("phase4-send-email-failure@university.edu")
    ticket = _create_ticket(user["id"])

    class FailingProvider:
        def send_email(self, **kwargs):
            raise EmailSendError("SES is unavailable")

    from app.email import service as email_service

    monkeypatch.setattr(email_service, "get_email_provider", lambda: FailingProvider())

    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"sender_type": "ADMIN", "body": "This will fail to send.", "send_email": True},
    )
    assert response.status_code == 201  # the message itself was still created
    body = response.json()
    assert body["email_sent"] is False
    assert body["email_error"] == "SES is unavailable"
    assert body["message"]["email_message_id"] is None

    events = client.get(f"/tickets/{ticket['id']}/events").json()["items"]
    assert any(e["event_type"] == "EMAIL_SEND_FAILED" for e in events)
