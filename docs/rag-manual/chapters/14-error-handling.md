# Error Handling Reference

## Purpose of This Chapter

The ingestion pipeline chapter already walked through error handling in the order failures actually occur inside `ingest_document()`. This chapter organizes the same overall territory differently -- as a lookup reference, grouped by exception type and by what actually happens at the HTTP boundary -- so a reader troubleshooting a specific status code or exception can find the relevant explanation directly, without re-reading the whole pipeline narrative.

## The Exception Types

| Exception | Introduced | Crosses HTTP boundary? | Mapped to |
|---|---|---|---|
| `NotFoundError` | Pre-existing (Phase 1/2) | Yes | 404, via a handler already registered in `app/main.py` |
| `ConflictError` | Pre-existing (Phase 2) | Yes | 409, via a handler already registered in `app/main.py` |
| `ValidationError` | New in Phase 7 (`app/errors.py`) | Yes | 422, via a new handler added to `app/main.py` |
| `ExtractionError` | New in Phase 7 (`app/rag/extraction.py`) | No | Never -- always caught inside `ingest_document()` |
| `EmbeddingError` | New in Phase 7 (`app/rag/embeddings/provider.py`) | No | Never -- always caught inside `ingest_document()` |

The first three are ordinary FastAPI-style domain exceptions: a service function raises one, and a single exception handler registered once in `app/main.py` translates it into the matching HTTP response, so no router has to build its own `HTTPException` by hand. `ValidationError` is the one genuinely new addition to this shared mechanism in this phase -- added specifically because none of the existing two (`NotFoundError`, `ConflictError`) correctly describes "the request itself can't be processed, independent of whether it conflicts with anything" (an unsupported file type isn't a 404, because nothing was being looked up; it isn't a 409, because there's no existing resource it conflicts with). 422 (Unprocessable Entity) is the correct HTTP semantics for exactly this case: the request was syntactically well-formed but semantically invalid.

`ExtractionError` and `EmbeddingError` are different in kind from the other three: they are never allowed to reach the HTTP layer at all. Both are always caught inside `ingest_document()`'s try block and converted into a `FAILED` document status with `error_message` set to the exception's message -- see the next section for why.

## Complete Reference Table

| Scenario | Exception raised | HTTP status | Where handled | Document row created? |
|---|---|---|---|---|
| Unsupported file type | `ValidationError` | 422 | Checked in `ingest_document()` before any row is created | No |
| Empty file | `ValidationError` | 422 | Same | No |
| Text extraction failure (corrupt/malformed file) | `ExtractionError` (internal) | 201, `status: "FAILED"` | Caught inside the savepoint-protected block in `ingest_document()` | Yes |
| Embedding API failure | `EmbeddingError` (internal) | 201, `status: "FAILED"` | Same | Yes |
| Database failure mid-insert | `psycopg2.Error` (internal) | 201, `status: "FAILED"` | Same, via `ROLLBACK TO SAVEPOINT` (see the ingestion pipeline chapter) | Yes |
| Duplicate document title, no `replace_document_id` | `ConflictError` | 409 | Checked before any row is created | No |
| `replace_document_id` references a nonexistent document | `NotFoundError` | 404 | Checked before any row is created | No |
| Document or chunk lookup by id fails | `NotFoundError` | 404 | Route handler / service lookup | N/A |
| Missing `X-Admin-Id` header | `HTTPException` raised directly | 401 | `app/auth.py`'s `require_admin` | N/A |
| `X-Admin-Id` doesn't match a real admin | `HTTPException` raised directly | 403 | Same | N/A |

## Why Pipeline Failures Return 201, Not 4xx or 5xx

The three "internal" rows in the table above -- extraction failure, embedding failure, database failure -- are the ones most likely to look surprising at first glance: shouldn't a failure return an error status code? The answer requires being precise about exactly *what* succeeded and what didn't.

By the time any of these three failures can occur, the `knowledge_documents` row itself has already been successfully created (status=PROCESSING) and its file has already been safely stored. The HTTP request's job -- accept an upload, create a trackable resource representing it -- genuinely succeeded. What failed afterward is that resource's internal *processing*: a fact about the resulting resource's state, which the response body communicates via `status: "FAILED"` and `error_message`, not a fact about whether the request itself was handled correctly.

Consider the alternative a less careful implementation might choose: catch the failure and return `500 Internal Server Error`, with no persisted record that an attempt was ever made. This is strictly worse for the person operating the system. A `500` with no corresponding row tells an admin nothing except "something broke, somewhere, at some point" -- they have no way to know which document they were trying to upload, whether it partially succeeded, or what to do next, short of digging through server logs they may not have access to or may not think to check. The actual design instead leaves a durable, inspectable record: `GET /admin/knowledge/{id}` (or `GET /admin/knowledge?status=FAILED`) shows exactly which document failed, precisely what went wrong (`error_message` contains the underlying exception's message, not a generic "an error occurred"), and when. The admin's next action is obvious and immediate: fix whatever the error message describes, and re-upload.

This design decision connects directly to the SAVEPOINT mechanism the ingestion pipeline chapter covers in depth -- that mechanism is precisely what makes it *possible* to reliably reach this well-defined FAILED end state instead of leaving the connection broken partway through, no matter which of the three failure types actually occurred.

## The Life of a FAILED Document

A document that lands in `status: "FAILED"` doesn't disappear or get cleaned up automatically. It remains visible via `GET /admin/knowledge` (filterable with `?status=FAILED` to find every currently-failed document at once) indefinitely, until an admin takes one of two actions:

1. **Re-upload successfully.** A fresh `POST /admin/knowledge` call with a corrected file and the same title creates a brand-new document (a new id, `version: 1`, since the FAILED attempt never reached READY and therefore was never eligible to be treated as an existing "current" version to replace via `replace_document_id` -- the duplicate-title check in `ingest_document()` only looks at documents with `status = 'READY'`, so a FAILED document never blocks a fresh retry under the same title).
2. **Hard-delete it.** `DELETE /admin/knowledge/{id}?hard=true` permanently removes the FAILED row (it has no chunks to cascade-delete, since none were ever inserted).

Nothing about a FAILED document is special-cased to expire, and nothing in this codebase automatically retries a failed ingestion -- both of those are reasonable directions for a future phase to consider (a scheduled cleanup of old FAILED rows past some age, or an automatic retry with backoff for a transient embedding-provider outage), but neither is built here, since neither was asked for by phase7.md and adding either now would be speculative complexity for problems this phase has no evidence exist yet.
