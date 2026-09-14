# Appendix B: API Reference

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/admin/knowledge` | Required | Upload a document (multipart: file + title + description? + category? + replace_document_id?). |
| GET | `/admin/knowledge` | Required | Paginated list; filters: `status`, `category`, `search`. |
| GET | `/admin/knowledge/{id}` | Required | Fetch one document. |
| GET | `/admin/knowledge/{id}/chunks` | Required | Paginated list of a document's chunks. |
| DELETE | `/admin/knowledge/{id}` | Required | Archive (default) or hard-delete (`?hard=true`). |
| POST | `/admin/knowledge/search` | Required | Preview retrieval: raw results + RAG context. |

"Required" means `require_admin` (Chapter 12) -- an `X-Admin-Id` header resolving to a real row in `admins`.

## `KnowledgeDocumentRead`

| Field | Type |
|---|---|
| `id` | UUID |
| `title` | str |
| `description` | str \| null |
| `category` | str \| null |
| `file_name` | str |
| `file_type` | str |
| `storage_location` | str |
| `version` | int |
| `status` | KnowledgeDocumentStatus |
| `previous_version_id` | UUID \| null |
| `error_message` | str \| null |
| `uploaded_by` | UUID \| null |
| `created_at` | datetime |
| `updated_at` | datetime |

## `KnowledgeChunkRead`

| Field | Type |
|---|---|
| `id` | UUID |
| `document_id` | UUID |
| `chunk_index` | int |
| `content` | str |
| `token_count` | int |
| `created_at` | datetime |

No `embedding` field -- by design (Chapter 12).

## `KnowledgeSearchRequest`

| Field | Type | Default |
|---|---|---|
| `query` | str (min length 1) | required |
| `top_k` | int (1-20) | 5 |
| `category` | str \| null | null |

## `KnowledgeSearchResponse`

```text
{
  "query": str,
  "results": [ { chunk_id, document_id, title, category, content, score }, ... ],
  "context": { "query": str, "results": [ { title, content, score }, ... ] }
}
```

## `KnowledgeDocumentStatus` enum

| Value | Meaning |
|---|---|
| `PROCESSING` | Ingestion in progress. |
| `READY` | Successfully ingested and queryable by retrieval -- the "ACTIVE" state. |
| `FAILED` | Ingestion failed; see `error_message`. Not queryable. |
| `ARCHIVED` | Superseded or manually archived. Not queryable, preserved. |
