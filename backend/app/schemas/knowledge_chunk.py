"""Pydantic schema for `knowledge_chunks` rows. Deliberately has no
`embedding` field -- phase7.md #18 ("embeddings are not exposed
publicly"): the raw 1024-float vector has no use to an API caller and
would bloat every response for no benefit, so app/rag/ingestion_service.py's
list_chunks() query never even selects that column."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class KnowledgeChunkRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    created_at: datetime
