"""
Covers phase5.md Part 13, items 9-13: S3 event parsing, the FastAPI
request/error paths, and duplicate-invocation behavior. S3 is mocked with
moto (no real AWS account needed); the FastAPI call is monkeypatched at
the fastapi_client module boundary rather than mocking urllib directly,
since what matters here is "does the handler call it correctly and handle
its exceptions," not urllib's own behavior.
"""
import os
from email.mime.text import MIMEText

import boto3
import pytest
from fastapi_client import FastAPIRequestError
from moto import mock_aws

import handler as handler_module

BUCKET = "test-inbound-email-bucket"
KEY = "emails/2026/01/01/test-object.eml"


def _s3_event(bucket: str = BUCKET, key: str = KEY) -> dict:
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


def _put_test_email(s3_client, bucket: str, key: str, message_id: str = "<handler-test@gmail.com>") -> None:
    msg = MIMEText("My VPN stopped working.")
    msg["From"] = "jane@university.edu"
    msg["To"] = "it-support@university.edu"
    msg["Subject"] = "VPN broken"
    msg["Message-ID"] = message_id
    s3_client.put_object(Bucket=bucket, Key=key, Body=msg.as_bytes())


@pytest.fixture(autouse=True)
def _lambda_env(monkeypatch):
    monkeypatch.setenv("FASTAPI_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("INBOUND_EMAIL_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:test")
    monkeypatch.setattr(handler_module, "_get_inbound_email_secret", lambda: "test-secret")
    handler_module._cached_secret = None


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        # Rebind the module's S3 client to one that's inside moto's mock
        # context -- the module-level client created at import time was
        # constructed before this fixture's mock_aws() context existed.
        handler_module._s3_client = boto3.client("s3", region_name="us-east-1")
        yield client


def test_s3_event_extracts_bucket_and_key_including_url_decoding(s3_bucket, monkeypatch):
    key_with_space = "emails/2026/01/01/subject with space.eml"
    _put_test_email(s3_bucket, BUCKET, key_with_space)

    captured = {}

    def _fake_post(base_url, secret, email, timeout_seconds=10):
        captured["base_url"] = base_url
        captured["secret"] = secret
        return {"status_code": 200, "body": {"status": "created"}}

    monkeypatch.setattr(handler_module, "post_inbound_email", _fake_post)

    # S3 event keys are URL-encoded; a space becomes "+".
    event = _s3_event(key=key_with_space.replace(" ", "+"))
    result = handler_module.lambda_handler(event, context=None)

    assert result["processed"][0]["fastapi_status"] == "created"
    assert captured["base_url"] == "https://api.example.test"
    assert captured["secret"] == "test-secret"


def test_fastapi_request_is_generated_with_the_normalized_email(s3_bucket, monkeypatch):
    _put_test_email(s3_bucket, BUCKET, KEY, message_id="<generation-test@gmail.com>")

    captured = {}

    def _fake_post(base_url, secret, email, timeout_seconds=10):
        captured["email"] = email
        return {"status_code": 200, "body": {"status": "created"}}

    monkeypatch.setattr(handler_module, "post_inbound_email", _fake_post)
    handler_module.lambda_handler(_s3_event(), context=None)

    assert captured["email"].from_email == "jane@university.edu"
    assert captured["email"].message_id == "<generation-test@gmail.com>"


def test_fastapi_authentication_failure_propagates(s3_bucket, monkeypatch):
    _put_test_email(s3_bucket, BUCKET, KEY)

    def _fake_post(base_url, secret, email, timeout_seconds=10):
        raise FastAPIRequestError("FastAPI returned 401: invalid secret", status_code=401)

    monkeypatch.setattr(handler_module, "post_inbound_email", _fake_post)

    with pytest.raises(FastAPIRequestError):
        handler_module.lambda_handler(_s3_event(), context=None)


def test_fastapi_unavailable_propagates(s3_bucket, monkeypatch):
    _put_test_email(s3_bucket, BUCKET, KEY)

    def _fake_post(base_url, secret, email, timeout_seconds=10):
        raise FastAPIRequestError("could not reach FastAPI: Connection refused")

    monkeypatch.setattr(handler_module, "post_inbound_email", _fake_post)

    with pytest.raises(FastAPIRequestError):
        handler_module.lambda_handler(_s3_event(), context=None)


def test_s3_download_failure_propagates(s3_bucket):
    # No object was put at this key -- get_object raises, and the handler
    # must let that propagate (phase5.md #12) rather than swallowing it.
    with pytest.raises(Exception):
        handler_module.lambda_handler(_s3_event(key="emails/does-not-exist.eml"), context=None)


def test_duplicate_invocation_sends_the_same_message_id_twice_without_lambda_side_dedup(
    s3_bucket, monkeypatch
):
    """phase5.md #12: "The Lambda should not attempt to solve ticket
    idempotency itself. FastAPI/PostgreSQL will enforce uniqueness." This
    confirms the Lambda has no such logic -- invoking it twice for the same
    object calls FastAPI twice with an identical message_id, leaving
    dedup entirely to the email_message_id UNIQUE constraint on the
    FastAPI/Postgres side (see backend/migrations/0004)."""
    _put_test_email(s3_bucket, BUCKET, KEY, message_id="<dup-test@gmail.com>")

    seen_message_ids = []

    def _fake_post(base_url, secret, email, timeout_seconds=10):
        seen_message_ids.append(email.message_id)
        return {"status_code": 200, "body": {"status": "duplicate" if len(seen_message_ids) > 1 else "created"}}

    monkeypatch.setattr(handler_module, "post_inbound_email", _fake_post)

    handler_module.lambda_handler(_s3_event(), context=None)
    handler_module.lambda_handler(_s3_event(), context=None)

    assert seen_message_ids == ["<dup-test@gmail.com>", "<dup-test@gmail.com>"]
