# Vector Storage

## Why PostgreSQL + pgvector, not a separate vector database

phase7.md section 7 is explicit: *"Use PostgreSQL with a vector extension such as `pgvector`... Do NOT introduce Pinecone, OpenSearch, Elasticsearch, or another vector database unless the existing infrastructure makes PostgreSQL vector search clearly unsuitable... We want to keep the architecture understandable."*

This project's own `docs/05-tech-stack.md` (written before this phase, during the project's original planning) already makes the substantive case for this, and it's worth restating because it's the actual reasoning, not just a rule being followed: a future AI agent needs to combine three different kinds of retrieval in a single reasoning turn -- semantic search over knowledge-base chunks (this phase), semantic search over historical ticket resolutions (a plausible future phase), and ordinary structured queries against users/tickets/devices/permissions (already built). Doing all three as one SQL query against a single database (`ORDER BY embedding <=> query_embedding LIMIT 5 WHERE status = 'READY'`) is simpler, and more consistent, than round-tripping between a relational database and a separate vector service and joining the results together in application code. And because `retrieval_service.search()` is the one and only call site that touches `knowledge_chunks`' embedding column, the storage engine behind it could change later without touching anything upstream of it -- the abstraction boundary that matters here isn't "which vector database," it's "this one function."

There's also a concrete practical reason this decision was easy: the project's `docker-compose.yml` was already pinning the `pgvector/pgvector:pg16` image back in Phase 1, specifically in anticipation of this phase, so no new infrastructure had to be introduced at all -- only a `CREATE EXTENSION` statement in a migration.

## Enabling the extension

One line, in `migrations/0006_knowledge_chunks_and_vector.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Since the Docker image already ships pgvector's compiled extension files, this is "turning the extension on," not "installing new software" -- confirmed during this implementation by querying the running container directly: `pgvector` version `0.8.6` was already available and ready to enable.

## The distance metric: cosine distance, explained from first principles

pgvector's `<=>` operator computes **cosine distance**, defined as `1 - cosine_similarity`. To make this concrete rather than just naming it: cosine similarity measures the angle between two vectors, ignoring their magnitude entirely -- it asks "do these two vectors point in the same direction in this 1024-dimensional space," which, for an embedding, corresponds to asking "do these two pieces of text mean approximately the same thing." Two identical vectors have a cosine similarity of 1 (angle of zero). Two unrelated vectors, in a high-dimensional space, tend to be close to orthogonal (similarity near 0). Two vectors pointing in opposite directions have a similarity of -1. Cosine *distance* (what `<=>` actually computes) is just `1 - similarity`, so it ranges from 0 (identical direction -- most relevant) up to 2 (opposite direction -- least relevant), with the ordering flipped relative to similarity: **smaller distance means more relevant.**

This is why `retrieval_service.search()`'s query orders results with `ORDER BY embedding <=> query_embedding` -- ascending distance, which is the same as descending relevance -- and separately computes a `score` field as `1 - (embedding <=> query_embedding)`, converting the distance back into a similarity in the familiar "higher is better, roughly 0 to 1" range that phase7.md's own example response format shows (`"score": 0.89`). The `score` field returned to an API caller is always this similarity value, never the raw distance -- so "higher score is more relevant" is uniformly true everywhere a score appears in this system's output, even though the underlying SQL sorts by the inverted distance value.

Why cosine distance specifically, rather than Euclidean distance (pgvector also supports `<->`) or raw dot product (`<#>`)? Because both this project's embedding providers produce **normalized** (unit-length) vectors -- `DevEmbeddingProvider` explicitly L2-normalizes its output, and `BedrockEmbeddingProvider` requests `normalize: true` from Bedrock. For normalized vectors, cosine similarity and dot product become mathematically equivalent, and cosine distance becomes the natural, magnitude-independent choice: it measures pure semantic direction, never rewarding a chunk simply for being longer or shorter text.

## Why HNSW, not IVFFlat

