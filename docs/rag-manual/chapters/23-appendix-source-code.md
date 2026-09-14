# Appendix D: Core Source Code

## Purpose of this appendix

The preceding chapters describe and explain the design of the ingestion pipeline, chunking algorithm, retrieval query, and the local development embedding provider in detail. This appendix reproduces the actual, complete, current source of the four modules that do the real work, verbatim, so a reader can check the prior chapters' descriptions against the real implementation directly, without needing the codebase open side by side. Every file below is reproduced in full -- nothing is abridged or paraphrased.

## `app/rag/chunking.py`

The boundary-aware chunking algorithm discussed in depth in the chunking strategy chapter: splits text into whole paragraph/heading/bullet blocks first, packs blocks into chunks up to a token budget, splits an oversized single block at sentence boundaries only as a last resort, and carries overlap text forward from one chunk to the next.

```python
"""
Chunking strategy (phase7.md #4-5).

Why chunk at all: an embedding model compresses a piece of text into one
fixed-size vector. Do that to an entire 20-page VPN guide and the vector
has to represent "installation instructions" AND "troubleshooting steps"
AND "common error codes" all at once -- averaged together, none of it is
retrievable precisely. A student asking "VPN authentication failed" needs
the *troubleshooting* section back, not a vector that's a blurry mix of
the whole document. Smaller, semantically coherent chunks mean each
embedding represents one idea, so a query about that idea scores that
chunk highly and leaves the rest of the document out of the way.

Why NOT chunk arbitrarily (e.g. every 500 characters): splitting in the
middle of a numbered instruction or a table row produces a chunk that is
syntactically valid text but semantically useless -- "3. Click OK. 4."
with no idea what step 4 actually is. Section 5 of phase7.md asks
explicitly for boundary-aware splitting; this module does it in two
passes: first split into whole *blocks* (heading/paragraph/bullet-list),
then pack whole blocks into chunks up to the target size, splitting a
single oversized block only as a last resort (at sentence boundaries).

Tokens vs. words: this project has no tokenizer dependency (no
tiktoken/transformers), and adding one just to count tokens more
precisely was judged not worth the extra dependency for a first
implementation. count_tokens_approx() uses words * 1.3 as a stand-in
(English text averages roughly 0.75 words per GPT-style token, i.e.
~1.3 tokens per word) and every "tokens" concept in this module is in
that approximated unit. This is documented explicitly rather than
pretending it's exact, per phase7.md #5 ("do not blindly assume these
values are optimal") -- see docs/rag-manual for the tradeoff writeup and
how to swap in a real tokenizer later without changing any call site
(chunk_text()'s signature and Chunk shape stay the same).
"""
import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"\S+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")
_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 /,\-]{2,80}:?)\s*$")

WORDS_TO_TOKENS_RATIO = 1.3


def count_tokens_approx(text: str) -> int:
    words = len(_WORD_RE.findall(text))
    return max(1, round(words * WORDS_TO_TOKENS_RATIO))


@dataclass
class Chunk:
    content: str
    chunk_index: int
    token_count: int


def _split_into_blocks(text: str) -> list[str]:
    """First pass: whole paragraphs/headings/bullet groups, never split
    internally. A heading line is kept attached to the block that follows
    it rather than becoming its own zero-content block."""
    raw_blocks = [b.strip() for b in _BLOCK_SPLIT_RE.split(text) if b.strip()]

    blocks: list[str] = []
    pending_heading: str | None = None
    for block in raw_blocks:
        first_line = block.splitlines()[0].strip()
        is_heading_only = len(block.splitlines()) == 1 and _HEADING_RE.match(first_line)
        if is_heading_only:
            pending_heading = block
            continue
        if pending_heading is not None:
            block = f"{pending_heading}\n\n{block}"
            pending_heading = None
        blocks.append(block)

    if pending_heading is not None:
        blocks.append(pending_heading)

    return blocks


def _split_oversized_block(block: str, max_tokens: int) -> list[str]:
    """Last resort for a single block that alone exceeds the chunk size.
    Splits at sentence boundaries rather than mid-sentence, packing
    sentences greedily up to max_tokens."""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(block) if s.strip()]
    if len(sentences) <= 1:
        return [block]

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        sentence_tokens = count_tokens_approx(sentence)
        if current and current_tokens + sentence_tokens > max_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += sentence_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _overlap_prefix(previous_content: str, overlap_tokens: int) -> str:
    """The trailing overlap_tokens words of the previous chunk, used as a
    prefix for the next one, so chunks stay coherent when read
    independently and out of original document order."""
    words = _WORD_RE.findall(previous_content)
    max_words = max(1, round(overlap_tokens / WORDS_TO_TOKENS_RATIO))
    if len(words) <= max_words:
        return previous_content
    return " ".join(words[-max_words:])


def chunk_text(
    text: str,
    chunk_size_tokens: int = 600,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    """Packs whole blocks into chunks up to ~chunk_size_tokens, carrying
    ~overlap_tokens of context forward from the end of one chunk to the
    start of the next. See the chunking strategy chapter for the full
    tradeoff discussion."""
    if not text or not text.strip():
        return []

    blocks = _split_into_blocks(text)

    normalized_blocks: list[str] = []
    for block in blocks:
        if count_tokens_approx(block) > chunk_size_tokens:
            normalized_blocks.extend(_split_oversized_block(block, chunk_size_tokens))
        else:
            normalized_blocks.append(block)

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0

    def _flush() -> None:
        if not current_parts:
            return
        content = "\n\n".join(current_parts)
        chunks.append(Chunk(content=content, chunk_index=len(chunks), token_count=count_tokens_approx(content)))

    for block in normalized_blocks:
        block_tokens = count_tokens_approx(block)
        if current_parts and current_tokens + block_tokens > chunk_size_tokens:
            _flush()
            prefix = _overlap_prefix(current_parts[-1], overlap_tokens) if overlap_tokens > 0 else None
            current_parts = [prefix, block] if prefix else [block]
            current_tokens = count_tokens_approx("\n\n".join(current_parts))
        else:
            current_parts.append(block)
            current_tokens += block_tokens

    _flush()
    return chunks
```

