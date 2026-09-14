"use client";

import { DocumentStatusBadge } from "./DocumentStatusBadge";
import { EmptyState } from "@/components/common/States";
import type { KnowledgeDocument } from "@/types";

interface DocumentTableProps {
  documents: KnowledgeDocument[];
  onArchive: (doc: KnowledgeDocument) => void;
  onHardDelete: (doc: KnowledgeDocument) => void;
  onCreateNewVersion: (doc: KnowledgeDocument) => void;
  busyDocumentId: string | null;
}

export function DocumentTable({
  documents,
  onArchive,
  onHardDelete,
  onCreateNewVersion,
  busyDocumentId,
}: DocumentTableProps) {
  if (documents.length === 0) {
    return <EmptyState message="No knowledge base documents match these filters." />;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Category</th>
            <th>Version</th>
            <th>Status</th>
            <th>Uploaded</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const busy = busyDocumentId === doc.id;
            const canManage = doc.status === "READY" || doc.status === "FAILED";
            return (
              <tr key={doc.id}>
                <td>
                  <div>{doc.title}</div>
                  <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{doc.file_name}</div>
                  {doc.status === "FAILED" && doc.error_message && (
                    <div className="doc-error-message" title={doc.error_message}>
                      {doc.error_message}
                    </div>
                  )}
                </td>
                <td>{doc.category ?? "—"}</td>
                <td>v{doc.version}</td>
                <td>
                  <DocumentStatusBadge status={doc.status} />
                </td>
                <td>{new Date(doc.created_at).toLocaleString()}</td>
                <td>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className="btn"
                      disabled={!canManage || busy}
                      onClick={() => onCreateNewVersion(doc)}
                      title="Upload a replacement file as a new version of this document"
                    >
                      New version
                    </button>
                    {doc.status !== "ARCHIVED" && (
                      <button type="button" className="btn" disabled={busy} onClick={() => onArchive(doc)}>
                        Archive
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => onHardDelete(doc)}
                      title="Permanently delete this document and its chunks"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
