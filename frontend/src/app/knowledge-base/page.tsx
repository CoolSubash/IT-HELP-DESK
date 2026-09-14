"use client";

import { useCallback, useEffect, useState } from "react";
import { DocumentTable } from "@/components/knowledge/DocumentTable";
import { SearchPreview } from "@/components/knowledge/SearchPreview";
import { UploadForm } from "@/components/knowledge/UploadForm";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/States";
import { archiveKnowledgeDocument, hardDeleteKnowledgeDocument, listKnowledgeDocuments } from "@/lib/api/knowledge";
import { useActingAdmin } from "@/lib/ActingAdminContext";
import { KNOWLEDGE_CATEGORIES, type KnowledgeDocument, type KnowledgeDocumentStatus, type Page } from "@/types";

const PAGE_SIZE = 20;
const STATUSES: KnowledgeDocumentStatus[] = ["PROCESSING", "READY", "FAILED", "ARCHIVED"];

export default function KnowledgeBasePage() {
  const { actingAdminId } = useActingAdmin();

  const [status, setStatus] = useState<KnowledgeDocumentStatus | "">("");
  const [category, setCategory] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  const [page, setPage] = useState<Page<KnowledgeDocument> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [replacingDoc, setReplacingDoc] = useState<KnowledgeDocument | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setOffset(0);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const reload = useCallback(() => {
    if (!actingAdminId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    listKnowledgeDocuments(actingAdminId, {
      limit: PAGE_SIZE,
      offset,
      status: status || undefined,
      category: category || undefined,
      search: search || undefined,
    })
      .then(setPage)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [actingAdminId, offset, status, category, search]);

  useEffect(() => {
    reload();
  }, [reload]);

  function resetToFirstPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setOffset(0);
    };
  }

  async function handleArchive(doc: KnowledgeDocument) {
    if (!actingAdminId) return;
    setBusyDocumentId(doc.id);
    try {
      await archiveKnowledgeDocument(actingAdminId, doc.id);
      reload();
    } finally {
      setBusyDocumentId(null);
    }
  }

  async function handleHardDelete(doc: KnowledgeDocument) {
    if (!actingAdminId) return;
    if (!window.confirm(`Permanently delete "${doc.title}" (v${doc.version}) and all its chunks? This cannot be undone.`)) {
      return;
    }
    setBusyDocumentId(doc.id);
    try {
      await hardDeleteKnowledgeDocument(actingAdminId, doc.id);
      reload();
    } finally {
      setBusyDocumentId(null);
    }
  }

  function handleCreateNewVersion(doc: KnowledgeDocument) {
    setReplacingDoc(doc);
    setUploadOpen(true);
  }

  function closeUploadPanel() {
    setUploadOpen(false);
    setReplacingDoc(null);
  }

  if (!actingAdminId) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1 className="page-title">Knowledge Base</h1>
            <div className="page-subtitle">Upload and manage IT documentation used for retrieval (Phase 7 RAG)</div>
          </div>
        </div>
        <EmptyState message='Pick an admin from "Acting as" in the top bar to manage the knowledge base -- every action here is attributed to that admin.' />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Knowledge Base</h1>
          <div className="page-subtitle">
            Upload and manage the IT documentation used for retrieval. Uploads go straight to S3 via a presigned URL,
            then get extracted, chunked, and embedded.
          </div>
        </div>
        {!uploadOpen && (
          <button type="button" className="btn btn--primary" onClick={() => setUploadOpen(true)}>
            Upload document
          </button>
        )}
      </div>

      {uploadOpen && (
        <UploadForm
          adminId={actingAdminId}
          replacing={replacingDoc}
          onCancel={closeUploadPanel}
          onUploaded={() => {
            closeUploadPanel();
            reload();
          }}
        />
      )}

      <div className="filters-bar">
        <input
          className="control search-input"
          placeholder="Search title..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <select
          className="control"
          value={status}
          onChange={(e) => resetToFirstPage(setStatus)(e.target.value as KnowledgeDocumentStatus | "")}
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select className="control" value={category} onChange={(e) => resetToFirstPage(setCategory)(e.target.value)}>
          <option value="">All categories</option>
          {KNOWLEDGE_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      {loading && <LoadingState label="Loading knowledge base..." />}
      {!loading && Boolean(error) && <ErrorState error={error} />}

      {!loading && !error && page && (
        <>
          <DocumentTable
            documents={page.items}
            onArchive={handleArchive}
            onHardDelete={handleHardDelete}
            onCreateNewVersion={handleCreateNewVersion}
            busyDocumentId={busyDocumentId}
          />
          <div className="pagination">
            <span>
              Showing {page.items.length === 0 ? 0 : offset + 1}–{offset + page.items.length} of {page.total}
            </span>
            <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </button>
            <button className="btn" disabled={offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </button>
          </div>
        </>
      )}

      <SearchPreview adminId={actingAdminId} />
    </div>
  );
}
