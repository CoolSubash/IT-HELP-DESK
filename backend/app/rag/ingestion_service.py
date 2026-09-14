"""
Knowledge ingestion pipeline (phase7.md #8):

    Admin uploads document
            |
    Document stored (app/rag/storage.py)
            |
    Extract text (app/rag/extraction.py)
            |
    Clean text  (app/rag/extraction.py)
            |
    Chunk text  (app/rag/chunking.py)
            |
    Generate embeddings (app/rag/embeddings/)
            |
    Store chunks + vectors (knowledge_chunks)

Two upload paths share every step below except "how the file's bytes get
to this process":

  ingest_document()  -- the file's bytes arrive in the HTTP request body
                         (multipart), pass through this API process, and
                         get written to storage here. Simple, works with
                         any storage backend, but the file's full transfer
                         time adds to this process's request latency and
                         its bytes sit in this process's memory.

  create_pending_upload() + complete_pending_upload()  -- the caller
                         (typically a browser) asks for a presigned S3
                         URL first, uploads the file directly to S3 with
                         its own PUT request (never touching this
                         process), then calls complete_pending_upload()
                         to run extraction onward. Requires
                         KNOWLEDGE_STORAGE_BACKEND=s3 (see
                         app/rag/storage.py's presign_upload_url()) --
                         this is the path app/routers/knowledge.py's
                         POST /admin/knowledge/presign +
                         POST /admin/knowledge/{id}/complete use, and
                         what the dashboard's upload page actually calls.

Both paths funnel into the same two private helpers
(_resolve_version()/_run_pipeline()) so "what counts as a duplicate
title," "how versioning archives the old document," and "how a mid-
pipeline failure is recorded" can never drift apart between them.

Failure handling (phase7.md #19, "do not leave a partially ingested
document in an ACTIVE state") has one subtlety worth calling out: once
the knowledge_documents row is inserted (status=PROCESSING), a failure in
extraction/chunking/embedding must NOT abort the whole request -- the
document row itself, now carrying status=FAILED and error_message, is a
normal, useful result (an admin can see it in GET /admin/knowledge and
understand why). But a psycopg2 error partway through inserting chunks
leaves the connection in Postgres's "aborted transaction" state, where
no further statement (including the UPDATE that would set status=FAILED)
can run until a ROLLBACK happens. A raw `try/except` around the whole
pipeline would therefore succeed at catching the error but then itself
fail trying to write FAILED. The fix is a SAVEPOINT taken right before
any of the risky work: on failure, ROLLBACK TO SAVEPOINT undoes only the
partial chunk inserts (never the original PROCESSING row, which was
written before the savepoint), leaving the connection usable again for
the FAILED update -- all still inside the one outer transaction
get_db() will commit when the request finishes successfully.
"""
import uuid

import psycopg2.errors
import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.enums import KnowledgeDocumentStatus
from app.errors import ConflictError, NotFoundError, ValidationError
from app.rag import chunking, extraction
from app.rag.embeddings.provider import EmbeddingError
from app.rag.embeddings.service import get_embedding_service
from app.rag.extraction import ExtractionError
from app.rag.storage import get_storage_backend
from app.rag.vector_literal import to_pgvector_literal


