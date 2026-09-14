# Retrieval Evaluation

## "Do not judge RAG only by whether the application runs"

That is phase7.md section 15's own framing, quoted directly, and it deserves to be taken literally rather than treated as a truism. A retrieval pipeline can run without a single error -- no exceptions, no crashes, a plausible-looking JSON response returned for every query, every time -- while consistently returning the *wrong* document for real questions, and nothing in the application's error handling (Chapter 13) would ever surface that as a problem. A wrong retrieval result is not an exception; it's a successful HTTP 200 carrying the wrong content. The only way to catch this is to measure retrieval against questions with a known-correct answer -- which is exactly what this chapter's evaluation harness (`backend/app/rag/eval.py`) does.

## Recall@K and Precision@K, defined precisely for this dataset

This project's evaluation dataset (by design, matching phase7.md's own examples) has exactly **one** labeled correct/expected document per test question. That single fact simplifies the general information-retrieval definitions of these two metrics in a specific, important way, worth working through carefully rather than glossing over.

**Recall@K**, in general, is *(number of relevant items retrieved in the top K) / (total number of relevant items that exist)*. With exactly one relevant document per question, that fraction can only ever be 0 or 1 -- there is no "half credit" possible. Recall@K here reduces exactly to: *did any chunk belonging to the expected document appear anywhere in the top K retrieved chunks*, averaged as a hit-rate across every question in the dataset. This is, precisely, phase7.md section 15's own literal request: "Measure whether the correct document/chunk appears in Top 1 / Top 3 / Top 5."

**Precision@K**, by contrast, is computed at the chunk level as *(number of the K returned chunks that belong to the expected document) / K*. This behaves very differently from Recall@K, and tells a genuinely different story. Work through one concrete example: a query whose single correct chunk lands at rank 1 of a top-5 result, with the other four results all belonging to unrelated documents. Recall@5 for that result is a clean `1.0` -- the correct document *was* found within the top 5. Precision@5 for that exact same result is only `0.2` (one relevant chunk out of five returned) -- because four of the five slots were "wasted" on irrelevant results, even though the one that mattered was found immediately, at rank 1.

That example is the whole reason both numbers matter together, not just one or the other: Recall@K alone cannot distinguish "found immediately, as the clearly dominant result" from "found immediately, but buried among mostly irrelevant noise at every other rank" -- both score identically on Recall@K if the correct answer happens to be present. Precision@K is what tells those two very different outcomes apart.

## The labeled dataset

Ten questions, each paired with exactly one expected document (`app/rag/eval.py`'s `EVAL_DATASET`), deliberately covering all eight seeded documents -- with two questions each probing the VPN and Password documents specifically, since those are the ones phase7.md's own examples emphasize, and one question each for the remaining six:

| Question | Expected document |
|---|---|
| "My VPN says authentication failed." | VPN Troubleshooting Guide |
| "VPN client won't connect at all, error VPN-ERR-403." | VPN Troubleshooting Guide |
| "I forgot my student password." | Password Reset Procedure |
| "I need to reset MFA on my account, I got a new phone." | Password Reset Procedure |
| "Campus WiFi keeps disconnecting." | WiFi Troubleshooting Guide |
| "How do I set up my new student account for the first time?" | Student Account Setup |
| "How do I install Microsoft Office on my laptop as a student?" | Microsoft Office Installation |
| "What's the wired ethernet setup for the dorms?" | Campus Network Guide |
| "The library printer says paper jam but there's no paper stuck." | Printer Troubleshooting |
| "Is there a known outage affecting campus email today?" | Known IT Issues |

## The actual results

Captured from a real run of `python -m scripts.evaluate_retrieval` against the real, fully-seeded 8-document knowledge base, and reproduced identically on a second independent run (expected, given the deterministic dev embedding provider -- see Chapter 5):

| Metric | Result |
|---|---|
| Recall@1 | 100.00% |
| Precision@1 | 100.00% |
| Recall@3 | 100.00% |
| Precision@3 | 43.33% |
| Recall@5 | 100.00% |
| Precision@5 | 26.00% |

Every one of the 10 labeled questions retrieved its correct expected document -- at rank 1, specifically, since Recall@1 is already 100%.

## Interpreting these numbers honestly

100% Recall at every K is a strong result, and it should be stated plainly: it means every single test question in this dataset found its correct expected document, in first place, without exception. But it's worth being precise about *why* this result is this strong and what it does and doesn't demonstrate, rather than treating a perfect score as proof of more than it actually proves.

This is a small (8-document), topically well-separated corpus -- VPN, WiFi, Password, Printer, and so on are lexically quite distinct from one another, which is exactly the condition under which the dev embedding provider's word-overlap-based similarity (Chapter 5) performs at its strongest. A student's query about VPN naturally shares vocabulary with the VPN document and very little vocabulary with the Printer document, so even a fairly crude bag-of-words signal separates them cleanly. This result is a genuinely meaningful, real signal that the **retrieval pipeline itself works correctly end to end** -- chunking, embedding, storage, and the vector query are all functioning and wired together correctly, which is not something that could be faked or coincidental across 10 independent real database queries. But it is not, by itself, proof that retrieval would perform this well against a much larger, more topically overlapping real-world corpus (where many documents might plausibly share far more vocabulary with each other), or with a genuinely semantic embedding model like Bedrock's Titan in place of the word-overlap-based dev provider, which would behave differently -- likely better on synonym-heavy queries, but not something this specific evaluation run measures.

Why does Precision@K fall as K grows, even though Recall stays perfect at every K? This follows mechanically from the single-relevant-document design of this dataset, not from any retrieval quality problem: with exactly one truly relevant document per question, every result slot beyond the first correct one is necessarily filled by a chunk from some *other*, less-relevant document -- there is no second "correct" chunk available to fill slot 2 through 5 with. Precision@5 of 26% is not evidence retrieval got worse; it's the expected mathematical consequence of asking for 5 results when only 1 relevant answer exists in the corpus for that question. Precision@1's perfect 100% score, by contrast, is the metric that most directly reflects whether the *single best* answer returned was actually correct -- and it was, every time.

## Using this harness going forward

Two practical uses beyond a one-time sanity check. First, growing the dataset: per `app/rag/eval.py`'s own docstring, add at least one labeled question for every new real document added to the knowledge base, so the evaluation's coverage keeps pace with the corpus rather than silently becoming stale as new, untested topics are added. Second, and more importantly, use this harness as the actual decision mechanism for tuning choices this phase deliberately left configurable rather than hardcoded (Chapter 4's chunk size and overlap defaults, in particular): before changing `RAG_CHUNK_SIZE_WORDS` or `RAG_CHUNK_OVERLAP_WORDS` from their defaults, re-run `python -m scripts.evaluate_retrieval` before and after the change and compare the Recall@K/Precision@K numbers directly, rather than assuming a change helped. This is precisely the discipline phase7.md section 15 asks for: don't judge whether the system works by whether it runs -- judge it by measuring it against known-correct answers, every time something that could affect retrieval quality changes.
