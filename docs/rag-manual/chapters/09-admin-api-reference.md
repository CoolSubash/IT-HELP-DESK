# Admin API Reference

## Overview

All six endpoints live under `/admin/knowledge`, defined in `backend/app/routers/knowledge.py`, and every one of them depends on `require_admin` (Chapter 12 explains exactly what that dependency does and does not guarantee). The router is thin, following this codebase's existing convention everywhere else: a route handler validates request shape (via FastAPI/Pydantic), calls exactly one service-layer function, and returns its result -- no business logic lives in the router itself.

phase7.md section 10 suggests `POST /admin/knowledge` and, separately, `POST /admin/knowledge/upload` as two endpoints ("if upload functionality is included"). This implementation combines them deliberately: `POST /admin/knowledge` **is** the upload endpoint -- a single multipart request carrying both the file and its metadata together. There is no scenario anywhere in phase7.md's own description of the system where a document's metadata is created independently of its file (there's no "reserve a title now, attach the file later" workflow described anywhere), so a separate `/upload` alias for what would be the exact same operation was judged to be a distinction without a difference, not an additional capability.

## Endpoint summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/admin/knowledge` | Required | Upload a document (multipart: file + metadata). Runs the full ingestion pipeline synchronously. |
| GET | `/admin/knowledge` | Required | List documents, paginated, with optional `status`/`category`/`search` filters. |
| GET | `/admin/knowledge/{id}` | Required | Fetch one document by id. |
| GET | `/admin/knowledge/{id}/chunks` | Required | List a document's chunks, paginated. |
| DELETE | `/admin/knowledge/{id}` | Required | Archive (default) or, with `?hard=true`, permanently delete. |
| POST | `/admin/knowledge/search` | Required | Preview retrieval quality -- raw results plus the RAG context format. |

## `POST /admin/knowledge`

Multipart form fields: `file` (the document itself), `title` (required), `description` (optional), `category` (optional), `replace_document_id` (optional -- see Chapter 8's versioning explanation).

Real request, captured during this implementation:

```bash
curl -H "X-Admin-Id: e05aa282-d3a1-400e-86f6-452a79e63022" \
  -F "file=@vpn_guide.txt" -F "title=Test Onboarding Guide" -F "category=OTHER" \
  http://localhost:8000/admin/knowledge
```

Real response (HTTP 201):

```json
{
  "id": "2429c665-cd96-454d-9fb5-5010803730db",
  "title": "Test Onboarding Guide",
  "description": null,
  "category": "OTHER",
  "file_name": "newdoc.txt",
  "file_type": "txt",
  "storage_location": "storage/knowledge_documents/2429c665-cd96-454d-9fb5-5010803730db_newdoc.txt",
  "version": 1,
  "status": "READY",
  "previous_version_id": null,
  "error_message": null,
  "uploaded_by": "e05aa282-d3a1-400e-86f6-452a79e63022",
  "created_at": "2026-09-14T02:31:24.532484Z",
  "updated_at": "2026-09-14T02:31:24.532484Z"
}
```

Note that a `201 Created` response does **not**, by itself, guarantee `status: READY` -- it guarantees a document row was created. Per Chapter 8's failure-handling design, `status` may instead be `FAILED`, with `error_message` populated, if extraction/chunking/embedding failed after the row was created. A caller (including a future admin dashboard UI) must check `status` in the response, not just the HTTP status code, to know whether ingestion actually succeeded.

Failure modes returned directly by this endpoint, captured for real:

- Unsupported file type -> HTTP 422: `{"detail": "unsupported file type 'exe'; supported types are ['docx', 'md', 'pdf', 'txt']"}`
- Empty file -> HTTP 422: `{"detail": "uploaded file is empty"}`
- Duplicate title, no `replace_document_id` -> HTTP 409 (body explains which existing document's id blocked it)

## `GET /admin/knowledge`

Query parameters: `limit` (default 20, max 100), `offset` (default 0), `status`, `category`, `search` (case-insensitive title substring match). Returns the project's standard pagination envelope, `Page[KnowledgeDocumentRead]`:

```json
{
  "items": [ { "...": "KnowledgeDocumentRead" }, "..." ],
  "total": 8,
  "limit": 3,
  "offset": 0
}
```

This is the exact same `Page[T]` shape (`items`/`total`/`limit`/`offset`) used by every other paginated list endpoint in this codebase (`GET /tickets`, `GET /users/{id}/tickets`, etc.) -- nothing new was invented for this phase's pagination.

## `GET /admin/knowledge/{id}`

Returns a single `KnowledgeDocumentRead`, or HTTP 404 if the id doesn't exist -- handled uniformly by the same `NotFoundError` -> 404 exception-handler mapping every other resource lookup in this project uses (`app/errors.py`, registered once in `app/main.py`).

## `GET /admin/knowledge/{id}/chunks`

Returns `Page[KnowledgeChunkRead]`. Verified directly, both by code inspection and by test: the response never includes an `embedding` field -- the underlying SQL query in `ingestion_service.list_chunks()` never selects that column in the first place, so there's no risk of it leaking even if the response schema were misconfigured. This is the concrete implementation of phase7.md section 18's "embeddings are not exposed publicly" requirement.

Real response for a document with one chunk:

```json
{
  "items": [
    {
      "id": "4092d1f5-b5ac-44ee-abb6-f3681274e4f5",
      "document_id": "9b48dddd-e0fa-4662-a433-fb73f0cbd375",
      "chunk_index": 0,
      "content": "Test Onboarding Guide\n\nThis is a short test document...",
      "token_count": 49,
      "created_at": "2026-09-14T02:31:24.586537Z"
    }
  ],
  "total": 1,
  "limit": 2,
  "offset": 0
}
```

## `DELETE /admin/knowledge/{id}`

Default behavior (no query parameter) **archives** the document -- sets `status = ARCHIVED`, leaving the row and all its chunks intact but excluded from future retrieval. This is deliberately the *default*, not `?archive=true` as an opt-in, because phase7.md section 9's "do not destroy historical knowledge blindly" principle should be the safe default a caller gets without having to know to ask for it.

`?hard=true` performs a genuine, irreversible delete: the `knowledge_documents` row is removed, and `ON DELETE CASCADE` (Chapter 4) automatically removes every one of its chunks in the same statement. Intended for correcting a genuine mistake (the wrong file uploaded entirely), not for normal document lifecycle management -- normal lifecycle management is archiving, or superseding via a versioned re-upload.

Both paths return HTTP 204 with an empty body on success, and both were verified for real: an archived document's subsequent `GET` shows `status: ARCHIVED`; a hard-deleted document's subsequent `GET` returns HTTP 404.

## `POST /admin/knowledge/search`

Request body:

```json
{ "query": "VPN still does not connect, auth failed", "top_k": 3, "category": null }
```

(`top_k` defaults to 5, constrained to the range 1-20; `category` is optional.)

Response -- both the raw, admin-facing results (with ids and category, useful for inspecting *why* something ranked the way it did) and the clean RAG context format a future AI agent will consume (Chapter 11 covers this shape in full):

```json
{
  "query": "VPN still does not connect, auth failed",
  "results": [
    {
      "chunk_id": "a513a2f7-cc05-4634-8e81-1e436816cb56",
      "document_id": "6e24f7c5-6d46-4b95-a3f7-130c24a12756",
      "title": "VPN Troubleshooting Guide",
      "category": "VPN",
      "content": "### VPN connects but internal sites are still unreachable...",
      "score": 0.2217
    }
  ],
  "context": {
    "query": "VPN still does not connect, auth failed",
    "results": [
      { "title": "VPN Troubleshooting Guide", "content": "...", "score": 0.2217 }
    ]
  }
}
```

This endpoint exists as an **admin-facing preview and testing tool**, not as the mechanism a future AI agent will actually use. A future agent, running inside this same backend process, will call `retrieval_service.search()` directly in Python -- there's no reason to pay an HTTP round-trip to talk to itself. This endpoint's real purpose is letting a human (an admin, or a developer verifying retrieval quality by hand) issue a search the same way the eventual agent's retrieval step will, and see exactly what comes back.

## What this is tested against

`tests/test_knowledge_api.py` (13 tests) exercises every endpoint above through the real FastAPI app via `TestClient` -- a genuine HTTP request/response cycle, not a mocked router -- including the admin-authorization boundary explicitly (missing header -> 401, unrecognized admin id -> 403), the full upload/list/get/chunks/archive/hard-delete/duplicate-409/versioning/search flow, and a direct assertion that a chunk response's keys never include `embedding`.
