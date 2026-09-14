"use client";

import { useState } from "react";
import { listKnowledgeDocuments, uploadDocumentViaPresignedUrl } from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/client";
import { KNOWLEDGE_CATEGORIES, type KnowledgeDocument, type UUID } from "@/types";

interface UploadFormProps {
  adminId: UUID;
  onUploaded: (doc: KnowledgeDocument) => void;
  onCancel: () => void;
  /** Set when opened via a row's "New version" button -- pre-fills and
   * locks the title (a new version must keep the original's title; that
   * invariant is what makes it a version of the same document rather
   * than an unrelated one) and skips the duplicate-title lookup below,
   * since colliding with the very document being replaced is expected. */
  replacing?: KnowledgeDocument | null;
}

type Stage = "idle" | "checking" | "presigning" | "uploading" | "processing" | "done" | "error";

const STAGE_LABEL: Record<Stage, string> = {
  idle: "",
  checking: "Checking for an existing version...",
  presigning: "Requesting an upload URL...",
  uploading: "Uploading file to S3...",
  processing: "Extracting, chunking, and embedding...",
  done: "Done.",
  error: "",
};

export function UploadForm({ adminId, onUploaded, onCancel, replacing = null }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState(replacing?.title ?? "");
  const [category, setCategory] = useState(replacing?.category ?? "");
  const [description, setDescription] = useState(replacing?.description ?? "");
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [versionConflict, setVersionConflict] = useState<KnowledgeDocument | null>(null);

  const busy = stage !== "idle" && stage !== "error";

  async function handleSubmit(e: React.FormEvent, replaceDocumentId?: UUID) {
    e.preventDefault();
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setError(null);
    setVersionConflict(null);

    try {
      // A version replacement (either explicitly opened for one, or
      // confirmed via the conflict banner below) skips this check --
      // colliding with the document it's replacing is expected, not a
      // conflict. Otherwise: look up whether a READY document already
      // has this exact title, independent of pagination/filters on the
      // table behind this form, so the conflict is caught before
      // spending a presigned URL and an S3 upload on a request the API
      // will reject anyway.
      const effectiveReplaceId = replaceDocumentId ?? (replacing ? replacing.id : undefined);
      if (!effectiveReplaceId) {
        setStage("checking");
        const existing = await listKnowledgeDocuments(adminId, { search: title, status: "READY", limit: 100 });
        const exactMatch = existing.items.find((doc) => doc.title === title);
        if (exactMatch) {
          setVersionConflict(exactMatch);
          setStage("idle");
          return;
        }
      }

      const uploaded = await uploadDocumentViaPresignedUrl(
        adminId,
        { file, title, description, category, replaceDocumentId: effectiveReplaceId },
        (uploadStage) => setStage(uploadStage)
      );
      setStage("done");
      onUploaded(uploaded);
    } catch (err) {
      setStage("error");
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
    }
  }

  return (
    <div className="card upload-panel">
      <form className="upload-form" onSubmit={(e) => handleSubmit(e)}>
        <div className="upload-form__field">
          <label htmlFor="kb-file">File (PDF, TXT, Markdown, or DOCX)</label>
          <input
            id="kb-file"
            type="file"
            accept=".pdf,.txt,.md,.docx"
            className="control"
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="upload-form__field">
          <label htmlFor="kb-title">Title</label>
          <input
            id="kb-title"
            type="text"
            className="control"
            value={title}
            disabled={busy || Boolean(replacing)}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>
        <div className="upload-form__field">
          <label htmlFor="kb-category">Category</label>
          <select
            id="kb-category"
            className="control"
            value={category}
            disabled={busy}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">(none)</option>
            {KNOWLEDGE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div className="upload-form__field">
          <label htmlFor="kb-description">Description (optional)</label>
          <input
            id="kb-description"
            type="text"
            className="control"
            value={description}
            disabled={busy}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        {versionConflict && (
          <div className="upload-form__version-notice">
            A READY document titled &ldquo;{versionConflict.title}&rdquo; already exists (v{versionConflict.version}).
            Uploading will create v{versionConflict.version + 1} and archive the current one.{" "}
            <button
              type="button"
              className="btn btn--primary"
              onClick={(e) => handleSubmit(e, versionConflict.id)}
              style={{ marginLeft: 8 }}
            >
              Upload as new version
            </button>{" "}
            <button type="button" className="btn" onClick={() => setVersionConflict(null)} style={{ marginLeft: 4 }}>
              Cancel
            </button>
          </div>
        )}

        <div className="upload-form__actions">
          <button type="submit" className="btn btn--primary" disabled={busy || Boolean(versionConflict)}>
            Upload
          </button>
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          {busy && <span className="upload-form__status">{STAGE_LABEL[stage]}</span>}
          {error && <span className="upload-form__status" style={{ color: "var(--color-danger)" }}>{error}</span>}
        </div>
      </form>
    </div>
  );
}
