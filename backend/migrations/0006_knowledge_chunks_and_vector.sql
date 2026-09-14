-- Phase 7: RAG knowledge base and retrieval (claudeprompt/phase7.md).
--
-- knowledge_documents already exists (0001_initial_schema.sql) as a
-- Phase 1 placeholder -- this migration does NOT redesign it. It adds:
--   1. the `vector` extension (image is pgvector/pgvector:pg16, so this is
--      just turning the extension on, not installing new software)
--   2. knowledge_chunks -- the table knowledge_documents was always
--      missing: one row per chunk, holding the embedding
--   3. two columns on knowledge_documents needed for versioning and error
--      handling (phase7.md #9 and #19) that a metadata-only Phase 1 table
--      had no reason to have yet

CREATE EXTENSION IF NOT EXISTS vector;

-- previous_version_id: explicit version chain (phase7.md #9 -- "VPN Guide
-- v1 -> VPN Guide v2"). Re-uploading a document creates a NEW row (new id,
-- version = old.version + 1, previous_version_id = old.id) rather than
-- mutating the old one in place; the old row's status flips to ARCHIVED.
-- This keeps every chunk/embedding that already exists immutable and
-- attributable to the exact document version that produced it, instead of
-- silently changing out from under a chunk that was embedded from the old
-- text.
--
-- error_message: set when status = 'FAILED' (extraction/embedding/db
-- failure -- phase7.md #19), so an admin can see *why* without grepping
-- logs. NULL in every other status.
ALTER TABLE knowledge_documents
    ADD COLUMN previous_version_id UUID REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    ADD COLUMN error_message TEXT;

-- knowledge_chunks: one row per chunk of a knowledge_documents row, plus
-- its embedding. content + chunk_index + token_count are always present
-- (a row is only ever inserted after chunking succeeds); embedding is
-- filled in per-chunk immediately after, so it's nullable only for the
-- instant between those two statements inside ingestion_service's
-- transaction -- never nullable in a row a committed transaction leaves
-- behind.
--
-- 1024 dims matches Amazon Titan Text Embeddings V2's default output size
-- (app/rag/embeddings/bedrock_provider.py). A vector column's dimension is
-- fixed at CREATE TABLE time in pgvector, so changing embedding models to
-- one with a different output size later is a migration (new column,
-- backfill, swap) -- see docs/rag-manual for that procedure.
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

-- HNSW over IVFFlat: no training/ANALYZE step needed before the index is
-- useful (IVFFlat's "lists" partitions are built from whatever data exists
-- at CREATE INDEX time -- bad on an empty or small table, which is exactly
-- the state right after this migration runs). pgvector 0.8.6 (confirmed
-- installed in the pgvector/pgvector:pg16 image) supports HNSW natively.
-- vector_cosine_ops matches the cosine distance operator (<=>) used in
-- app/rag/retrieval_service.py.
CREATE INDEX ix_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
