"""
Turns raw .eml bytes into a NormalizedEmail. Uses only Python's standard
library `email` package -- no third-party dependency, so the Lambda
deployment package needs no bundling step beyond the plain .py files (see
the CDK stack's lambda.Code.from_asset).

Deliberately contains zero ticket-matching or business logic (phase5.md
Part 3: "Do not put ticket matching logic inside Lambda") -- this module's
only job is "raw bytes in, normalized fields out."
"""
import hashlib
import re
from email import message_from_bytes
from email.message import Message
from email.utils import getaddresses
from html.parser import HTMLParser

from models import NormalizedEmail


class EmailParsingError(Exception):
    """Raised when an .eml can't be turned into a usable NormalizedEmail at
    all (e.g. no body of any kind could be extracted). Caught by
    handler.py, which logs it and re-raises so the Lambda invocation fails
    -- per phase5.md Part 12, a parsing failure should never silently
    produce a corrupt ticket."""


class _TagStripper(HTMLParser):
    """Minimal HTML-to-text fallback for when an email has no text/plain
    part -- just enough to get readable text out of a text/html body
    without pulling in a third-party HTML library. Not a general-purpose
    HTML renderer; good enough for "what did the student type," which is
    all this needs to preserve."""

    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._chunks)).strip()


def _html_to_text(html: str) -> str:
    stripper = _TagStripper()
    stripper.feed(html)
    return stripper.text()


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        # An unknown/unsupported charset name -- fall back rather than
        # raising, since this is exactly the kind of malformed-but-real
        # email phase5.md #12 says must not crash the Lambda.
        return payload.decode("utf-8", errors="replace")


def _extract_body(message: Message) -> str:
    """Prefers a text/plain part; falls back to text/html (converted);
    skips attachments entirely (phase5.md Part 2: "handle attachments
    without crashing" -- the raw .eml already preserves them in S3, so
    this function's only job is finding the human-readable body, not
    processing every part)."""
    if not message.is_multipart():
        content_type = message.get_content_type()
        text = _decode_part(message)
        return _html_to_text(text) if content_type == "text/html" else text

    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(_decode_part(part))
        elif content_type == "text/html":
            html_parts.append(_decode_part(part))

    if plain_parts:
        return "\n".join(plain_parts).strip()
    if html_parts:
        return _html_to_text("\n".join(html_parts))
    return ""


def _first_address(header_value: str | None) -> str:
    if not header_value:
        return ""
    addresses = getaddresses([header_value])
    return addresses[0][1] if addresses else header_value.strip()


def _parse_references(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    # References is a whitespace-separated list of <message-id> tokens.
    return re.findall(r"<[^<>]+>", header_value)


def parse_eml_bytes(raw_bytes: bytes, fallback_id_seed: str) -> NormalizedEmail:
    """`fallback_id_seed` (the S3 object key, in practice -- see
    handler.py) is used only when the email itself has no Message-ID
    header. It's derived deterministically (a hash of the seed, not a
    random uuid) so that if the same S3 event is retried, the same
    fallback id comes out both times -- keeping FastAPI's
    email_message_id-based duplicate protection meaningful even for an
    email that arrived with a missing header, per phase5.md #12's
    "duplicate Lambda invocation" guidance."""
    try:
        message = message_from_bytes(raw_bytes)
    except Exception as exc:  # email.message_from_bytes rarely raises, but
        # a sufficiently malformed byte stream can still break it --
        # wrapping unconditionally is what makes "malformed email" a
        # well-defined, always-caught failure mode rather than an
        # unhandled crash.
        raise EmailParsingError(f"could not parse email: {exc}") from exc

    from_email = _first_address(message.get("From"))
    to_email = _first_address(message.get("To"))
    subject = str(message.get("Subject", "")).strip()
    message_id = message.get("Message-ID")
    if not message_id:
        digest = hashlib.sha256(fallback_id_seed.encode("utf-8")).hexdigest()[:16]
        message_id = f"<generated-{digest}@lambda-ingestion>"

    try:
        body = _extract_body(message)
    except Exception as exc:
        raise EmailParsingError(f"could not extract a body: {exc}") from exc

    return NormalizedEmail(
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        body=body,
        message_id=message_id.strip(),
        in_reply_to=(message.get("In-Reply-To") or "").strip() or None,
        references=_parse_references(message.get("References")),
        thread_id=None,  # SES doesn't provide a provider-level thread id;
        # left None so app/email/service.py's matching falls through to
        # References/subject-tag strategies, per phase4.md #12.
    )
