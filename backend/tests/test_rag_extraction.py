"""
Extraction tests (phase7.md #20: "Document ingestion: PDF, TXT,
Markdown"). PDF/DOCX byte-generation for a *valid* file needs their
respective write-side libraries (pypdf's PdfWriter, python-docx), which
this project only added as read-side (extraction) dependencies -- so PDF
and DOCX are exercised end-to-end at the ingestion level instead
(test_rag_ingestion.py, using real files under seed/knowledge_docs/ plus
a deliberately-corrupt PDF for the failure path). This module covers
TXT/Markdown directly (no extra library needed to construct valid input)
and the shared validation/cleaning logic that every format goes through.
"""
import pytest

from app.errors import ValidationError
from app.rag.extraction import clean_text, extract_text


def test_extracts_txt():
    text = extract_text(b"Hello IT support", "txt")
    assert text == "Hello IT support"


def test_extracts_markdown():
    text = extract_text(b"# Heading\n\nSome content.", "md")
    assert "# Heading" in text
    assert "Some content." in text


def test_file_type_is_case_and_dot_insensitive():
    assert extract_text(b"hi", "TXT") == "hi"
    assert extract_text(b"hi", ".txt") == "hi"


def test_unsupported_file_type_raises_validation_error():
    with pytest.raises(ValidationError):
        extract_text(b"whatever", "exe")


def test_empty_file_raises_validation_error():
    with pytest.raises(ValidationError):
        extract_text(b"", "txt")


def test_non_utf8_bytes_are_replaced_not_raised():
    # Invalid UTF-8 shouldn't crash extraction -- decode with replacement
    # per extraction.py's _extract_plain_text -- errors surface later as
    # unusual content, not as an ExtractionError.
    text = extract_text(b"\xff\xfe not valid utf-8", "txt")
    assert isinstance(text, str)


def test_clean_text_collapses_excess_blank_lines():
    messy = "Paragraph one.\n\n\n\n\nParagraph two."
    cleaned = clean_text(messy)
    assert "\n\n\n" not in cleaned
    assert "Paragraph one." in cleaned
    assert "Paragraph two." in cleaned


def test_clean_text_normalizes_windows_line_endings():
    text = clean_text("line one\r\nline two\r\n")
    assert "\r" not in text


def test_clean_text_preserves_markdown_headings_and_bullets():
    text = clean_text("## Heading\n\n- item one\n- item two\n")
    assert "## Heading" in text
    assert "- item one" in text
