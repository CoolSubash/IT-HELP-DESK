# Executive Summary

This chapter explains what Phase 7 is, why it exists, what it does and does not do, and how to use the rest of this manual. Everything stated here is expanded in depth in a later chapter -- treat this as the map, not the territory.

## What Phase 7 Is

Phase 7 (`claudeprompt/phase7.md`) builds the **RAG knowledge base and retrieval layer** for the AI IT Helpdesk Agent project. In one sentence: it makes "what does the IT department's official documentation say about this problem" a question the system can answer automatically, given a student's plain-language question, by finding the most relevant chunks of internal IT documentation and handing them back in a clean, structured form.

RAG stands for Retrieval-Augmented Generation. The "Generation" half -- an AI actually composing a reply using this retrieved material -- is explicitly **not** part of this phase. Phase 7 builds only the "Retrieval-Augmented" half: the machinery that finds the right documentation. A future phase will take what this phase produces and feed it into an AI agent that reasons over it and drafts a response. This phase stops one step before that, by design.

## The Full Pipeline

Two flows exist side by side after this phase: one that gets documentation *into* the system (ingestion, run by an admin, ahead of time), and one that gets the right piece of it back *out* (retrieval, run per student question, at query time).

**Ingestion** (offline, admin-triggered, one document at a time):

```text
Admin uploads a document (PDF / TXT / Markdown / DOCX)
        |
Document metadata stored (knowledge_documents row, status=PROCESSING)
        |
Extract text from the file
        |
Clean the extracted text (normalize whitespace, line endings)
        |
Split the text into chunks (boundary-aware, not fixed-character-count)
        |
Generate an embedding vector for each chunk
        |
Store every chunk + its embedding (knowledge_chunks rows)
        |
Document status flips to READY (or FAILED, with a reason, if any step failed)
```

**Retrieval** (online, per student question, milliseconds):

```text
Student's message text
        |
Convert the query text into an embedding vector (same embedding model as ingestion)
        |
Run a vector similarity search against every READY document's chunks
        |
Return the top-K most similar chunks, ranked by score
        |
Package the result into a clean JSON context object
        |
[Phase 7 stops here]
        |
A future AI agent will consume that context object
```

Every arrow above corresponds to a real, working, tested piece of code in this project -- none of it is a plan for later. The rest of this manual documents each stage in detail, including the actual source files, the actual SQL, and the actual test results from running the whole thing against a live Postgres database.

## What This Phase Explicitly Does NOT Build

`claudeprompt/phase7.md` section 23 is explicit that the following are **out of scope** for this phase, and none of them exist in this codebase after Phase 7:

- an AI agent
- automatic AI replies
- Bedrock chat generation (Bedrock is used here only for *embeddings*, never for generating a response)
- ticket classification by AI
- automatic escalation
- email response generation
- autonomous tools
- automatic ticket closure
- a human-approval workflow

Those all belong to later phases. If you are looking for "where does the AI decide what to tell the student," it is not in this codebase yet -- and that is intentional, not an oversight. Phase 7's job is narrower and, deliberately, more testable on its own: prove that the *retrieval* step works correctly, in isolation, before any generation step is layered on top of it. A wrong or noisy retrieval result would otherwise become a wrong AI answer with no visible error anywhere in between -- the retrieval evaluation chapter later in this manual explains why that ordering matters.

## Results at a Glance

Everything below was produced by actually running this system, not estimated:

| Metric | Result |
|---|---|
| Example IT documents ingested through the real pipeline | 8 of 8 succeeded, all reached status `READY` |
| Total automated tests passing | 120 (63 pre-existing Phase 1-6 tests, unaffected by this phase's changes, plus 57 new Phase 7 tests across 6 test files) |
| Retrieval evaluation: Recall@1 | 100.00% |
| Retrieval evaluation: Recall@3 | 100.00% |
| Retrieval evaluation: Recall@5 | 100.00% |
| Labeled evaluation questions used | 10, each with one hand-labeled expected document |

Every one of the 10 labeled evaluation questions retrieved its correct expected document at rank 1 -- not just "somewhere in the top 5." The full evaluation methodology, the complete labeled dataset, and the full per-question breakdown (including Precision@K, which tells a different and complementary story from Recall@K) are covered later in this manual's evaluation chapter.

## How to Use This Manual

This manual is organized to be read start to back by someone who needs to understand, operate, extend, or test this system, but each chapter is also written to stand alone as a reference:

- **System context and the ticket-history/RAG distinction** (the next two chapters) explain *why* this system is shaped the way it is, and the one architectural rule that must never be violated: ticket history and the knowledge base are different things, retrieved differently, for different purposes.
- **Data model, chunking, embeddings, and vector storage** (four chapters) are the technical core: exactly what tables exist, exactly how text becomes chunks, exactly how chunks become vectors, and exactly how those vectors are stored and searched.
- **Ingestion pipeline and the admin API** document the actual code path from an uploaded file to a queryable chunk, and every HTTP endpoint available to manage it, with real request/response examples.
- **Retrieval and similarity search** explains the query-time path in full, including the actual cosine-similarity math, worked with real numbers.
- **Security, error handling, and testing** cover what happens when things go wrong (corrupted files, failed embedding calls, unauthorized callers) and exactly how to verify all of it yourself, step by step.
- **Retrieval evaluation** is where the Recall@K/Precision@K numbers above come from, in full, with the reasoning for why this matters before any AI agent is layered on top.
- **A worked end-to-end example, AWS deployment considerations, and appendices** (full schema reference, full API reference, glossary) close out the manual.

If you only need one thing right now -- to run this system locally and confirm it works -- skip to the testing chapter, which is a self-contained, step-by-step walkthrough starting from a clean checkout.
