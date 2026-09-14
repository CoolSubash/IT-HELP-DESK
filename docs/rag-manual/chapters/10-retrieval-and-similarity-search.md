# Retrieval and Similarity Search

## The flow

phase7.md section 12 describes retrieval as a straight pipeline:

```text
User query
    |
    v
Query embedding
    |
    v
Vector similarity search
    |
    v
Top K chunks
```

`app/rag/retrieval_service.py`'s `search()` function is exactly this pipeline, and nothing more -- everything this phase built toward converges here. Its signature:

```python
def search(
    conn: PGConnection,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
```

## Step 1: embed the query

`get_embedding_service().generate_embedding(query)` -- the exact same `EmbeddingService` interface, and, critically, the exact same *provider*, that produced every chunk's embedding during ingestion (Chapter 5). This is not incidental: a query embedded with one model and compared against chunks embedded with a different model would produce numbers that are not meaningfully comparable at all -- two different embedding models place semantically identical text at different, unrelated points in their own respective vector spaces, so a cosine similarity computed between vectors from two different models is essentially meaningless, not just less accurate. Swapping `EMBEDDING_PROVIDER` from `dev` to `bedrock` therefore requires re-ingesting the knowledge base (or at minimum being aware that old dev-embedded chunks and new Bedrock-embedded chunks are not comparable against each other) -- this is a real operational constraint of any embedding-based system, not specific to this implementation, and is called out explicitly here so it isn't discovered the hard way later.

## Step 2: the query, annotated line by line

```sql
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
WHERE d.status = %s AND d.category = %s   -- category clause only present when a filter was given
ORDER BY c.embedding <=> %s::vector
LIMIT %s
```

- `1 - (c.embedding <=> %s::vector) AS score` -- computes the similarity score returned to the caller. Chapter 6 explains exactly why `1 - distance` is the right conversion, and why the query parameter needs the explicit `::vector` cast (the `to_pgvector_literal()` helper from that same chapter).
- `JOIN knowledge_documents d ON d.id = c.document_id` -- every chunk needs its parent document's `title`, `category`, and, most importantly, `status`, since a chunk row itself carries no status of its own.
- `WHERE d.status = %s` -- this is the entire mechanism behind "only READY documents are retrievable." There is no separate filter step in application code after the query returns; a `PROCESSING`, `FAILED`, or `ARCHIVED` document's chunks are excluded at the SQL level, by the `WHERE` clause itself, before any row is even fetched into Python.
- `ORDER BY c.embedding <=> %s::vector` -- ascending cosine *distance*, which is descending relevance (Chapter 6). This is the clause the HNSW index (Chapter 6) actually accelerates: this is a real index-backed approximate nearest-neighbor query, not a full-table scan scored row by row in Python, which is what keeps query time roughly stable as the chunk count grows well beyond this project's current handful of documents.
- `LIMIT %s` -- the caller's requested `top_k`, applied last, after ordering.

## Metadata filtering

phase7.md section 13 asks for retrieval to support filtering by metadata, while explicitly allowing the first implementation to "keep metadata simple" as long as it's designed so more filtering can be added later. This implementation's filter is `category`, added as one optional `AND d.category = %s` clause. The design intentionally keeps this pattern easy to extend: adding a second filterable field later -- a hypothetical `department` column, for instance -- is one more optional keyword argument to `search()` and one more conditionally-appended `AND` clause, following the exact same pattern this project's own `ticket_service.list_tickets()` already uses for its own optional filters (`status`, `priority`, `category`, `assigned_admin_id`, `search`), built from fixed SQL fragments with only the *values* coming from caller input -- the same SQL-injection-safe construction technique already established elsewhere in this codebase, reused here rather than invented fresh.

## What comes back

A list of plain dicts (via `psycopg2.extras.RealDictCursor`, consistent with every other service function in this project -- there's no ORM, no model objects, anywhere in this codebase), each with `chunk_id`, `document_id`, `chunk_index`, `content`, `title`, `category`, `score`, already ordered by descending relevance. `POST /admin/knowledge/search` (Chapter 9) wraps this directly into its HTTP response; `app/rag/context.py`'s `build_rag_context()` (Chapter 11) reshapes it into the clean format a future AI agent will consume.

## A real example

Query: `"VPN still does not connect, auth failed"`, `top_k=3`, run against this project's actual seeded 8-document knowledge base. The real, captured top-2 results:

1. `VPN Troubleshooting Guide`, a chunk covering "VPN connects but internal sites are still unreachable" and "When to Escalate" -- score approximately 0.2217.
2. `VPN Troubleshooting Guide`, a chunk covering "Overview," "Installing Cisco AnyConnect," and the "VPN-ERR-403: Authentication Failed" section -- score approximately 0.2163.

Two observations worth making about these actual numbers, honestly rather than optimistically: first, the correct document won, clearly and by a real margin over anything from a different document -- retrieval worked. Second, the absolute score values (around 0.22) look low in isolation if you're expecting something closer to 1.0; this is a property of the **dev embedding provider** specifically (Chapter 5's hashing-trick bag-of-words approach naturally produces lower absolute cosine similarities than a genuinely semantic model would, since it only rewards literal shared vocabulary, and any two pieces of English text share only some fraction of their total possible vocabulary space even when they're topically identical) -- a score of 0.22 from `DevEmbeddingProvider` is not directly comparable to, and should not be read as "worse than," a score of 0.7 or 0.8 that a real semantic model like Bedrock's Titan would likely produce for the same query/chunk pair. What matters for retrieval *correctness* is the *relative ordering* of scores within one query's results, not their absolute magnitude -- and that ordering was correct here.

## What this is tested against

`tests/test_rag_retrieval.py` (8 tests, run against a real pgvector query, not a mock) verifies: a VPN-themed query's top result is the VPN document; a password-themed query's top result is the password document; a WiFi-themed query's top result is the WiFi document (this is phase7.md section 20's literal example test, implemented as written); results come back in genuinely descending score order; an archived document is excluded even when its content is an exact keyword match for the query (proving the `WHERE d.status = 'READY'` clause, not luck, is what's doing the filtering); a category filter correctly restricts results to only that category; `top_k` correctly caps the result count; and a category filter matching zero documents returns an empty list cleanly rather than erroring.
