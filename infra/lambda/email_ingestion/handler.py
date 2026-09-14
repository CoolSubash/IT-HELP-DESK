"""
Lambda entry point: it-helpdesk-email-ingestion.

Flow (phase5.md Part 2): S3 ObjectCreated event -> download the .eml ->
parse it -> normalize it -> POST to FastAPI. No ticket-matching or business
logic lives here -- that's entirely FastAPI's job (app/email/service.py).

Module-level globals (the boto3 clients, the cached secret) are
initialized once per *cold start* and reused across warm invocations of
the same execution environment -- standard Lambda practice, avoids
re-fetching the secret or reconstructing a client on every single email.
"""
import json
import logging
import os
import urllib.parse

import boto3

from email_parser import EmailParsingError, parse_eml_bytes
from fastapi_client import FastAPIRequestError, post_inbound_email

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_s3_client = boto3.client("s3")
_secrets_client = boto3.client("secretsmanager")
_cached_secret: str | None = None


def _get_inbound_email_secret() -> str:
    global _cached_secret
    if _cached_secret is None:
        secret_arn = os.environ["INBOUND_EMAIL_SECRET_ARN"]
        response = _secrets_client.get_secret_value(SecretId=secret_arn)
        _cached_secret = response["SecretString"]
    return _cached_secret


def lambda_handler(event: dict, context) -> dict:
    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # S3 event keys are URL-encoded (e.g. spaces become "+") -- decoding
        # is required or GetObject calls on any key with special
        # characters silently 404.
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        results.append(_process_one_object(bucket, key))
    return {"processed": results}


def _process_one_object(bucket: str, key: str) -> dict:
    logger.info(json.dumps({"event": "processing_started", "bucket": bucket, "key": key}))

    try:
        response = _s3_client.get_object(Bucket=bucket, Key=key)
        raw_bytes = response["Body"].read()
    except Exception as exc:
        # phase5.md #12: "S3 download fails -- log the error and fail the
        # Lambda invocation so AWS retry behavior can occur." Re-raising
        # (rather than swallowing) is what makes this Lambda invocation
        # report as failed to S3/Lambda's own retry mechanism.
        logger.error(json.dumps({"event": "s3_download_failed", "bucket": bucket, "key": key, "error": str(exc)}))
        raise

    try:
        email = parse_eml_bytes(raw_bytes, fallback_id_seed=f"{bucket}/{key}")
    except EmailParsingError as exc:
        logger.error(json.dumps({"event": "parsing_failed", "bucket": bucket, "key": key, "error": str(exc)}))
        raise

    logger.info(
        json.dumps(
            {
                "event": "parsed",
                "bucket": bucket,
                "key": key,
                "message_id": email.message_id,
                "from_email": email.from_email,
                "subject": email.subject,
                # Body deliberately excluded from this log line --
                # phase5.md #11: "Do not log ... full sensitive email
                # bodies unnecessarily." The opt-in debug log right below
                # is the exception, off by default.
            }
        )
    )

    # TESTING/DEBUG ONLY -- off by default (DEBUG_LOG_EMAIL_BODY unset).
    # Logs the full raw email body to CloudWatch, which the line above
    # deliberately never does. Enable only for a specific debugging
    # session against real inbound email, never left on in a real
    # deployment -- CloudWatch Logs isn't the right place for that
    # content to live long-term, retention here is TWO_WEEKS
    # (email_stack.py's LambdaFunction has no explicit log retention set
    # yet, defaulting to "never expire" -- worth revisiting if this flag
    # is ever left on for a while). Toggle via:
    #   aws lambda update-function-configuration \
    #     --function-name it-helpdesk-email-ingestion \
    #     --environment "Variables={FASTAPI_BASE_URL=...,INBOUND_EMAIL_SECRET_ARN=...,DEBUG_LOG_EMAIL_BODY=true}"
    # (include every existing variable -- this call replaces the whole
    # set, it doesn't merge).
    if os.environ.get("DEBUG_LOG_EMAIL_BODY", "").lower() == "true":
        logger.info(
            json.dumps({"event": "debug_email_body", "message_id": email.message_id, "body": email.body})
        )

    secret = _get_inbound_email_secret()
    base_url = os.environ["FASTAPI_BASE_URL"]

    try:
        result = post_inbound_email(base_url, secret, email)
    except FastAPIRequestError as exc:
        logger.error(
            json.dumps(
                {
                    "event": "fastapi_request_failed",
                    "message_id": email.message_id,
                    "status_code": exc.status_code,
                    "error": str(exc),
                }
            )
        )
        raise

    logger.info(
        json.dumps(
            {
                "event": "fastapi_request_succeeded",
                "message_id": email.message_id,
                "status_code": result["status_code"],
                "ticket_status": result["body"].get("status"),
            }
        )
    )
    return {"message_id": email.message_id, "fastapi_status": result["body"].get("status")}
