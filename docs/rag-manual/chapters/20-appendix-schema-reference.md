# Appendix A: Schema Reference

## Full migration text

The complete, exact contents of `backend/migrations/0006_knowledge_chunks_and_vector.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE knowledge_documents
    ADD COLUMN previous_version_id UUID REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    ADD COLUMN error_message TEXT;

CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    embedding vector(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX ix_knowledge_chunks_document_id ON knowledge_chunks (document_id);

CREATE INDEX ix_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
```

## `knowledge_documents` -- full column reference

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | UUID | No (PK) | Primary key. |
| `title` | VARCHAR(500) | No | Document title; duplicate-detection and versioning key off this. |
| `description` | TEXT | Yes | Optional free-text description. |
| `category` | VARCHAR(100) | Yes | Free-text category; no CHECK constraint (Chapter 4). |
| `file_name` | VARCHAR(255) | No | Original uploaded filename. |
| `file_type` | VARCHAR(50) | No | One of `pdf`, `txt`, `md`, `docx`; enforced in application code. |
| `storage_location` | VARCHAR(1000) | No | Local path or `s3://bucket/key` URI. |
| `version` | INTEGER | No, default 1 | Version number within this title's lineage. |
| `status` | VARCHAR(20) | No, default `PROCESSING` | One of `PROCESSING`, `READY`, `FAILED`, `ARCHIVED` (CHECK-constrained). |
| `previous_version_id` | UUID | Yes | *Phase 7.* Self-referencing FK to the superseded document. |
| `error_message` | TEXT | Yes | *Phase 7.* Set only when `status = FAILED`. |
| `uploaded_by` | UUID | Yes | Uploading admin's id; no FK. |
| `created_at` | TIMESTAMPTZ | No | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | Auto-maintained by `set_updated_at()`. |

### `status` values

| Value | Meaning |
|---|---|
| `PROCESSING` | Ingestion in progress. Not queryable by retrieval. |
| `READY` | Successfully ingested; this is phase7.md's conceptual "ACTIVE." **The only status retrieval ever queries.** |
| `FAILED` | Ingestion failed; `error_message` explains why. Not queryable. |
| `ARCHIVED` | Superseded by a newer version, or manually archived. Preserved, not queryable. |

## `knowledge_chunks` -- full column reference

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | UUID | No (PK) | Primary key. |
| `document_id` | UUID | No | FK to `knowledge_documents.id`, `ON DELETE CASCADE`. |
| `content` | TEXT | No | The chunk's text -- embedded, and returned to callers. |
| `chunk_index` | INTEGER | No | Position within the document, starting at 0. |
| `token_count` | INTEGER | No | Approximate token count (Chapter 5). |
| `embedding` | vector(1024) | Yes* | *Nullable only transiently mid-transaction; never nullable in a committed row.* |
| `created_at` | TIMESTAMPTZ | No | Creation timestamp. |

Plus: `UNIQUE (document_id, chunk_index)`; an index on `document_id`; an HNSW index on `embedding` using `vector_cosine_ops`.

## Relationship

```text
knowledge_documents (1) ----< (many) knowledge_chunks     [ON DELETE CASCADE]
        |
        | previous_version_id (self-referencing, nullable)
        v
knowledge_documents (an earlier version of itself)
```