def ingest_document(
    conn: PGConnection,
    *,
    title: str,
    description: str | None,
    category: str | None,
    file_name: str,
    file_type: str,
    file_bytes: bytes,
    uploaded_by: uuid.UUID | None = None,
    replace_document_id: uuid.UUID | None = None,
    chunk_size_tokens: int = 600,
    overlap_tokens: int = 80,
) -> dict:
    """The multipart upload path -- file_bytes arrive already in memory
    (from the request body) and are written to storage here before the
    shared pipeline runs. Raises ValidationError (unsupported file type /
    empty file) before any row is written, and ConflictError if `title`
    collides with an existing READY document and `replace_document_id`
    wasn't given. Every other failure (extraction, embedding, DB) is
    captured INTO the returned document row as status=FAILED rather than
    raised -- see module docstring."""
    file_type = _validate_file_type(file_type)
    if not file_bytes:
        raise ValidationError("uploaded file is empty")

    previous_document, version = _resolve_version(conn, title, replace_document_id)

    document_id = uuid.uuid4()
    storage_location = get_storage_backend().save(document_id, file_name, file_bytes)

    document = _insert_document(
        conn,
        document_id=document_id,
        title=title,
        description=description,
        category=category,
        file_name=file_name,
        file_type=file_type,
        storage_location=storage_location,
        version=version,
        previous_version_id=previous_document["id"] if previous_document else None,
        uploaded_by=uploaded_by,
    )

    return _run_pipeline(
        conn, document, previous_document, file_bytes,
        chunk_size_tokens=chunk_size_tokens, overlap_tokens=overlap_tokens,
    )


def create_pending_upload(
    conn: PGConnection,
    *,
    title: str,
    description: str | None,
    category: str | None,
    file_name: str,
    file_type: str,
    uploaded_by: uuid.UUID | None = None,
    replace_document_id: uuid.UUID | None = None,
) -> tuple[dict, str]:
    """First half of the presigned-upload path. Does every check that can
    be done without the file's bytes (file type, duplicate-title/version
    resolution -- the same as ingest_document()'s, via _resolve_version())
    BEFORE asking S3 for a presigned URL, so a request that was always
    going to be rejected never gets one handed back. Creates the
    knowledge_documents row as status=PROCESSING immediately (there is no
    file yet, only a promise of where one will land) and returns it
    alongside the URL the caller should PUT the raw file bytes to.

    Emptiness can't be checked here (there are no bytes yet) -- an empty
    file uploaded to the presigned URL surfaces later, inside
    complete_pending_upload(), as an ExtractionError ("no extractable
    text content") and the document lands FAILED, the same outcome as
    every other pipeline-stage failure.

    Raises ValidationError for a bad file type, ConflictError for a
    duplicate title without replace_document_id, and lets
    storage.presign_upload_url()'s NotImplementedError propagate as-is if
    the configured storage backend doesn't support presigned uploads
    (i.e. KNOWLEDGE_STORAGE_BACKEND=local -- see app/rag/storage.py)."""
    file_type = _validate_file_type(file_type)
    previous_document, version = _resolve_version(conn, title, replace_document_id)

    document_id = uuid.uuid4()
    upload_url, storage_location = get_storage_backend().presign_upload_url(document_id, file_name)

    document = _insert_document(
        conn,
        document_id=document_id,
        title=title,
        description=description,
        category=category,
        file_name=file_name,
        file_type=file_type,
        storage_location=storage_location,
        version=version,
        previous_version_id=previous_document["id"] if previous_document else None,
        uploaded_by=uploaded_by,
    )
    return document, upload_url


def complete_pending_upload(
    conn: PGConnection,
    document_id: uuid.UUID,
    *,
    chunk_size_tokens: int = 600,
    overlap_tokens: int = 80,
) -> dict:
    """Second half of the presigned-upload path -- called once the client
    reports its direct PUT to S3 finished. Idempotent: calling this again
    on a document that isn't still PROCESSING (already completed by an
    earlier call, or raced by another request) just returns its current
    row instead of reprocessing or erroring, since re-running the
    pipeline against an already-READY document would create duplicate
    chunks.

    If the object isn't actually in storage yet (the client called this
    before its PUT finished, the PUT failed client-side, or the presigned
    URL was never used), storage.read() raises -- that's recorded as a
    FAILED document with a clear reason, the same as any other pipeline
    failure, not a 500."""
    document = get_document(conn, document_id)
    if document["status"] != KnowledgeDocumentStatus.PROCESSING.value:
        return document

    previous_document = None
    if document["previous_version_id"] is not None:
        previous_document = get_document(conn, document["previous_version_id"])

    try:
        file_bytes = get_storage_backend().read(document["storage_location"])
    except Exception as exc:  # noqa: BLE001 -- any storage/network failure here means
        # "the file isn't retrievable," regardless of which library raised it
        # (botocore's many exception classes, a local FileNotFoundError, etc.)
        return _set_status(
            conn, document_id, KnowledgeDocumentStatus.FAILED,
            error_message=f"uploaded file could not be retrieved from storage (was the upload completed?): {exc}",
        )

    return _run_pipeline(
        conn, document, previous_document, file_bytes,
        chunk_size_tokens=chunk_size_tokens, overlap_tokens=overlap_tokens,
    )


