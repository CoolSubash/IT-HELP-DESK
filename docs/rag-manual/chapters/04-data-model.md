# Data Model

## Design goal: two tables, not many

phase7.md is explicit: "Do not unnecessarily create many tables." This implementation has exactly two tables for the entire knowledge base -- `knowledge_documents` and `knowledge_chunks` -- plus reuses two columns' worth of extension on the first of those, and nothing else. There is no separate "categories" table, no "tags" table, no "versions" table. Category is a plain string column. Versioning is handled with two columns on the existing document row (explained below), not a separate history table. This is a deliberate minimalism, consistent with how the rest of this codebase is built: `enums.py`'s own docstring explains that this project prefers a CHECK constraint on a VARCHAR column over either a separate lookup table or a native Postgres ENUM type, specifically so that adding a new valid value later is an ordinary migration, not a schema redesign.

## `knowledge_documents`: already existed, extended by two columns

This table is not new to Phase 7. It was created in the very first migration of this project (`migrations/0001_initial_schema.sql`), with a comment explaining it was a placeholder for exactly this later phase: *"knowledge_documents: metadata for IT documentation a later RAG phase will chunk and embed. No chunks/embeddings table yet."* Phase 7's job with this table was to finish what it was left waiting for -- populate it for real, and add the two columns its original design didn't yet need.

The table, as it stands after Phase 7's migration:

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | UUID | No (PK) | Primary key. |
| `title` | VARCHAR(500) | No | Human-readable document title (e.g. "VPN Troubleshooting Guide"). The duplicate-detection and versioning logic (see below) keys off this field. |
| `description` | TEXT | Yes | Free-text description, optional. |
| `category` | VARCHAR(100) | Yes | Free-text category (e.g. "VPN", "WIFI"). No CHECK constraint tying it to a fixed enum -- see "Why category is free text," below. |
| `file_name` | VARCHAR(255) | No | The original uploaded filename. |
| `file_type` | VARCHAR(50) | No | One of `pdf`, `txt`, `md`, `docx` (enforced in application code, not a CHECK constraint -- see the Error Handling chapter). |
| `storage_location` | VARCHAR(1000) | No | Where the original file bytes actually live -- a local filesystem path or an `s3://bucket/key` URI, depending on the configured storage backend (Chapter 7). |
| `version` | INTEGER | No, default 1 | Version number within this document's title lineage. Increments by 1 with each re-upload via `replace_document_id`. |
| `status` | VARCHAR(20) | No, default `PROCESSING` | One of `PROCESSING`, `READY`, `FAILED`, `ARCHIVED` (CHECK-constrained). See below. |
| `previous_version_id` | UUID | Yes | **New in Phase 7.** Self-referencing foreign key to the document this row's version superseded, or `NULL` for a version-1 document. |
| `error_message` | TEXT | Yes | **New in Phase 7.** Set only when `status = FAILED`; explains why ingestion failed. `NULL` in every other status. |
| `uploaded_by` | UUID | Yes | The admin who uploaded this document. No foreign key -- see "Why no foreign key," below. |
| `created_at` / `updated_at` | TIMESTAMPTZ | No | Standard timestamps; `updated_at` auto-maintained by the same `set_updated_at()` trigger every other table in this project uses. |

### The `status` lifecycle

phase7.md's own vocabulary talks about documents being `ACTIVE` or `ARCHIVED`. This implementation's actual status values are `PROCESSING`, `READY`, `FAILED`, and `ARCHIVED` -- a superset that existed in the schema (as an enum in `app/enums.py`, `KnowledgeDocumentStatus`) before Phase 7 began, left over from the same Phase 1 placeholder. Rather than rename anything, this implementation maps phase7.md's conceptual "ACTIVE" onto the existing `READY` value: a `READY` document is exactly the phase7.md concept of an active, retrievable document. The extra two states (`PROCESSING`, `FAILED`) exist because phase7.md's own error-handling requirements ("do not leave partially ingested documents in an ACTIVE state") need somewhere for a document to sit while ingestion is in progress, and somewhere for it to land if ingestion fails -- see Chapter 13 (Error Handling) for the full failure-handling design this makes possible.

```text
        upload
          |
          v
     PROCESSING  -----(extraction/chunking/embedding fails)----->  FAILED
          |
          | (chunks + embeddings stored successfully)
          v
        READY  <----------------------(only state retrieval ever queries)
          |
          | (superseded by a new version, or manually archived)
          v
      ARCHIVED
```

