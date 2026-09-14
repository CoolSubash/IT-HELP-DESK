# The RAG Context Format

## One Small, Reusable Interface

phase7.md section 17 draws a clear line for this phase: the future AI agent's eventual context will be built from three parts --

```
CURRENT MESSAGE
        +
TICKET HISTORY
        +
RETRIEVED KNOWLEDGE
        |
AI AGENT
```

-- but this phase should only build the third piece, RETRIEVED KNOWLEDGE, and should do so as a small, reusable interface rather than the full context-assembly logic. That interface is exactly one function, `build_rag_context()`, in `backend/app/rag/context.py`:

```python
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
```

Given the raw output of `retrieval_service.search()`, this produces exactly the JSON shape phase7.md section 16 specifies:

```json
{
  "query": "VPN still does not work",
  "results": [
    { "title": "VPN Troubleshooting Guide", "content": "If the VPN client...", "score": 0.91 },
    { "title": "VPN Common Errors", "content": "Authentication failures...", "score": 0.84 }
  ]
}
```

## What's Deliberately Left Out

`retrieval_service.search()`'s raw results carry more fields than this: `chunk_id`, `document_id`, and `chunk_index` are all present in the raw result dicts (and are exposed as-is in the `results` field of `POST /admin/knowledge/search`'s HTTP response, described in the admin API reference chapter, because an admin debugging retrieval quality benefits from seeing exactly which chunk of which document matched). `build_rag_context()` strips all three of them out.

This isn't an oversight -- it's the whole point of having this function exist separately from the raw search results. An LLM consuming this context to answer a student's question has no legitimate use for a database UUID or a chunk index number. Handing those values to a language model as part of its context risks something subtler than simple clutter: a model given numbers or identifiers with no explained meaning will sometimes invent significance for them anyway -- treating a `chunk_index` of `3` as if it carried some information about recency, importance, or ordering, when it is in fact just an artifact of how one particular document happened to get split during ingestion. The discipline here is to hand a context-consuming model only what it actually needs to reason about the question in front of it: the source document's title (so it can attribute an answer, e.g. "according to the VPN Troubleshooting Guide..."), the actual relevant text, and a similarity score it could in principle use to judge how confident to be in a given piece of retrieved context. Nothing else.

## Why This Is a Separate Function at All

It would have been possible to build this JSON shape inline, directly inside the `POST /admin/knowledge/search` route handler, and skip creating a separate module for it. That wasn't done, for a reason that matters specifically because of what phase7.md explicitly defers to a later phase: the future AI agent is very likely to call `retrieval_service.search()` directly, in-process, rather than through any HTTP endpoint -- it will run inside this same backend, and an HTTP round-trip to itself would be pure overhead with no benefit. If the RAG-context JSON shape were only ever constructed inline inside the search router, that in-process agent code would either have to duplicate the same dict-building logic itself, or reach into the router's internals in an awkward way. By pulling `build_rag_context()` out as its own small, tested, standalone function, both call paths -- the HTTP endpoint (today, for admin testing) and a future in-process agent call (later, for actual use) -- produce the exact same shape from the exact same code. There is no way for the two to quietly drift apart over time, which is exactly the kind of small inconsistency that becomes a confusing bug much later, once an agent depending on this shape actually exists and something upstream changes without this function being updated to match.

## What This Phase Explicitly Does Not Build

Building the full three-part context -- combining this RETRIEVED KNOWLEDGE output with a ticket's CURRENT MESSAGE and TICKET HISTORY into one assembled prompt for an AI agent -- is explicitly out of scope for this phase. phase7.md section 17 states this directly, and the architecture-boundaries chapter of this manual goes into why that separation of responsibilities is treated as a hard rule throughout this whole implementation, not just a scheduling convenience: PostgreSQL owns application state and ticket history, the knowledge base owns official IT documentation, RAG's only job is finding relevant knowledge within that documentation, and reasoning, deciding, and responding are explicitly reserved for the AI agent phase that has not been built yet. `build_rag_context()` produces exactly the third of those responsibilities and stops there.
