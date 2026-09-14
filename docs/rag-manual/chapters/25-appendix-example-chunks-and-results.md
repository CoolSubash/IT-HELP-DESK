# Appendix F: Example Chunks and Example Retrieval Results

## Purpose of this appendix

phase7.md's final-deliverables list asks for example chunks and example retrieval results alongside the example documents in the previous appendix. Everything in this appendix was captured by actually querying the real, live database used throughout this implementation -- the VPN Troubleshooting Guide document exactly as it exists after real ingestion, and a real `retrieval_service.search()` call against it. Nothing here is invented or hand-constructed to look plausible.

## Example: how the VPN Troubleshooting Guide was actually chunked

Querying `knowledge_chunks` for the ingested VPN Troubleshooting Guide document (`RAG_CHUNK_SIZE_WORDS=600`, `RAG_CHUNK_OVERLAP_WORDS=80`, the project defaults) returns exactly **two chunks**:

| chunk_index | token_count (approx.) | word count |
|---|---|---|
| 0 | 573 | 441 |
| 1 | 140 | 108 |

**Chunk 0** (441 words) covers the document's "Overview," "Installing Cisco AnyConnect," "Connecting to the VPN," "VPN-ERR-403: Authentication Failed," the unnamed "Connection attempt has failed" section, and most of "VPN connects but internal sites are still unreachable" -- packed together because their combined size (573 approximate tokens) still sits under the 600-token budget, and because `chunk_text()`'s block-packing loop keeps adding whole blocks to the current chunk as long as they fit, only starting a new chunk once the *next* block would push the running total over budget.

**Chunk 1** (108 words) is where this is worth reading closely, because it's a real, live example of the overlap mechanism described in the chunking strategy chapter, not a constructed illustration of it. Its actual content, in full:

```text
### VPN connects but internal sites are still unreachable

- Confirm the AnyConnect icon shows green (connected), not yellow
  (connecting) or red (disconnected).
- DNS can take up to 30 seconds to update after connecting. Wait, then
  retry.
- Some browsers cache a "site not found" result. Clear the browser's DNS
  cache or try a private/incognito window.

## When to Escalate

If a student has confirmed their password is current, MFA was approved
promptly, and the account is more than 24 hours old, and VPN-ERR-403
still occurs, escalate to network engineering -- this can indicate the
account was not correctly added to the VPN authorization group during
provisioning.
```

Notice the heading `### VPN connects but internal sites are still unreachable` and its three bullet points appear in **both** chunk 0 (as the tail of that chunk) and chunk 1 (as the head of this one). This is exactly `_overlap_prefix()` doing its job: when chunk 0 filled up and a new chunk had to start, the last block that had just been added to chunk 0 (this heading + its bullets) was carried forward as chunk 1's opening context, before chunk 1's own new content ("When to Escalate") begins. A reader who only ever retrieves chunk 1 in isolation -- which is exactly what happens at query time, since chunks are retrieved independently and ranked by score, not read in original document order -- still gets the full "VPN connects but internal sites are still unreachable" guidance intact, not a fragment starting mid-list.

## Example: a real retrieval result

Using phase7.md's own literal example query -- a student's message, *"My VPN is not connecting"* -- against the real seeded 8-document knowledge base, with `top_k=3`:

| Rank | Score | Document | Chunk |
|---|---|---|---|
| 1 | 0.3279 | VPN Troubleshooting Guide | chunk 1 ("VPN connects but internal sites are still unreachable" / "When to Escalate") |
| 2 | 0.2764 | VPN Troubleshooting Guide | chunk 0 (Overview through most of the errors section) |
| 3 | 0.2023 | WiFi Troubleshooting Guide | chunk 0 (Overview through "CampusGuest Limitations") |

Both of the VPN Troubleshooting Guide's chunks outrank every chunk of every other document, which is the correct, expected outcome for a VPN-specific query -- and the WiFi Troubleshooting Guide's chunk ranks third rather than being excluded outright, which is also correct and expected: `retrieval_service.search()` doesn't have a relevance *threshold* below which results are dropped, it returns the top `top_k` by score regardless of how low the lowest of those scores is (see the retrieval chapter for the reasoning: filtering by an absolute score threshold in a hashing-trick vocabulary-overlap embedding space is not a reliable signal, since the *meaning* of a given score value shifts depending on how sparse or common the shared vocabulary between two pieces of text happens to be -- ranking is reliable here, an absolute cutoff would not be).

The full, real `build_rag_context()` output for this exact query -- what a future AI agent would actually receive:

```json
{
  "query": "My VPN is not connecting",
  "results": [
    {
      "title": "VPN Troubleshooting Guide",
      "content": "### VPN connects but internal sites are still unreachable...\n[full text is chunk 1, reproduced above]",
      "score": 0.3279
    },
    {
      "title": "VPN Troubleshooting Guide",
      "content": "## Overview\n\nThe university VPN (Virtual Private Network)...\n[full text is chunk 0, reproduced in Appendix E]",
      "score": 0.2764
    },
    {
      "title": "WiFi Troubleshooting Guide",
      "content": "## Overview\n\nCampus WiFi is provided under two network names (SSIDs)...\n[full text in Appendix E]",
      "score": 0.2023
    }
  ]
}
```

(Every `content` field is shown truncated above purely for this appendix's print layout -- the real response contains each chunk's complete, untruncated text with real embedded newlines, exactly as reproduced in full for chunk 1 in the fenced block earlier in this appendix, and for every document's full text in Appendix E. Note also this is a *different* real query from the "VPN still does not connect, auth failed" example used in the admin API reference and testing chapters -- the two queries word themselves differently enough that they produce different score values and, for this one, a different top-ranked chunk, which is itself a useful illustration that retrieval is sensitive to actual query phrasing, not just topic.)

## What this demonstrates end to end

Between this appendix and Appendix E, a reader now has: the complete, real source text of a real knowledge document; the complete, real chunks that document was actually split into, including a genuine (not constructed-for-effect) example of the overlap mechanism carrying context across a chunk boundary; and a complete, real ranked retrieval result and RAG context object for a realistic student query against that document, sitting alongside seven other real documents in the same knowledge base. Every number, every piece of text, and every ranking above came from actually running this system, not from describing what it should do.
