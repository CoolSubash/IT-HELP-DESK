"""
Retrieval / similarity search (phase7.md #11-13):

    User query
        |
    Query embedding
        |
    Vector similarity search  (Postgres + pgvector, NOT an external vector DB
        |                       -- see docs/05-tech-stack.md and phase7.md #7)
    Top K chunks

search() is the one function this whole phase builds toward: everything
in extraction.py/chunking.py/embeddings/ exists to get chunks + vectors
into the database; everything here exists to get the right ones back out.

Distance metric: pgvector's `<=>` operator is COSINE DISTANCE, defined as
`1 - cosine_similarity`. Cosine similarity measures the angle between two
vectors (not their magnitude) -- it asks "do these two pieces of text
point in the same semantic direction," which is what "relevant to this
query" means for an embedding. It ranges from -1 (opposite) to 1
(identical direction); `<=>` therefore ranges from 0 (identical
direction) to 2 (opposite). `score` below is computed as
`1 - (embedding <=> query_embedding)`, converting distance back into a
similarity in the familiar 0-1-ish range (1.0 = maximal similarity) that
phase7.md #11's example response shows (`"score": 0.89`). `ORDER BY
embedding <=> query_embedding` (ascending distance = descending
similarity) is what the HNSW index built in
migrations/0006_knowledge_chunks_and_vector.sql actually accelerates --
this is a real index-backed nearest-neighbor query, not a full table scan
scored in Python, so it stays fast as the chunk count grows.

WHERE d.status = 'READY' is the metadata filter phase7.md #13 asks for --
kept simple for this phase (status + optional category) but structured so
adding another filter later (e.g. a hypothetical `department` column) is
one more optional keyword argument and one more `AND` clause, not a
rewrite.
"""
import psycopg2.extras
from psycopg2.extensions import connection as PGConnection

from app.enums import KnowledgeDocumentStatus
from app.rag.embeddings.service import get_embedding_service
from app.rag.vector_literal import to_pgvector_literal


def search(
    conn: PGConnection,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    """Returns up to top_k chunks, each a dict with chunk_id, document_id,
    title, category, content, chunk_index, score -- ordered by score
    descending (most relevant first). Only chunks belonging to a READY
    (phase7.md's "ACTIVE") document are ever considered: an ARCHIVED
    document's chunks still exist (so their embeddings aren't
    recomputed if the document is ever un-archived) but are excluded
    from every search, and a FAILED/PROCESSING document has no chunks to
    exclude in the first place (see app/rag/ingestion_service.py -- chunks
    are only inserted once ingestion fully succeeds)."""
    embedding_service = get_embedding_service()
    query_vector_literal = to_pgvector_literal(embedding_service.generate_embedding(query))

    where_clauses = ["d.status = %s"]
    where_params: list = [KnowledgeDocumentStatus.READY.value]
    if category:
        where_clauses.append("d.category = %s")
        where_params.append(category)
    where_sql = " AND ".join(where_clauses)

    sql = f"""
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
        WHERE {where_sql}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    params = [query_vector_literal, *where_params, query_vector_literal, top_k]

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()
