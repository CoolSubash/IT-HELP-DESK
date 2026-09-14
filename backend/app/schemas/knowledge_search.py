"""Request/response shapes for POST /admin/knowledge/search
(app/routers/knowledge.py), which wraps app/rag/retrieval_service.search()
+ app/rag/context.py's RAG context format (phase7.md #11, #16)."""
import uuid

from pydantic import BaseModel, Field


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    category: str | None = None


class KnowledgeSearchResultRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    category: str | None
    content: str
    score: float


class KnowledgeContextResult(BaseModel):
    title: str
    content: str
    score: float


class KnowledgeContext(BaseModel):
    """phase7.md #16's exact RAG context shape -- see app/rag/context.py."""

    query: str
    results: list[KnowledgeContextResult]


class KnowledgeSearchResponse(BaseModel):
    """`results` (raw, with ids/category -- for admins inspecting
    retrieval quality) and `context` (phase7.md #16's exact shape -- what
    a future AI agent would actually consume) are both included so this
    one endpoint doubles as a manual testing tool (docs/rag-manual) and a
    preview of the future integration point, without needing two
    endpoints for what is fundamentally the same search."""

    query: str
    results: list[KnowledgeSearchResultRead]
    context: KnowledgeContext