A document can only reach `READY` once its chunks and embeddings are fully and successfully stored -- there is no code path that sets `status = READY` before that work is done. Only `READY` documents are ever considered by `retrieval_service.search()` (Chapter 9); `PROCESSING`, `FAILED`, and `ARCHIVED` documents are all excluded from search results, for different reasons (still being ingested, ingestion didn't succeed, and superseded/manually retired, respectively) but with the same practical effect.

### Why `previous_version_id`, not just a bumped `version` number

phase7.md section 9 is specific about the requirement: "We should not destroy historical knowledge blindly... Design the system so an updated document can replace/deactivate the previous version." A `version` integer column alone (which already existed pre-Phase-7) can tell you *that* a document is at version 3, but not *which specific row* was version 2 -- if two documents happened to share a title independently, or if history needed to be traced backward, there'd be no link. `previous_version_id` makes the version chain explicit and queryable: given any document, you can walk backward through its full version history by following `previous_version_id` until you reach a row where it's `NULL` (the original version 1). This is a single nullable self-referencing foreign key, not a separate versions table, in keeping with the "don't create unnecessary tables" goal -- see Chapter 7 for exactly how and when this column gets set during ingestion.

### Why `category` is a free-text column, not a foreign key to a categories table or a native enum

Two reasons, both consistent with existing conventions elsewhere in this codebase (see `app/enums.py`'s own docstring, which makes the identical argument for `ticket_events.event_type` and `agent_actions.action_type`): the set of useful categories for a knowledge base is going to grow as more departments and topics get documented, and neither a foreign-key lookup table nor a native Postgres `ENUM` type make adding a new value as cheap as it should be (a native enum needs `ALTER TYPE ... ADD VALUE`, with its own transactional quirks; a lookup table needs an extra join on every query). The eight example documents in this project reuse the existing `TicketCategory` enum's string values (`VPN`, `WIFI`, `PASSWORD`, etc.) as a matter of consistency -- so a future AI agent's category-scoped search lines up with the vocabulary tickets already use -- but nothing in the database enforces that; it's a convention, not a constraint.

### Why `uploaded_by` has no foreign key

This follows a pattern already established everywhere else in this codebase for admin-actor columns: `tickets.assigned_admin_id`, `ticket_events`/`messages`' actor references, and the original (pre-Phase-7) `knowledge_documents.uploaded_by` column are all plain `UUID` columns with no foreign-key constraint, because -- as the project's own README explains -- this project had no `admins` table at all until Phase 3, and by the time it existed, adding an FK retroactively to every already-shaped column wasn't worth a migration for columns that already worked correctly without one. Phase 7 didn't change this convention; it just used the same shape for a new document row's `uploaded_by`.

## `knowledge_chunks`: new in Phase 7

The table `knowledge_documents` was always waiting for:

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | UUID | No (PK) | Primary key. |
| `document_id` | UUID | No | Foreign key to `knowledge_documents.id`, `ON DELETE CASCADE`. |
| `content` | TEXT | No | The chunk's actual text content -- what gets embedded and what gets returned to a caller. |
| `chunk_index` | INTEGER | No | Position of this chunk within its document, starting at 0. |
| `token_count` | INTEGER | No | Approximate token count for this chunk (see the Chunking chapter for exactly how this is computed and why it's an approximation). |
| `embedding` | vector(1024) | Yes* | The chunk's embedding vector. *Nullable only for the brief instant between two SQL statements inside a single ingestion transaction -- a chunk row is never inserted without its embedding already computed; there is no code path that leaves a *committed* row with a `NULL` embedding. |
| `created_at` | TIMESTAMPTZ | No | Standard timestamp. |

Plus a `UNIQUE (document_id, chunk_index)` constraint (two chunks of the same document can never share a position), an index on `document_id` (fast "give me all chunks for this document" lookups, used by `GET /admin/knowledge/{id}/chunks`), and an HNSW index on `embedding` (fast approximate nearest-neighbor search, used by every retrieval query -- see Chapter 6).

`ON DELETE CASCADE` from `knowledge_chunks.document_id` to `knowledge_documents.id` means a hard delete of a document (`DELETE /admin/knowledge/{id}?hard=true`) automatically removes every one of its chunks in the same statement -- there's no orphaned-chunk cleanup step needed anywhere in the application code, because the database itself guarantees it.

### Why `1024` dimensions, specifically

A pgvector `vector` column's dimension is fixed at `CREATE TABLE` time -- it's part of the column's type, not a value that varies row to row. `1024` was chosen because it's the default (and a supported) output size of Amazon Titan Text Embeddings V2, the model this project's production embedding provider (Chapter 5) calls. The local development provider (also Chapter 5) is configured to produce the same dimension, specifically so the exact same `knowledge_chunks` schema, the exact same SQL queries, and the exact same tests work identically regardless of which embedding provider is active -- nothing about the database schema needs to know or care which provider actually produced a given vector.

## Entity relationship, in one picture

```text
knowledge_documents (1) ----< (many) knowledge_chunks
        |
        | previous_version_id (self-referencing, nullable)
        v
knowledge_documents (an earlier version of itself)
```

One document has many chunks (`ON DELETE CASCADE`). A document optionally points to the document it superseded, forming a version chain. Nothing else references either table, and neither table references anything outside itself except `admins` (informally, via the unconstrained `uploaded_by` column).

## Migration mechanics

Like every other schema change in this project, this one is a single plain `.sql` file (`migrations/0006_knowledge_chunks_and_vector.sql`), applied by the project's existing tiny migration runner (`migrations/run_migrations.py`) -- no Alembic, no ORM migration tooling, consistent with the rest of the project's deliberate "no ORM" choice. The full text of this migration is reproduced in the Appendix (Schema Reference chapter) for exact reference. Applying it is one command from `backend/`: `python -m migrations.run_migrations` -- it was run for real against a live `pgvector/pgvector:pg16` Postgres container during this implementation, and applied cleanly on the first attempt, alongside the five pre-existing migrations from earlier phases, with no conflicts.
