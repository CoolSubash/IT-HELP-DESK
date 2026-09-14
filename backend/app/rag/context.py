"""
RAG context format (phase7.md #16-17): the one small, reusable interface
this phase builds for the future AI agent, without building the agent
itself. Turns retrieval_service.search() results into exactly the JSON
shape phase7.md #16 specifies:

    {
      "query": "...",
      "results": [
        {"title": "...", "content": "...", "score": 0.91},
        ...
      ]
    }

Deliberately excludes chunk_id/document_id/chunk_index -- those are
retrieval/debugging details (present in the raw search() results and in
POST /admin/knowledge/search's response for that reason) that an LLM
consuming this context doesn't need and shouldn't be tempted to
hallucinate meaning from. Deliberately does NOT merge in ticket history
or the current message (phase7.md #17: "keep RAG separate from ticket
history" -- that combination is the future AI agent's job, not this
phase's)."""


def build_rag_context(query: str, results: list[dict]) -> dict:
    return {
        "query": query,
        "results": [
            {
                "title": result["title"],
                "content": result["content"],
                "score": round(float(result["score"]), 4),
            }
            for result in results
        ],
    }
