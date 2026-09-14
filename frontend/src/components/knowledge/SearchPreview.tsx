"use client";

import { useState } from "react";
import { searchKnowledgeBase } from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/client";
import type { KnowledgeSearchResult, UUID } from "@/types";

/** A small admin-facing tool for eyeballing retrieval quality without
 * leaving the dashboard -- calls the same POST /admin/knowledge/search
 * endpoint documented in docs/rag-manual's admin API reference chapter.
 * Not what a future AI agent will use (it calls retrieval_service.search()
 * directly, in-process -- see that chapter) -- this is purely a human
 * preview tool, same as curling the endpoint by hand. */
export function SearchPreview({ adminId }: { adminId: UUID }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeSearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await searchKnowledgeBase(adminId, query, 5);
      setResults(response.results);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="page-subtitle" style={{ marginBottom: 10 }}>
        Test retrieval -- preview what a student question would surface from READY documents
      </div>
      <form onSubmit={handleSearch} style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <input
          className="control search-input"
          placeholder='e.g. "My VPN is not connecting"'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" className="btn btn--primary" disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </form>
      {error && <div className="state-block state-block--error">{error}</div>}
      {results && results.length === 0 && <div className="state-block">No results.</div>}
      {results && results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {results.map((result) => (
            <div key={result.chunk_id} className="card" style={{ padding: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 600 }}>
                <span>{result.title}</span>
                <span style={{ color: "var(--color-text-muted)" }}>score {result.score.toFixed(4)}</span>
              </div>
              <div style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 6, whiteSpace: "pre-wrap" }}>
                {result.content.length > 300 ? `${result.content.slice(0, 300)}…` : result.content}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
