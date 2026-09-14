"""Pydantic schema for `KnowledgeDocument` -- see app/schemas/user.py for
how this validates a raw row dict."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.enums import KnowledgeDocumentStatus


class KnowledgeDocumentRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    file_name: str
    file_type: str
    storage_location: str
    version: int
    status: KnowledgeDocumentStatus
    # previous_version_id / error_message added in
    # migrations/0006_knowledge_chunks_and_vector.sql (Phase 7) -- see
    # that file's comment for why versioning needed an explicit chain
    # column rather than just bumping `version` in place.
    previous_version_id: uuid.UUID | None
    error_message: str | None
    uploaded_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
