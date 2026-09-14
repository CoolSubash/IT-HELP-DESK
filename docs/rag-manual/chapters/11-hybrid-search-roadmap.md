# Hybrid Search: Why Not Yet, and What It Would Take

## What's Built, and What Isn't

The retrieval chapter of this manual covers what this phase actually implements: pure vector similarity search over embeddings, using pgvector's HNSW-accelerated cosine distance. phase7.md section 14 is explicit about sequencing: implement vector similarity search first, and only *explain* -- without necessarily implementing -- how keyword search could later be combined with it. This chapter is that explanation. Nothing described here exists in the codebase; every SQL fragment and function signature below is a sketch of a future change, clearly labeled as such.

## Why Hybrid Search Matters at All

Pure semantic (vector) search is very good at understanding that two pieces of text are *about* the same topic even when they share almost no vocabulary -- "my internet keeps cutting out in the dorm" and "WiFi disconnects intermittently in residence halls" would score highly similar despite barely overlapping in words. That strength is also its weakness for a specific, important category of query: an exact, short, low-frequency term that matters enormously but carries very little of what an embedding model treats as "semantic content."

phase7.md gives three concrete examples worth examining individually:

- **`VPN-ERR-403`** -- a specific error code. An embedding model understands this string is "VPN-related," roughly the same way it understands the word "VPN" is VPN-related, but it has no special mechanism to recognize this as an *exact identifier* that should be prioritized over merely topically-similar text. A chunk that discusses VPN authentication failures generally, without ever mentioning this exact code, could easily out-score the one chunk that documents this precise error, purely because the general discussion happens to touch more topics an embedding associates with "VPN problem." A keyword or full-text search, by contrast, would find the one chunk containing that literal string immediately and unambiguously.
- **`Cisco AnyConnect`** -- a specific product name. Same reasoning: an embedding captures "this is about VPN client software" reasonably well, but doesn't specially privilege an exact product-name match over a paragraph that discusses VPN clients in general terms.
- **`MFA`** -- a common acronym that shows up across many different topics (VPN login, password reset, account setup all mention it in this project's own seeded documents). Its meaning is diffuse enough across the corpus that a semantic match on "MFA" alone is a weak signal; an exact keyword match narrows things down more sharply when a student's question happens to use that literal term.

None of this means vector search is bad -- the evaluation chapter later in this manual shows it performing at 100% Recall@1 across a real 10-question test set using nothing but vector search. It means vector search has a specific, well-understood blind spot around exact terms, and hybrid search is the standard mitigation for that blind spot.

## The Standard Pattern, Conceptually

The common approach combines two independently-computed relevance scores into one ranking:

1. **A keyword/full-text relevance score.** The classic choice is BM25, a ranking function from traditional information retrieval that scores a document based on how often and how distinctively a query's terms appear in it. This project's stack doesn't need a dedicated BM25 engine to get most of the benefit, though -- Postgres has built-in full-text search (`tsvector` columns, `to_tsquery()`, and the `ts_rank()` function), which would add zero new infrastructure to a project that has already standardized on "everything lives in Postgres" as one of its core architectural decisions (see the vector storage chapter's discussion of why pgvector was chosen over a separate vector database for exactly this same reason).
2. **The existing vector similarity score**, unchanged from what `retrieval_service.search()` already computes.
3. **A combination step** that merges the two into a single ranked list. Two common techniques:
   - **Weighted linear combination**: `combined_score = (weight_a * vector_score) + (weight_b * keyword_score)`, after normalizing both scores onto comparable scales (cosine similarity is already conveniently bounded in roughly the 0-1 range, but a raw `ts_rank` score is not, and would need its own normalization before this kind of blend is meaningful).
   - **Reciprocal rank fusion (RRF)**: instead of trying to make two differently-scaled scores comparable, RRF combines two *ranked lists* by each item's rank *position* -- an item ranked #1 by vector search and #3 by keyword search gets a combined score of `1/(k+1) + 1/(k+3)` for some small constant `k` (commonly 60). RRF sidesteps the score-normalization problem entirely, which is a large part of why it's a popular choice when combining rankings from fundamentally different scoring systems.

## What It Would Concretely Touch

If and when this is built, the changes would be contained and predictable:

- A `tsvector` generated column (or an expression index) on `knowledge_chunks.content`, so Postgres can full-text search chunk content without recomputing a `tsvector` on every query.
- A second SQL branch in `retrieval_service.search()` computing `ts_rank(content_tsv, to_tsquery(...))` alongside the existing vector distance calculation.
- A combination step -- either a weighted blend or RRF, as above -- merging the two ranked lists into the one list `search()` already returns.

None of this requires touching `ingestion_service.py`, the chunking or embedding modules, or any router -- the change is contained entirely within `retrieval_service.search()`'s query and the ranking logic immediately around it, exactly the kind of narrow, contained change the existing docs/05-tech-stack.md document already anticipated when it noted that `search_knowledge_base()`-shaped functions are deliberately the only call sites that would need to change if the storage/retrieval strategy behind them evolves.

## Why This Wasn't Built Now

phase7.md section 14 states the governing rule directly: "Do not implement hybrid search unless it is simple within the current architecture." Building it now, before any real evidence suggested it was needed, would have been speculative complexity added against no demonstrated problem. This project's actual, real evaluation results -- covered in full in the evaluation chapter -- show 100% Recall@1, @3, and @5 across a real 10-question labeled dataset run against the real 8-document seeded knowledge base, using nothing but the vector search this phase actually built. There is no measured retrieval-quality gap for hybrid search to close yet.

That doesn't mean hybrid search will never be worth adding -- a larger, more heterogeneous real-world knowledge base with more exact error codes, product names, and acronyms scattered across many more documents is exactly the scenario where vector search's blind spot described above starts to matter in practice. The right way to decide if and when that point has been reached is the same evaluation harness (`app/rag/eval.py`) already built in this phase: grow the labeled question set to include queries built specifically around exact terms and codes, run the eval script, and see whether Recall@K and Precision@K actually suffer without hybrid search before deciding to build it. Evaluating the need, with real measurements, before building the mitigation is the same discipline phase7.md section 15 asks for applied to the whole retrieval system generally -- it applies just as well to deciding whether a specific enhancement to that system is worth its complexity.