pgvector supports two approximate-nearest-neighbor index types for a `vector` column. This project's migration builds an HNSW index:

```sql
CREATE INDEX ix_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
```

The choice matters specifically for the state the database is in immediately after this migration runs: it's empty. An IVFFlat index partitions the vector space into a fixed number of "lists," and those partitions are built from whatever data exists in the table *at index-creation time* -- built well on a large, already-populated table, and built poorly (or not meaningfully at all) on an empty or small one, typically requiring an explicit `ANALYZE` and, ideally, a rebuild once real data volume exists. HNSW has no such training step: it's a graph-based index built incrementally as rows are inserted, useful immediately regardless of how much data exists when it's created. Since this migration creates the index before a single row of data exists, and the actual amount of data (a handful of example documents' worth of chunks, growing gradually as an admin uploads more) never reaches a scale where IVFFlat's tuning tradeoffs would clearly win, HNSW was the correct default for this project's scale. `vector_cosine_ops` tells the index to optimize specifically for the `<=>` operator this project's queries actually use -- pgvector requires the index's operator class to match the distance operator used in the query, or the index simply won't be used at all.

## From a Python list of floats to a queryable `vector` column: a genuine implementation subtlety

This is worth documenting explicitly because it was a real bug encountered and fixed during this implementation, and understanding it matters for anyone extending this code.

The `pgvector` Python package (installed as a dependency, providing the psycopg2 adapter) offers `register_vector(conn)`, called once per pooled database connection in `app/database.py`'s `get_db()`. This function does two things: it registers a *read-side* type cast, so a `vector` column fetched back from a query automatically arrives in Python as a `list[float]` rather than a raw string -- this works correctly and is used throughout this project. But its *write-side* adapter, in the installed version of the package, is registered only for `numpy.ndarray` objects, not for plain Python `list` objects. Passing a plain Python list as a query parameter for a `vector`-typed column, without an explicit cast, causes psycopg2 to fall back to its default behavior for a list: adapting it as a Postgres `ARRAY`, not a `vector` -- which fails outright the first time it's used against the `<=>` operator, with an error to the effect of `operator does not exist: vector <=> numeric[]`.

There were two ways to fix this: add `numpy` as a project dependency purely to satisfy one adapter registration, or handle the conversion explicitly without a new dependency. This implementation chose the second, in `app/rag/vector_literal.py`:

```python
def to_pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(component)) for component in vector) + "]"
```

Every place that writes or filters by an embedding -- inserting chunks in `ingestion_service.py`, and building the query in `retrieval_service.search()` -- converts the Python list to pgvector's own text literal format (`"[0.1,0.2,...]"`) using this helper, and pairs it with an explicit `::vector` cast at the corresponding `%s` placeholder in the SQL (for example, `%s::vector`, or, for a bulk insert via `psycopg2.extras.execute_values`, a custom row template ending in `%s::vector`). Postgres parses `"[0.1,0.2,...]"::vector` exactly the way it would parse a `vector` literal written directly in a hand-typed query. This avoids a new dependency, keeps the conversion visible and explicit at every call site rather than hidden inside an adapter registration, and was verified to work correctly end to end -- both the ingestion insert path and the retrieval query path were run for real against a live pgvector-backed table during this implementation.

## What the final picture looks like

```text
PostgreSQL
   |-- users
   |-- tickets
   |-- messages
   |-- ticket_events
   |-- agent_actions
   |-- devices
   |-- admins
   |-- knowledge_documents
   `-- knowledge_chunks
              `-- embedding vector(1024), HNSW-indexed, vector_cosine_ops
```

One database. One connection pool (the same `app/database.py` pool every other table already uses). One query language. A developer who already understands how to query `tickets` in this codebase already knows, structurally, how to query `knowledge_chunks` -- it's a `RealDictCursor`-backed SQL string with `%s` placeholders, exactly like every other service function in this project, with one additional operator (`<=>`) and one additional cast (`::vector`) that this chapter has now fully explained.