def _validate_file_type(file_type: str) -> str:
    file_type = file_type.lower().lstrip(".")
    if file_type not in extraction.SUPPORTED_FILE_TYPES:
        raise ValidationError(
            f"unsupported file type {file_type!r}; supported types are {sorted(extraction.SUPPORTED_FILE_TYPES)}"
        )
    return file_type


def _resolve_version(
    conn: PGConnection, title: str, replace_document_id: uuid.UUID | None
) -> tuple[dict | None, int]:
    """Shared by both upload paths: either replace_document_id names the
    document this upload supersedes (version = old + 1), or `title` must
    not already belong to a READY document (phase7.md #19's "Duplicate
    document" case -> ConflictError)."""
    if replace_document_id is not None:
        previous_document = get_document(conn, replace_document_id)
        return previous_document, previous_document["version"] + 1

    existing_ready = _find_ready_document_by_title(conn, title)
    if existing_ready is not None:
        raise ConflictError(
            f"an ACTIVE (READY) document titled {title!r} already exists "
            f"(id={existing_ready['id']}); pass replace_document_id to upload a new version"
        )
    return None, 1


def _run_pipeline(
    conn: PGConnection,
    document: dict,
    previous_document: dict | None,
    file_bytes: bytes,
    *,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> dict:
    """The SAVEPOINT-protected extract/chunk/embed/store sequence -- see
    module docstring for why the savepoint exists. `document` must
    already be a PROCESSING row; returns it updated to READY or FAILED."""
    document_id = document["id"]

    with conn.cursor() as cur:
        cur.execute("SAVEPOINT ingest_pipeline")

    try:
        text = extraction.clean_text(extraction.extract_text(file_bytes, document["file_type"]))
        if not text.strip():
            raise ExtractionError("no extractable text content (document may be empty, scanned, or image-only)")

        chunks = chunking.chunk_text(text, chunk_size_tokens=chunk_size_tokens, overlap_tokens=overlap_tokens)
        if not chunks:
            raise ExtractionError("chunking produced zero chunks from the extracted text")

        embedding_service = get_embedding_service()
        vectors = embedding_service.generate_embeddings([chunk.content for chunk in chunks])

        _insert_chunks(conn, document_id, chunks, vectors)
        document = _set_status(conn, document_id, KnowledgeDocumentStatus.READY)

        if previous_document is not None:
            _set_status(conn, previous_document["id"], KnowledgeDocumentStatus.ARCHIVED)

    except (ExtractionError, EmbeddingError, psycopg2.Error) as exc:
        with conn.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT ingest_pipeline")
        document = _set_status(conn, document_id, KnowledgeDocumentStatus.FAILED, error_message=str(exc))

    return document


def get_document(conn: PGConnection, document_id: uuid.UUID) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM knowledge_documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(f"knowledge document {document_id} not found")
    return row


def list_documents(
    conn: PGConnection,
    limit: int,
    offset: int,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    conditions: list[str] = []
    params: list = []
    if status is not None:
        conditions.append("status = %s")
        params.append(status)
    if category is not None:
        conditions.append("category = %s")
        params.append(category)
    if search:
        conditions.append("title ILIKE %s")
        params.append(f"%{search}%")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT count(*) AS count FROM knowledge_documents {where_sql}", params)
        total = cur.fetchone()["count"]
        cur.execute(
            f"SELECT * FROM knowledge_documents {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        return cur.fetchall(), total


def list_chunks(conn: PGConnection, document_id: uuid.UUID, limit: int, offset: int) -> tuple[list[dict], int]:
    get_document(conn, document_id)  # raises NotFoundError if missing
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM knowledge_chunks WHERE document_id = %s", (document_id,))
        total = cur.fetchone()["count"]
        cur.execute(
            """
            SELECT id, document_id, chunk_index, content, token_count, created_at
            FROM knowledge_chunks WHERE document_id = %s
            ORDER BY chunk_index LIMIT %s OFFSET %s
            """,
            (document_id, limit, offset),
        )
        return cur.fetchall(), total


def archive_document(conn: PGConnection, document_id: uuid.UUID) -> dict:
    get_document(conn, document_id)
    return _set_status(conn, document_id, KnowledgeDocumentStatus.ARCHIVED)


def delete_document(conn: PGConnection, document_id: uuid.UUID) -> None:
    """Hard delete -- removes the row and, via ON DELETE CASCADE
    (migrations/0006_knowledge_chunks_and_vector.sql), every chunk that
    belonged to it, AND removes the underlying file from storage (local
    disk or S3 -- see app/rag/storage.py's delete()). Used for genuine
    mistakes (wrong file uploaded); the default DELETE behavior in
    app/routers/knowledge.py is archive_document() instead, per
    phase7.md #9 ("we should not destroy historical knowledge blindly")
    -- archive_document() never touches storage, only this does.

    Storage is deleted BEFORE the database row: if the storage delete
    raises (a real AWS/network failure -- rare, since S3's DeleteObject
    is idempotent even against a key that's already gone), the database
    row is deliberately left in place rather than risk the reverse
    ordering's failure mode -- a database row silently gone while its
    file still sits in storage, untracked and never reachable through
    the API again."""
    document = get_document(conn, document_id)
    get_storage_backend().delete(document["storage_location"])
    with conn.cursor() as cur:
        cur.execute("DELETE FROM knowledge_documents WHERE id = %s", (document_id,))


def _find_ready_document_by_title(conn: PGConnection, title: str) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM knowledge_documents WHERE title = %s AND status = %s",
            (title, KnowledgeDocumentStatus.READY.value),
        )
        return cur.fetchone()


def _insert_document(
    conn: PGConnection,
    *,
    document_id: uuid.UUID,
    title: str,
    description: str | None,
    category: str | None,
    file_name: str,
    file_type: str,
    storage_location: str,
    version: int,
    previous_version_id: uuid.UUID | None,
    uploaded_by: uuid.UUID | None,
) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO knowledge_documents
                (id, title, description, category, file_name, file_type,
                 storage_location, version, status, previous_version_id, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                document_id,
                title,
                description,
                category,
                file_name,
                file_type,
                storage_location,
                version,
                KnowledgeDocumentStatus.PROCESSING.value,
                previous_version_id,
                uploaded_by,
            ),
        )
        return cur.fetchone()


def _insert_chunks(
    conn: PGConnection,
    document_id: uuid.UUID,
    chunks: list[chunking.Chunk],
    vectors: list[list[float]],
) -> None:
    rows = [
        (uuid.uuid4(), document_id, chunk.content, chunk.chunk_index, chunk.token_count, to_pgvector_literal(vector))
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO knowledge_chunks (id, document_id, content, chunk_index, token_count, embedding)
            VALUES %s
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s::vector)",
        )


def _set_status(
    conn: PGConnection, document_id: uuid.UUID, status: KnowledgeDocumentStatus, error_message: str | None = None
) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE knowledge_documents SET status = %s, error_message = %s WHERE id = %s RETURNING *",
            (status.value, error_message, document_id),
        )
        return cur.fetchone()
