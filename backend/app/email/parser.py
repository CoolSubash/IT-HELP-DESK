"""
Small text-processing helpers for email content -- kept separate from
service.py's orchestration logic so they're independently testable and so
service.py doesn't accumulate string/regex handling mixed in with database
calls.
"""
import re

# Matches the "T-104" format app/email/threading.py:build_reply_subject
# generates -- e.g. "Re: VPN issue [Ticket T-104]" -> "104". An exact
# integer, not a UUID-prefix guess (Phase 4's original approach): looking
# a ticket up by ticket_number is a precise, collision-free match, unlike
# an 8-hex-character UUID prefix.
_TICKET_NUMBER_PATTERN = re.compile(r"\[Ticket T-(\d+)\]")


def normalize_email_address(address: str) -> str:
    return address.strip().lower()


def extract_ticket_number(subject: str) -> int | None:
    """Returns None if the subject has no such tag -- this is only ever a
    fallback matching strategy (see app/email/service.py's
    _find_matching_ticket), never the primary one; headers are checked
    first (phase6.md Part 3: "Do NOT rely only on subject text to
    identify threads. Email headers are more reliable.")."""
    match = _TICKET_NUMBER_PATTERN.search(subject)
    return int(match.group(1)) if match else None