## `app/rag/ingestion_service.py`

The full orchestration: validation, versioning, storage, the SAVEPOINT-protected extract/chunk/embed/store sequence, and every supporting query function (`get_document`, `list_documents`, `list_chunks`, `archive_document`, `delete_document`).

```python
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

ingest_document() is the one function that ties every other app/rag/
module together. Failure handling (phase7.md #19) uses a SAVEPOINT taken
right before any risky work: on failure, ROLLBACK TO SAVEPOINT undoes
only the partial chunk inserts (never the original PROCESSING row),
leaving the connection usable again for the FAILED update -- all still
inside the one outer transaction get_db() commits when the request
finishes successfully.
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
    """Raises ValidationError before any row is written, and ConflictError
    if title collides with an existing READY document and
    replace_document_id wasn't given. Every other failure (extraction,
    embedding, DB) is captured INTO the returned document row as
    status=FAILED rather than raised."""
    file_type = file_type.lower().lstrip(".")
    if file_type not in extraction.SUPPORTED_FILE_TYPES:
        raise ValidationError(
            f"unsupported file type {file_type!r}; supported types are {sorted(extraction.SUPPORTED_FILE_TYPES)}"
        )
    if not file_bytes:
        raise ValidationError("uploaded file is empty")

    previous_document = None
    if replace_document_id is not None:
        previous_document = get_document(conn, replace_document_id)
        version = previous_document["version"] + 1
    else:
        existing_ready = _find_ready_document_by_title(conn, title)
        if existing_ready is not None:
            raise ConflictError(
                f"an ACTIVE (READY) document titled {title!r} already exists "
                f"(id={existing_ready['id']}); pass replace_document_id to upload a new version"
            )
        version = 1

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

    with conn.cursor() as cur:
        cur.execute("SAVEPOINT ingest_pipeline")

    try:
        text = extraction.clean_text(extraction.extract_text(file_bytes, file_type))
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
    get_document(conn, document_id)
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
    """Hard delete -- removes the row and, via ON DELETE CASCADE, every
    chunk that belonged to it."""
    get_document(conn, document_id)
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
                document_id, title, description, category, file_name, file_type,
                storage_location, version, KnowledgeDocumentStatus.PROCESSING.value,
                previous_version_id, uploaded_by,
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
```

## `app/rag/retrieval_service.py`

The full vector similarity search, including the annotated cosine-distance SQL query discussed in the retrieval chapter.

```python
"""
Retrieval / similarity search (phase7.md #11-13).

search() is the one function this whole phase builds toward: everything
in extraction.py/chunking.py/embeddings/ exists to get chunks + vectors
into the database; everything here exists to get the right ones back out.

pgvector's <=> operator is COSINE DISTANCE, defined as
1 - cosine_similarity. score below is computed as
1 - (embedding <=> query_embedding), converting distance back into a
similarity in the familiar 0-1-ish range. ORDER BY embedding <=>
query_embedding is what the HNSW index accelerates -- a real index-backed
nearest-neighbor query, not a full table scan scored in Python.

WHERE d.status = 'READY' is the metadata filter phase7.md #13 asks for --
kept simple for this phase (status + optional category) but structured so
adding another filter later is one more optional keyword argument and one
more AND clause, not a rewrite.
"""
import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.enums import KnowledgeDocumentStatus
from app.rag.embeddings.service import get_embedding_service
from app.rag.vector_literal import to_pgvector_literal


def search(
    conn: PGConnection,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    """Returns up to top_k chunks, each a dict with chunk_id, document_id,
    title, category, content, chunk_index, score -- ordered by score
    descending. Only chunks belonging to a READY document are ever
    considered."""
    embedding_service = get_embedding_service()
    query_vector_literal = to_pgvector_literal(embedding_service.generate_embedding(query))

    where_clauses = ["d.status = %s"]
    where_params: list = [KnowledgeDocumentStatus.READY.value]
    if category:
        where_clauses.append("d.category = %s")
        where_params.append(category)
    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.chunk_index,
            c.content,
            d.title,
            d.category,
            1 - (c.embedding <=> %s::vector) AS score
        FROM knowledge_chunks c
        JOIN knowledge_documents d ON d.id = c.document_id
        WHERE {where_sql}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    params = [query_vector_literal, *where_params, query_vector_literal, top_k]

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()
```

## `app/rag/embeddings/dev_provider.py`

The deterministic hashing-trick embedding used by default (`EMBEDDING_PROVIDER=dev`), discussed at length in the embeddings chapter.

```python
"""
Local-development embedding provider. Selected by EMBEDDING_PROVIDER=dev,
the default. A deterministic "hashing trick" bag-of-words embedding:
each lowercased word token is hashed (SHA-256) into one of `dimensions`
buckets, with a deterministic +1/-1 sign per token to reduce collision
bias, then the whole vector is L2-normalized. Two texts sharing
vocabulary end up with higher cosine similarity, two texts sharing none
end up near-orthogonal. This is NOT a semantic embedding -- production
uses BedrockEmbeddingProvider.
"""
import hashlib
import math
import re

from app.config import settings
from app.rag.embeddings.provider import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class DevEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.embedding_dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _TOKEN_RE.findall(text.lower()) or ["__empty__"]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            vector[0] = 1.0
            norm = 1.0
        return [component / norm for component in vector]
```
