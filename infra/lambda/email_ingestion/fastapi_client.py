"""
Posts a NormalizedEmail to FastAPI's POST /email/inbound. Uses
urllib.request (standard library) rather than `requests` -- the whole
Lambda package needs zero third-party pip dependencies this way (boto3 is
preinstalled in the Lambda runtime), so there's no dependency-bundling step
in the CDK stack, just plain .py files.
"""
import json
import urllib.error
import urllib.request

from models import NormalizedEmail


class FastAPIRequestError(Exception):
    """Raised for any non-2xx response, or if FastAPI can't be reached at
    all (DNS/connection/timeout). Both cases are treated the same way by
    handler.py: log and re-raise so the Lambda invocation is reported as
    failed and S3/Lambda's own retry behavior can kick in (phase5.md #12 --
    Lambda does not attempt its own retry/backoff logic)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def post_inbound_email(
    base_url: str, secret: str, email: NormalizedEmail, timeout_seconds: int = 10
) -> dict:
    url = f"{base_url.rstrip('/')}/email/inbound"
    body = json.dumps(email.to_json_dict()).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            # Matches app/routers/email.py's _verify_webhook_secret, which
            # reads a plain X-Webhook-Secret header today -- kept as a
            # simple shared-secret header rather than a bearer token
            # scheme, since that's what the existing FastAPI endpoint
            # already checks (see phase4.md's implementation). Sent as
            # both headers is unnecessary; using the header the backend
            # actually validates is what matters here.
            "X-Webhook-Secret": secret,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # A non-2xx response -- FastAPI is reachable but rejected the
        # request (e.g. 401 for a wrong secret, 404 for a bad ticket
        # reference, 500 for a server error).
        error_body = exc.read().decode("utf-8", errors="replace")
        raise FastAPIRequestError(
            f"FastAPI returned {exc.code}: {error_body}", status_code=exc.code
        ) from exc
    except urllib.error.URLError as exc:
        # FastAPI unreachable entirely (DNS failure, connection refused,
        # timeout) -- phase5.md #12's "FastAPI unavailable" case.
        raise FastAPIRequestError(f"could not reach FastAPI: {exc.reason}") from exc

    return {"status_code": status_code, "body": json.loads(response_body)}
