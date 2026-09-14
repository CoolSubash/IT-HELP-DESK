"""
Covers phase5.md Part 13, items 1-8: the parsing scenarios. Test emails are
built with Python's email.mime constructs rather than hand-written .eml
fixture files -- less fragile (no manually-maintained MIME boundaries) and
just as faithful, since email_parser.py consumes real email.message.Message
objects either way once message_from_bytes runs.
"""
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest
from email_parser import EmailParsingError, parse_eml_bytes


def _plain_email(**headers) -> bytes:
    msg = MIMEText("My VPN stopped working after the update.", "plain")
    msg["From"] = headers.pop("From", "Jane Doe <jane@university.edu>")
    msg["To"] = headers.pop("To", "it-support@university.edu")
    msg["Subject"] = headers.pop("Subject", "VPN broken")
    for key, value in headers.items():
        msg[key] = value
    return msg.as_bytes()


def test_plain_text_email_parses_all_fields():
    raw = _plain_email(**{"Message-ID": "<msg-1@gmail.com>"})
    email = parse_eml_bytes(raw, fallback_id_seed="unused")

    assert email.from_email == "jane@university.edu"
    assert email.to_email == "it-support@university.edu"
    assert email.subject == "VPN broken"
    assert "My VPN stopped working" in email.body
    assert email.message_id == "<msg-1@gmail.com>"


def test_html_email_is_converted_to_plain_text():
    msg = MIMEText("<p>My <b>VPN</b> is broken.</p><p>Please help.</p>", "html")
    msg["From"] = "jane@university.edu"
    msg["To"] = "it-support@university.edu"
    msg["Subject"] = "VPN broken"
    msg["Message-ID"] = "<msg-html@gmail.com>"

    email = parse_eml_bytes(msg.as_bytes(), fallback_id_seed="unused")

    assert "<p>" not in email.body
    assert "<b>" not in email.body
    assert "VPN" in email.body
    assert "Please help" in email.body


def test_multipart_email_prefers_the_plain_text_part():
    msg = MIMEMultipart("alternative")
    msg["From"] = "jane@university.edu"
    msg["To"] = "it-support@university.edu"
    msg["Subject"] = "VPN broken"
    msg["Message-ID"] = "<msg-multipart@gmail.com>"
    msg.attach(MIMEText("Plain text version of the message.", "plain"))
    msg.attach(MIMEText("<p>HTML version of the message.</p>", "html"))

    email = parse_eml_bytes(msg.as_bytes(), fallback_id_seed="unused")

    assert email.body == "Plain text version of the message."


def test_missing_in_reply_to_is_none():
    raw = _plain_email(**{"Message-ID": "<msg-no-reply@gmail.com>"})
    email = parse_eml_bytes(raw, fallback_id_seed="unused")
    assert email.in_reply_to is None


def test_missing_references_is_an_empty_list():
    raw = _plain_email(**{"Message-ID": "<msg-no-refs@gmail.com>"})
    email = parse_eml_bytes(raw, fallback_id_seed="unused")
    assert email.references == []


def test_multiple_references_are_all_extracted():
    raw = _plain_email(
        **{
            "Message-ID": "<msg-3@gmail.com>",
            "References": "<msg-1@gmail.com> <msg-2@gmail.com>",
        }
    )
    email = parse_eml_bytes(raw, fallback_id_seed="unused")
    assert email.references == ["<msg-1@gmail.com>", "<msg-2@gmail.com>"]


def test_missing_message_id_gets_a_deterministic_fallback():
    raw = _plain_email()  # no Message-ID header at all

    first = parse_eml_bytes(raw, fallback_id_seed="bucket/emails/2026/01/01/abc.eml")
    second = parse_eml_bytes(raw, fallback_id_seed="bucket/emails/2026/01/01/abc.eml")
    different_seed = parse_eml_bytes(raw, fallback_id_seed="bucket/emails/2026/01/01/xyz.eml")

    assert first.message_id  # something was generated
    assert first.message_id == second.message_id  # same seed -> same id (idempotent retries)
    assert first.message_id != different_seed.message_id


def test_malformed_email_raises_email_parsing_error(monkeypatch):
    import email_parser

    def _broken(_bytes):
        raise ValueError("simulated corrupt byte stream")

    monkeypatch.setattr(email_parser, "message_from_bytes", _broken)

    with pytest.raises(EmailParsingError):
        parse_eml_bytes(b"not a real email", fallback_id_seed="unused")


def test_attachments_are_skipped_without_crashing():
    msg = MIMEMultipart()
    msg["From"] = "jane@university.edu"
    msg["To"] = "it-support@university.edu"
    msg["Subject"] = "VPN broken, log attached"
    msg["Message-ID"] = "<msg-attachment@gmail.com>"
    msg.attach(MIMEText("See attached log file.", "plain"))

    from email.mime.application import MIMEApplication

    attachment = MIMEApplication(b"\x00\x01\x02binary-log-data", _subtype="octet-stream")
    attachment.add_header("Content-Disposition", "attachment", filename="log.bin")
    msg.attach(attachment)

    email = parse_eml_bytes(msg.as_bytes(), fallback_id_seed="unused")
    assert email.body == "See attached log file."
