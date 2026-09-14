import { apiDelete, apiGet, apiPost, apiPostForm, ApiError, toQueryString } from "./client";
import type {
  KnowledgeChunk,
  KnowledgeDocument,
  KnowledgeDocumentStatus,
  KnowledgeSearchResponse,
  Page,
  PresignUploadResponse,
  UUID,
} from "@/types";

/**
 * Every function here needs the caller's acting-admin id, sent as the
 * `X-Admin-Id` header backend/app/auth.py's require_admin() checks --
 * see that module for exactly what this does and doesn't guarantee
 * (it's a dev-phase stand-in, not real authentication). Pages call these
 * with `useActingAdmin().actingAdminId` (the same id already used for
 * ticket "assigned to me" -- see lib/ActingAdminContext.tsx), and should
 * treat a null id as "not allowed to call this yet," not attempt the
 * call and let it 401.
 */
function adminHeaders(adminId: UUID): HeadersInit {
  return { "X-Admin-Id": adminId };
}

export interface ListKnowledgeDocumentsParams {
  limit?: number;
  offset?: number;
  status?: KnowledgeDocumentStatus;
  category?: string;
  search?: string;
}

export function listKnowledgeDocuments(
  adminId: UUID,
  params: ListKnowledgeDocumentsParams = {}
): Promise<Page<KnowledgeDocument>> {
  return apiGet<Page<KnowledgeDocument>>(
    `/admin/knowledge${toQueryString({ limit: 20, offset: 0, ...params })}`,
    adminHeaders(adminId)
  );
}

export function getKnowledgeDocument(adminId: UUID, id: UUID): Promise<KnowledgeDocument> {
  return apiGet<KnowledgeDocument>(`/admin/knowledge/${id}`, adminHeaders(adminId));
}

export function getKnowledgeDocumentChunks(
  adminId: UUID,
  id: UUID,
  limit = 50,
  offset = 0
): Promise<Page<KnowledgeChunk>> {
  return apiGet<Page<KnowledgeChunk>>(
    `/admin/knowledge/${id}/chunks${toQueryString({ limit, offset })}`,
    adminHeaders(adminId)
  );
}

export function archiveKnowledgeDocument(adminId: UUID, id: UUID): Promise<void> {
  return apiDelete<void>(`/admin/knowledge/${id}`, adminHeaders(adminId));
}

export function hardDeleteKnowledgeDocument(adminId: UUID, id: UUID): Promise<void> {
  return apiDelete<void>(`/admin/knowledge/${id}?hard=true`, adminHeaders(adminId));
}

export function searchKnowledgeBase(
  adminId: UUID,
  query: string,
  topK = 5,
  category?: string
): Promise<KnowledgeSearchResponse> {
  return apiPost<KnowledgeSearchResponse>(
    "/admin/knowledge/search",
    { query, top_k: topK, category: category || undefined },
    adminHeaders(adminId)
  );
}

export interface UploadDocumentInput {
  file: File;
  title: string;
  description?: string;
  category?: string;
  replaceDocumentId?: UUID;
}

/**
 * The dashboard's actual upload path (phase7.md #10's "Upload document"):
 *
 *   1. POST /admin/knowledge/presign -- ask the API for a place to put
 *      the file (creates the knowledge_documents row as PROCESSING,
 *      returns a short-lived presigned S3 PUT URL).
 *   2. PUT the raw file bytes to that URL -- goes straight to S3, never
 *      touches this app's own API server, so a large PDF's upload time
 *      doesn't add to any request this API server has to hold open.
 *   3. POST /admin/knowledge/{id}/complete -- tell the API the upload
 *      finished; it downloads the bytes back from S3 and runs
 *      extraction/chunking/embedding synchronously, returning the final
 *      READY or FAILED document.
 *
 * If step 2 fails (network drop, S3 rejects the PUT), the PROCESSING row
 * from step 1 is hard-deleted here rather than left behind forever stuck
 * in PROCESSING with no file ever arriving for it.
 */
export async function uploadDocumentViaPresignedUrl(
  adminId: UUID,
  input: UploadDocumentInput,
  onProgress?: (stage: "presigning" | "uploading" | "processing") => void
): Promise<KnowledgeDocument> {
  onProgress?.("presigning");
  const presigned = await apiPost<PresignUploadResponse>(
    "/admin/knowledge/presign",
    {
      title: input.title,
      file_name: input.file.name,
      description: input.description || undefined,
      category: input.category || undefined,
      replace_document_id: input.replaceDocumentId || undefined,
    },
    adminHeaders(adminId)
  );

  onProgress?.("uploading");
  let putResponse: Response;
  try {
    putResponse = await fetch(presigned.upload_url, {
      method: "PUT",
      body: input.file,
      headers: { "Content-Type": input.file.type || "application/octet-stream" },
    });
  } catch (networkError) {
    await hardDeleteKnowledgeDocument(adminId, presigned.document.id).catch(() => undefined);
    throw new ApiError(0, "Could not reach S3 to upload the file (network error). Please try again.");
  }
  if (!putResponse.ok) {
    await hardDeleteKnowledgeDocument(adminId, presigned.document.id).catch(() => undefined);
    throw new ApiError(putResponse.status, "S3 rejected the file upload. Please try again.");
  }

  onProgress?.("processing");
  return apiPost<KnowledgeDocument>(`/admin/knowledge/${presigned.document.id}/complete`, undefined, adminHeaders(adminId));
}

/**
 * The non-browser / small-file path (a script, curl, a future automated
 * importer): file bytes go straight to this API in one multipart
 * request, which stores them and runs the pipeline inline. Kept for
 * parity with the backend's POST /admin/knowledge, which still works
 * exactly as before -- most of this dashboard's own UI uses
 * uploadDocumentViaPresignedUrl instead, see that function's docstring
 * for why.
 */
export function uploadDocumentDirect(adminId: UUID, input: UploadDocumentInput): Promise<KnowledgeDocument> {
  const formData = new FormData();
  formData.append("file", input.file);
  formData.append("title", input.title);
  if (input.description) formData.append("description", input.description);
  if (input.category) formData.append("category", input.category);
  if (input.replaceDocumentId) formData.append("replace_document_id", input.replaceDocumentId);
  return apiPostForm<KnowledgeDocument>("/admin/knowledge", formData, adminHeaders(adminId));
}
