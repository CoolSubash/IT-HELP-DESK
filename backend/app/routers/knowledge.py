"""
Admin knowledge-base endpoints (phase7.md #10). Every endpoint depends on
`require_admin` (app/auth.py) -- see that module for exactly what that
does and doesn't guarantee.

phase7.md #10 lists POST /admin/knowledge/upload as a separate endpoint
from POST /admin/knowledge "if upload functionality is included." This
implementation combines them: POST /admin/knowledge IS the upload
endpoint (multipart: file + metadata fields together), since a knowledge
document's metadata is never meaningful without its file (there is no
"create the row now, attach a file later" workflow anywhere in phase7.md)
-- a separate /upload alias for the exact same operation would be a
distinction without a difference. See app/rag/ingestion_service.py for
the actual pipeline this endpoint kicks off.

Two ways to get a file in:

  POST /admin/knowledge (below) -- multipart, the file's bytes pass
  through this API process. Simple, works against any storage backend
  (including local, so it's what the test suite and any non-browser/
  scripted caller uses), but a large file's full upload time adds to
  this request's latency and its bytes sit in this process's memory for
  the duration.

  POST /admin/knowledge/presign + PUT <url> + POST .../complete -- the
  dashboard's upload page uses this one: get a presigned S3 URL, upload
  the file directly to S3 from the browser (never touching this
  process), then tell the API the upload finished so it can run
  extraction onward. Requires KNOWLEDGE_STORAGE_BACKEND=s3 (the default
  -- see app/config.py). See app/rag/ingestion_service.py's
  create_pending_upload()/complete_pending_upload() for the actual
  logic; both paths share the same extraction/chunking/embedding/
  versioning/failure-handling code underneath.
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.auth import require_admin
from app.database import get_db
from app.enums import KnowledgeDocumentStatus
from app.rag import context as rag_context
from app.rag import ingestion_service, retrieval_service
from app.schemas.knowledge_chunk import KnowledgeChunkRead
from app.schemas.knowledge_document import KnowledgeDocumentRead
from app.schemas.knowledge_search import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.schemas.knowledge_upload import PresignUploadRequest, PresignUploadResponse
from app.schemas.pagination import Page
from psycopg2.extensions import connection as PGConnection

router = APIRouter(prefix="/admin/knowledge", tags=["knowledge"])

PRESIGNED_URL_EXPIRES_IN_SECONDS = 900


@router.post("", response_model=KnowledgeDocumentRead, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str | None = Form(default=None),
    category: str | None = Form(default=None),
    replace_document_id: uuid.UUID | None = Form(default=None),
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    file_bytes = await file.read()
    file_type = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else ""
    return ingestion_service.ingest_document(
        db,
        title=title,
        description=description,
        category=category,
        file_name=file.filename or "untitled",
        file_type=file_type,
        file_bytes=file_bytes,
        uploaded_by=admin["id"],
        replace_document_id=replace_document_id,
    )


@router.post("/presign", response_model=PresignUploadResponse, status_code=201)
def presign_upload(
    payload: PresignUploadRequest,
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    """Step 1 of the direct-to-S3 upload path (see module docstring).
    The browser calls this first, PUTs the raw file bytes straight to
    S3 at `upload_url` (no auth header needed on that PUT -- the URL
    itself is the credential, valid for `expires_in` seconds), then
    calls POST .../complete."""
    try:
        document, upload_url = ingestion_service.create_pending_upload(
            db,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            file_name=payload.file_name,
            file_type=(payload.file_name.rsplit(".", 1)[-1] if "." in payload.file_name else ""),
            uploaded_by=admin["id"],
            replace_document_id=payload.replace_document_id,
        )
    except NotImplementedError as exc:
        # The configured storage backend (KNOWLEDGE_STORAGE_BACKEND=local)
        # doesn't support presigned uploads -- see app/rag/storage.py.
        # Not a client input error, so 501, not 422/409.
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return PresignUploadResponse(document=document, upload_url=upload_url, expires_in=PRESIGNED_URL_EXPIRES_IN_SECONDS)


@router.post("/{document_id}/complete", response_model=KnowledgeDocumentRead)
def complete_upload(
    document_id: uuid.UUID,
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    """Step 2 of the direct-to-S3 upload path -- called after the
    browser's direct PUT to the presigned URL finishes. Runs the same
    extraction/chunking/embedding pipeline POST /admin/knowledge runs
    inline, just triggered here instead of at upload time. Safe to call
    more than once (e.g. a retried request) -- see
    complete_pending_upload()'s docstring."""
    return ingestion_service.complete_pending_upload(db, document_id)


@router.get("", response_model=Page[KnowledgeDocumentRead])
def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: KnowledgeDocumentStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    items, total = ingestion_service.list_documents(
        db, limit, offset, status=status.value if status else None, category=category, search=search
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=KnowledgeDocumentRead)
def get_document(document_id: uuid.UUID, admin: dict = Depends(require_admin), db: PGConnection = Depends(get_db)):
    return ingestion_service.get_document(db, document_id)


@router.get("/{document_id}/chunks", response_model=Page[KnowledgeChunkRead])
def list_document_chunks(
    document_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    items, total = ingestion_service.list_chunks(db, document_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    hard: bool = Query(default=False, description="true = permanently delete row + chunks; false (default) = archive"),
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    if hard:
        ingestion_service.delete_document(db, document_id)
    else:
        ingestion_service.archive_document(db, document_id)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge_base(
    payload: KnowledgeSearchRequest,
    admin: dict = Depends(require_admin),
    db: PGConnection = Depends(get_db),
):
    """Admin-facing preview of retrieval quality (curl/Postman-testable --
    see docs/rag-manual's testing chapter). The in-process Python call a
    future AI agent will actually use is retrieval_service.search()
    directly -- no HTTP hop needed, since the agent runs in this same
    backend process (phase7.md #17)."""
    results = retrieval_service.search(db, payload.query, top_k=payload.top_k, category=payload.category)
    return KnowledgeSearchResponse(
        query=payload.query,
        results=results,
        context=rag_context.build_rag_context(payload.query, results),
    )
