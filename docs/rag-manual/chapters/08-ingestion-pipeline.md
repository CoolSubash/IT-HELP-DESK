# Ingestion Pipeline

## The pipeline, end to end

phase7.md section 8 lays out the ingestion flow at a high level:

```text
Admin uploads document
        |
        v
Document stored
        |
        v
Extract text
        |
        v
Clean text
        |
        v
Chunk text
        |
        v
Generate embeddings
        |
        v
Store chunks + vectors
```

`app/rag/ingestion_service.py`'s `ingest_document()` function is the single orchestration point that implements this entire flow -- it's the one function in this codebase that calls into every other RAG module (`storage.py`, `extraction.py`, `chunking.py`, `embeddings/service.py`), and it's the only one that does. Every other module in `app/rag/` does exactly one job and has no knowledge of the others; `ingestion_service.py` is where they're actually wired together.

## Step 1: document storage -- local disk or S3, behind a swappable backend

Before any text extraction happens, the raw uploaded bytes are persisted, using the same provider-abstraction pattern this project already uses for email (Chapter 6) and now embeddings: `app/rag/storage.py` defines a `FileStorage` abstract base class with `save()` and `read()`, and two implementations -- `LocalFileStorage` (the default, `KNOWLEDGE_STORAGE_BACKEND=local`) writes to a directory on the API server's own disk, prefixing each filename with the document's UUID so two uploads named `guide.pdf` never collide; `S3FileStorage` (`KNOWLEDGE_STORAGE_BACKEND=s3`) uploads to a configured private S3 bucket under a `knowledge-documents/<document-id>/` key prefix, deliberately never passing any object-level ACL that could override the bucket's own access policy (see the Security and AWS Deployment chapters for why bucket-level privacy is the correct posture here, not per-object ACLs). Whichever backend is active, `save()` returns a single string -- a local path or an `s3://bucket/key` URI -- stored directly in the existing `storage_location` column. Nothing downstream of this step needs to know or care which backend actually wrote the file.

## Step 2: text extraction -- format-specific, but not a pluggable abstraction

`app/rag/extraction.py`'s `extract_text()` dispatches on file type: plain UTF-8 decoding for `txt`/`md` (with `errors="replace"`, so malformed byte sequences degrade to replacement characters rather than crashing extraction outright), `pypdf`'s `PdfReader` for `pdf` (page text joined with blank lines between pages), and `python-docx`'s `Document` for `docx` (paragraph text joined the same way, skipping empty paragraphs). Unlike the embedding provider, this is deliberately **not** built as a swappable-provider abstraction -- there's no reasonable scenario where this project would swap out its PDF library at runtime based on a setting the way it swaps embedding providers. `python-docx` is imported lazily, inside the function that needs it, specifically so a deployment that never receives a DOCX upload never pays the cost of importing it -- keeping true to phase7.md section 8's instruction: *"If DOCX is easy to support, include it, but do not let DOCX support complicate the core design."*

Any failure during extraction -- a corrupted PDF, an unparseable DOCX -- is caught and re-raised as a single `ExtractionError`, regardless of which underlying library actually raised the original exception. This was verified directly during this implementation: uploading a file containing only the bytes `%PDF-1.4 not a real pdf` (a syntactically-plausible-looking but actually-invalid PDF header) through the real running API produced a document with `status: FAILED` and `error_message: "failed to extract text from pdf file: Stream has ended unexpectedly"` -- not a server error, not a crash, not a hung request; a clean, informative failure captured exactly where the Error Handling chapter says it should be.

## Step 3: cleaning

`clean_text()` normalizes whitespace before chunking sees the text: Windows line endings (`\r\n`) are converted, trailing whitespace is stripped per line, and runs of three or more consecutive blank lines are collapsed down to one -- kept deliberately conservative, collapsing only excess blank lines rather than reformatting content, specifically so `chunking.py`'s block-boundary detection (which relies on blank lines to find paragraph breaks) continues to work predictably. Markdown structure -- heading markers, bullet markers -- is explicitly *not* stripped or altered here, because the next step's boundary detection depends on that structure still being present.

## Step 4 and 5: chunking and embedding

Covered in full in Chapters 4 and 5 respectively; `ingestion_service.py`'s role here is simple orchestration -- call `chunking.chunk_text()` with the configured size/overlap, then call `EmbeddingService.generate_embeddings()` once with the full list of chunk contents (a single batched call, not one call per chunk, even though the default `embed_batch()` implementation loops internally -- this keeps the call site simple regardless of whether a future provider adds real network-level batching).

## Step 6: storing chunks and flipping status to `READY`

Chunk rows are inserted in a single bulk statement via `psycopg2.extras.execute_values`, each embedding converted to pgvector's text-literal format first (Chapter 6 explains exactly why this conversion is necessary). Only after every chunk has been successfully inserted does the document's `status` flip to `READY` -- there is no earlier point in this function where that happens, which is the concrete mechanism behind phase7.md section 19's requirement that a document never appear `ACTIVE`/`READY` while only partially ingested.

## Document versioning: how a re-upload actually works

phase7.md section 9's requirement -- an updated document replaces the old one without destroying it -- is implemented as follows. `ingest_document()` accepts an optional `replace_document_id` parameter:

- **Without it**, the function first checks whether a `READY` document with the same `title` already exists. If one does, the upload is rejected outright with a `ConflictError` (mapped to HTTP 409) *before* any new document row, any file storage write, or any processing happens at all -- a plain duplicate-title upload is treated as a probable mistake, not silently accepted as a second competing "active" version.
- **With it**, the caller is explicitly saying "this upload is a new version of that specific existing document." The new document row is created with `version = old.version + 1` and `previous_version_id` pointing at the document being replaced. Ingestion then proceeds normally (extract, clean, chunk, embed, store) against the *new* row. Only **after** the new version successfully reaches `READY`, the *old* version's status is flipped to `ARCHIVED`.

