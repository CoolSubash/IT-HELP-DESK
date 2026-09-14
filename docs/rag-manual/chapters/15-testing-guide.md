# Testing Guide

## Prerequisites

Python 3.12, Docker (for a local Postgres+pgvector container), and a terminal. Nothing else. Every step below runs with **zero external services and zero AWS credentials** -- the default settings (`EMBEDDING_PROVIDER=dev`, `KNOWLEDGE_STORAGE_BACKEND=local`) mean the entire pipeline, every automated test, and every manual curl call in this chapter work completely offline.

## 1. Local environment setup

From a clean checkout, every command below runs from the `backend/` directory unless stated otherwise.

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in `requirements.txt` (FastAPI, psycopg2, pydantic, boto3, and this phase's additions: `python-multipart` for file uploads, `pgvector` for the Postgres adapter, `pypdf` and `python-docx` for extraction) plus `pytest`, `httpx`, and `reportlab`. `reportlab` is a **test-only** dependency -- it exists solely to generate a real, valid PDF file inside `tests/test_rag_ingestion.py`, so that test exercises `pypdf`'s actual parsing code against real PDF bytes rather than a hand-typed fake.

```bash
cp .env.example .env
```

The RAG-specific settings in `.env.example` already have sensible local-development defaults and don't need editing to run anything in this chapter: `EMBEDDING_PROVIDER=dev`, `KNOWLEDGE_STORAGE_BACKEND=local`, `RAG_CHUNK_SIZE_WORDS=600`, `RAG_CHUNK_OVERLAP_WORDS=80`.

```bash
cd ..                          # back to repo root
docker compose up -d           # starts Postgres, using the pinned pgvector/pgvector:pg16 image
cd backend
python -m migrations.run_migrations
```

Expected output includes `Applying 0006_knowledge_chunks_and_vector.sql ...` / `Applied 0006_knowledge_chunks_and_vector.sql` alongside the five pre-existing migrations from earlier phases -- this is the migration that enables the `vector` extension and creates `knowledge_chunks` (Chapter 4).

```bash
python -m seed.seed_data
```

Creates a demo user, two admins, and three demo tickets -- unrelated to RAG directly, but the knowledge-base seed step below needs an existing admin row to use as `uploaded_by`.

```bash
python -m seed.seed_knowledge_base
```

Ingests all eight example documents in `seed/knowledge_docs/*.md` through the real ingestion pipeline -- real chunking, real (dev-provider) embedding, real database inserts, exactly the same code path `POST /admin/knowledge` uses. Expected output:

```text
ingested 'VPN Troubleshooting Guide' -> status=READY id=<uuid>
ingested 'WiFi Troubleshooting Guide' -> status=READY id=<uuid>
ingested 'Password Reset Procedure' -> status=READY id=<uuid>
ingested 'Student Account Setup' -> status=READY id=<uuid>
ingested 'Microsoft Office Installation' -> status=READY id=<uuid>
ingested 'Campus Network Guide' -> status=READY id=<uuid>
ingested 'Printer Troubleshooting' -> status=READY id=<uuid>
ingested 'Known IT Issues' -> status=READY id=<uuid>
```

All eight reaching `status=READY` is the expected, verified outcome -- this was run for real during this implementation and produced exactly this output.

```bash
uvicorn app.main:app --reload
```

The API is now serving at `http://localhost:8000`.

## 2. Running the automated test suite

```bash
pytest -v
```

This runs the complete suite: 63 pre-existing tests from Phases 1-6 (entirely unaffected by this phase's changes -- none of them touch RAG code) plus 57 new Phase 7 tests across six files, 120 tests total, all passing against the real Postgres+pgvector container. What each new file actually proves:

**`tests/test_rag_chunking.py` (6 tests, pure unit tests, no database needed).** Verifies: empty text produces zero chunks; a short text produces exactly one chunk with correctly computed metadata; a long, multi-paragraph text splits into multiple chunks each respecting the configured size budget; chunk boundaries genuinely carry forward overlap text from the previous chunk (the test checks the tail words of one chunk actually reappear at the head of the next, not just that overlap is configured); a bullet list short enough to fit in one chunk isn't needlessly split across two; and an artificially oversized single block with no paragraph breaks splits at sentence boundaries, with every resulting chunk verified to end on a period, never mid-sentence.

**`tests/test_rag_embeddings.py` (6 tests).** Verifies the dev embedding provider is deterministic (embedding identical text twice produces an identical vector -- proving no hidden randomness, such as Python's per-process-randomized `hash()`, leaks into the result); produces vectors of exactly the requested dimension; produces genuinely unit-length (L2-normalized) vectors; that `embed_batch()` produces results identical to calling `embed_text()` once per item; that even empty-string input still produces a valid unit vector rather than crashing; and -- the most important assertion in this file -- that semantically similar text scores a measurably higher cosine similarity than dissimilar text, which is what proves the hashing-trick embedding (Chapter 5) is a genuine, testable stand-in rather than noise wearing an embedding's shape.

**`tests/test_rag_extraction.py` (9 tests).** Covers TXT and Markdown extraction directly; case- and dot-insensitive file-type matching (`"TXT"`, `".txt"`, and `"txt"` all work); an unsupported file type and an empty file both raising `ValidationError`; non-UTF-8 bytes being replaced with a placeholder character rather than crashing extraction; and the text-cleaning function collapsing runs of excess blank lines, normalizing Windows line endings, and preserving Markdown headings/bullets so that chunking's boundary detection still works correctly on cleaned text.

**`tests/test_rag_ingestion.py` (15 tests, against a real Postgres connection -- the most important integration test file).** Ingesting a real TXT, Markdown, PDF, and DOCX file each produces a `READY` document with correctly stored chunks. The PDF and DOCX tests use genuinely generated files -- a real PDF built with `reportlab`'s `canvas` and a real DOCX built with `python-docx`'s `Document`, not hand-typed byte strings -- so `pypdf`'s and `python-docx`'s actual parsing code paths are exercised, not bypassed. An unsupported file type and an empty file are both verified to leave zero new document rows behind (rejected before any row is created). A duplicate title without `replace_document_id` raises `ConflictError`. `replace_document_id` correctly produces a version-2 document and archives the original -- verified end to end. A `replace_document_id` pointing at a nonexistent document raises `NotFoundError`. A monkeypatched embedding-provider failure leaves a document `FAILED` with the exact error message captured and zero chunks inserted. And -- the single most scrutinized test in the whole suite -- a dedicated test proves the *same* database connection stays fully usable for a second, successful, unrelated ingestion immediately after the first one failed, which is the direct proof that the `SAVEPOINT`/`ROLLBACK TO SAVEPOINT` mechanism (Chapter 8) genuinely works and doesn't leave a pooled connection poisoned for whatever request runs on it next.

**`tests/test_rag_retrieval.py` (8 tests, against a real pgvector query, not a mock).** Ingests real documents through the real pipeline, then queries through `retrieval_service.search()`: a VPN-themed query's top result is the VPN document; a password-themed query's top result is the password document; a WiFi-themed query's top result is the WiFi document (this is phase7.md section 20's literal example test, implemented exactly as written). Results come back genuinely ordered by descending score. An archived document is excluded from search even when its content is an exact keyword match for the query (proving the `WHERE d.status = 'READY'` clause, not luck, is doing the filtering). A category filter correctly restricts results. `top_k` correctly caps the result count. A category filter matching zero documents returns an empty list cleanly rather than erroring.

**`tests/test_knowledge_api.py` (13 tests, full HTTP request/response cycle via FastAPI's `TestClient`, not a mocked router).** Covers the admin-authorization boundary explicitly: no `X-Admin-Id` header -> 401; an `X-Admin-Id` that doesn't resolve to a real admin -> 403. Plus the full upload/get/list-chunks/archive-delete/hard-delete/duplicate-409/versioning/search flow, each through a real HTTP call, and a direct assertion that a chunk response's JSON keys never include `embedding`.

A project-wide note worth restating here: this test suite talks to a **real** Postgres database throughout -- there is no SQLite fallback and no mocking of the database layer anywhere in this project, a deliberate choice made back in Phase 1 and carried forward unchanged into this phase. The whole point is that these tests verify the actual schema, actual constraints, and (for this phase specifically) actual pgvector query behavior work correctly -- not merely that Python code runs without throwing an exception.

## 3. Manual API testing walkthrough

A complete, sequential walkthrough against a locally running `uvicorn` instance (from step 1), with the exact curl commands and the actual responses captured running this exact sequence during this implementation.

**(a) Get an admin id to use.**

```bash
docker exec <postgres-container-name> psql -U helpdesk -d helpdesk -t \
  -c "SELECT id FROM admins LIMIT 1;"
```

Or `curl http://localhost:8000/admins` and take any `id` from the response. Save it as `$ADMIN_ID` for the rest of this walkthrough.

**(b) Confirm the auth gate works.**

```bash
curl -i http://localhost:8000/admin/knowledge
```

No header -> `401`. Then:

```bash
curl -i -H "X-Admin-Id: 00000000-0000-0000-0000-000000000000" http://localhost:8000/admin/knowledge
```

A syntactically valid but nonexistent admin id -> `403`.

**(c) List the seeded knowledge base.**

```bash
curl -H "X-Admin-Id: $ADMIN_ID" http://localhost:8000/admin/knowledge
```

Returns the eight seeded documents, `"total": 8`, every one at `"status": "READY"`.

**(d) Run a search.**

```bash
curl -X POST -H "X-Admin-Id: $ADMIN_ID" -H "Content-Type: application/json" \
  -d '{"query": "VPN still does not connect, auth failed", "top_k": 3}' \
  http://localhost:8000/admin/knowledge/search
```

The real captured top result: a `VPN Troubleshooting Guide` chunk covering "VPN connects but internal sites are still unreachable" / "When to Escalate," score approximately `0.2217`; second result, the same document's "Overview" / "Installing Cisco AnyConnect" / "VPN-ERR-403" chunk, score approximately `0.2163`. (See Chapter 10 for why these absolute score values look low and why that's expected for the dev embedding provider specifically, and why it doesn't indicate a problem.)

**(e) Upload a brand-new test document.**

```bash
curl -H "X-Admin-Id: $ADMIN_ID" \
  -F "file=@newdoc.txt" -F "title=Test Onboarding Guide" -F "category=OTHER" \
  http://localhost:8000/admin/knowledge
```

`201`, `"status": "READY"`. Note the returned `"id"` -- used below.

**(f) Re-upload the same title without `replace_document_id`.**

```bash
curl -i -H "X-Admin-Id: $ADMIN_ID" \
  -F "file=@newdoc.txt" -F "title=Test Onboarding Guide" \
  http://localhost:8000/admin/knowledge
```

`409` -- rejected as a duplicate, exactly as designed (Chapter 8/13).

**(g) Re-upload as an explicit new version.**

```bash
curl -H "X-Admin-Id: $ADMIN_ID" \
  -F "file=@newdoc.txt" -F "title=Test Onboarding Guide" -F "replace_document_id=<id-from-e>" \
  http://localhost:8000/admin/knowledge
```

`201`, `"version": 2`, `"previous_version_id"` set to the id from step (e). A follow-up `GET /admin/knowledge/<id-from-e>` confirms that original document's status is now `ARCHIVED`.

**(h) Upload an unsupported file type.**

```bash
curl -i -H "X-Admin-Id: $ADMIN_ID" -F "file=@malware.exe" -F "title=Bad File" \
  http://localhost:8000/admin/knowledge
```

`422`, real captured body: `{"detail": "unsupported file type 'exe'; supported types are ['docx', 'md', 'pdf', 'txt']"}`.

**(i) Upload a genuinely empty file.**

```bash
touch empty.txt
curl -i -H "X-Admin-Id: $ADMIN_ID" -F "file=@empty.txt" -F "title=Empty Doc" \
  http://localhost:8000/admin/knowledge
```

`422`, `{"detail": "uploaded file is empty"}`.

**(j) Upload a deliberately corrupted PDF.**

```bash
echo "%PDF-1.4 not a real pdf" > corrupt.pdf
curl -H "X-Admin-Id: $ADMIN_ID" -F "file=@corrupt.pdf" -F "title=Corrupt PDF Doc" \
  http://localhost:8000/admin/knowledge
```

`201`, but `"status": "FAILED"`, `"error_message": "failed to extract text from pdf file: Stream has ended unexpectedly"`. This is the intended, designed failure-handling behavior (Chapter 8's SAVEPOINT mechanism, Chapter 13's error taxonomy) -- not a bug, and not a crash.

**(k) Fetch a document's chunks and confirm no embedding leaks.**

```bash
curl -H "X-Admin-Id: $ADMIN_ID" http://localhost:8000/admin/knowledge/<any-ready-doc-id>/chunks
```

Confirm the response JSON has no `embedding` key anywhere.

**(l) Archive a document (default delete behavior).**

```bash
curl -i -X DELETE -H "X-Admin-Id: $ADMIN_ID" http://localhost:8000/admin/knowledge/<doc-id>
```

`204`. A follow-up `GET` on the same id shows `"status": "ARCHIVED"` -- the row and its chunks are untouched, just excluded from future search.

**(m) Hard-delete a document.**

```bash
curl -i -X DELETE -H "X-Admin-Id: $ADMIN_ID" "http://localhost:8000/admin/knowledge/<doc-id>?hard=true"
```

`204`. A follow-up `GET` on the same id now returns `404` -- the row and its chunks (via `ON DELETE CASCADE`) are genuinely gone.

## 4. Running the retrieval evaluation

After the knowledge-base seed step (step 1):

```bash
python -m scripts.evaluate_retrieval
```

Prints Recall@1/@3/@5 and Precision@1/@3/@5 against the 10-question labeled dataset in `app/rag/eval.py`, plus a per-question breakdown. Chapter 16 covers what these numbers mean and interprets the actual results from a real run in full.

## 5. Resetting the local environment

To reset the local Postgres schema for a clean manual re-run (not needed for `pytest`, which manages its own schema lifecycle automatically -- see below):

```bash
docker exec <postgres-container-name> psql -U helpdesk -d helpdesk \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

Or, to discard the container's data volume entirely: `docker compose down -v && docker compose up -d`. Either way, follow with `python -m migrations.run_migrations`, `python -m seed.seed_data`, and `python -m seed.seed_knowledge_base` again to get back to a fully seeded state.

This manual reset is never needed to run `pytest` itself: `tests/conftest.py`'s session-scoped fixture already applies every migration fresh at the start of a test session and drops the entire `public` schema at the end, automatically, every time -- the automated suite is fully self-contained and never depends on, or interferes with, whatever state the manual curl walkthrough above left behind.
