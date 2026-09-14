"""
Text extraction + cleaning (phase7.md #8): PDF/DOCX/Markdown -> plain text,
the first step of the ingestion pipeline before chunking can happen at all.

Kept as one small module with one function per format rather than a
pluggable-provider abstraction (unlike app/rag/embeddings/) -- phase7.md
#6 specifically asks for provider abstraction on the embedding call
because *that* is the piece likely to change (AWS Bedrock vs. something
else later). Text extraction isn't: PDF is PDF, and there's no reasonable
world where this project swaps pypdf for a different PDF library at
runtime based on a setting. python-docx is imported lazily inside
extract_text() so a deployment that never uploads a DOCX file doesn't pay
for importing it, keeping phase7.md #8's "don't let DOCX complicate the
core design" literally true.
"""
import io

from app.errors import ValidationError

SUPPORTED_FILE_TYPES = {"pdf", "txt", "md", "docx"}


class ExtractionError(Exception):
    """Raised when a file of a supported type can't actually be read --
    corrupted PDF, non-UTF-8 text file, etc. Caught by
    app/rag/ingestion_service.py and turned into a FAILED document status,
    not an HTTP error, because by the time extraction runs the document
    row already exists (see that module's docstring)."""


def extract_text(file_bytes: bytes, file_type: str) -> str:
    file_type = file_type.lower().lstrip(".")
    if file_type not in SUPPORTED_FILE_TYPES:
        raise ValidationError(
            f"unsupported file type {file_type!r}; supported types are {sorted(SUPPORTED_FILE_TYPES)}"
        )
    if not file_bytes:
        raise ValidationError("uploaded file is empty")

    try:
        if file_type in ("txt", "md"):
            return _extract_plain_text(file_bytes)
        if file_type == "pdf":
            return _extract_pdf(file_bytes)
        return _extract_docx(file_bytes)  # file_type == "docx"
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any
        # third-party parser failure (corrupt file, unsupported PDF
        # feature, etc.) becomes one uniform ExtractionError so
        # ingestion_service has a single exception type to catch,
        # regardless of which library raised it or why.
        raise ExtractionError(f"failed to extract text from {file_type} file: {exc}") from exc


def _extract_plain_text(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _extract_docx(file_bytes: bytes) -> str:
    import docx  # python-docx; imported lazily, see module docstring

    document = docx.Document(io.BytesIO(file_bytes))
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())


def clean_text(text: str) -> str:
    """Normalizes whitespace before chunking: collapses runs of 3+ blank
    lines to a single blank line (keeps chunking.py's block-splitting
    predictable), converts Windows line endings, and strips trailing
    whitespace per line. Deliberately does NOT strip formatting like
    Markdown headings or bullet markers -- chunking.py's boundary
    detection depends on those still being there."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned_lines: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()