That last detail is the entire point of the design, and it's worth being explicit about why the ordering matters: if the old version were archived *first* (or at the same time the new version starts processing), and the new version's ingestion then failed for any reason -- a corrupted replacement file, an embedding-provider outage -- the knowledge base would be left with **no working version of that document at all** during the window before someone notices and re-uploads correctly. By archiving the old version only after the new one is confirmed `READY`, the previously-working version stays fully queryable for the entire duration of the replacement attempt, and a failed re-ingestion simply results in a new `FAILED` row sitting alongside the still-working old one -- zero downtime, and the failure is visible (via `GET /admin/knowledge/{id}` on the new row) rather than silent. This exact sequence -- successful new version reaching `READY`, immediately followed by the old version flipping to `ARCHIVED` -- was verified end to end against a real running instance during this implementation, both via direct Python calls in `tests/test_rag_ingestion.py` and via a full HTTP round-trip in `tests/test_knowledge_api.py`.

## Failure handling: the SAVEPOINT, explained in depth

This is the single most subtle piece of engineering in the ingestion pipeline, and it deserves a full explanation rather than a one-line comment, because getting it wrong would be easy and the failure mode would be confusing to debug.

Once a document row has been inserted (`status = PROCESSING`), a failure anywhere in the rest of the pipeline -- extraction, chunking producing zero chunks, an embedding-provider error, or a database error partway through inserting chunks -- must **not** abort the entire request. The document row itself, updated to `status = FAILED` with a descriptive `error_message`, is a normal, useful, expected outcome: an admin looking at `GET /admin/knowledge` should see exactly why a specific upload didn't succeed, not get a generic HTTP 500 with no persisted record of what happened at all.

A naive `try`/`except` around the risky part of the pipeline looks like it should handle this -- catch the exception, then run an `UPDATE ... SET status = 'FAILED'` inside the `except` block. But this breaks specifically when the failure is a **database** error (for instance, a constraint violation partway through inserting several chunk rows): once a single SQL statement inside a transaction fails, PostgreSQL puts the entire transaction into an "aborted" state, and refuses to execute *any further statement* on that same connection -- including the `UPDATE` that's supposed to record the failure -- until an explicit `ROLLBACK` happens. A naive `try`/`except` would catch the original exception successfully, then immediately raise a *new*, different exception (`InFailedSqlTransaction`) the moment it tried to run the status-update query, and the actual failure reason would never make it into `error_message` at all.

The fix is a `SAVEPOINT`, taken immediately before any of the risky work begins:

```python
with conn.cursor() as cur:
    cur.execute("SAVEPOINT ingest_pipeline")

try:
    # extraction, chunking, embedding, chunk insertion, status update to READY
    ...
except (ExtractionError, EmbeddingError, psycopg2.Error) as exc:
    with conn.cursor() as cur:
        cur.execute("ROLLBACK TO SAVEPOINT ingest_pipeline")
    document = _set_status(conn, document_id, KnowledgeDocumentStatus.FAILED, error_message=str(exc))
```

`ROLLBACK TO SAVEPOINT` undoes only the work performed *since* the savepoint was taken (any partially-inserted chunk rows, any status change attempted) -- it does not touch or discard the original `PROCESSING` document row, which was committed to the transaction before the savepoint existed. Crucially, it also returns the connection to a normal, usable state, exactly as if the failed statements had never been attempted -- so the very next line, the `UPDATE` that records `status = FAILED`, executes successfully on the same connection, inside the same outer transaction that `app/database.py`'s `get_db()` will still commit normally once the request finishes (with no exception propagating out of the route handler at all -- from the router's point of view, "ingestion produced a FAILED document" and "ingestion produced a READY document" are both ordinary, successful return values).

This was not left unverified. `tests/test_rag_ingestion.py` includes a test that deliberately forces an embedding-provider failure via `monkeypatch`, confirms the resulting document lands as `FAILED` with the expected error message and zero chunks stored, and then -- on the *same* database connection, in the *same* test, immediately afterward -- runs a second, unrelated, successful ingestion and confirms it completes normally and reaches `READY`. That second half of the test exists specifically to prove the connection wasn't left in a broken state by the first failure -- exactly the scenario a pooled connection would hit in production if two unrelated HTTP requests happened to reuse the same pooled connection, one right after the other, one of which failed.

## What this is tested against

`tests/test_rag_ingestion.py` (15 tests, run against a real Postgres connection) covers every claim in this chapter directly: successful ingestion of a real TXT, Markdown, PDF (a genuine PDF built with `reportlab`, not hand-typed bytes -- so `pypdf`'s actual parsing code runs), and DOCX (a genuine file built with `python-docx`) file, each producing a `READY` document with correctly stored chunks; an unsupported file type and an empty file both being rejected *before* any document row is created; a duplicate title without `replace_document_id` raising `ConflictError`; `replace_document_id` correctly producing a version-2 document with the original archived only afterward; a `replace_document_id` pointing at a nonexistent document raising `NotFoundError`; the embedding-failure-then-recovery savepoint test described above; and the full set of read/list/archive/hard-delete operations (`get_document`, `list_documents` with status/category filtering, `list_chunks`, `archive_document`, `delete_document` with cascade verified directly against the `knowledge_chunks` table).
