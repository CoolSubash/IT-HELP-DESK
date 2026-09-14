"""Request/response shapes for the presigned-upload path
(POST /admin/knowledge/presign + POST /admin/knowledge/{id}/complete --
app/routers/knowledge.py, app/rag/ingestion_service.py). See that
module's docstring for how this differs from the direct multipart
POST /admin/knowledge."""
import uuid

from pydantic import BaseModel, Field

from app.schemas.knowledge_document import KnowledgeDocumentRead


class PresignUploadRequest(BaseModel):
    title: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    replace_document_id: uuid.UUID | None = None


class PresignUploadResponse(BaseModel):
    document: KnowledgeDocumentRead
    upload_url: str
    expires_in: int
