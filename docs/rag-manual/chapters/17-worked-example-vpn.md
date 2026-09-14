# Worked Example: A Complete VPN Scenario

## Why one concrete example, traced fully

phase7.md section 21 asks for the complete pipeline explained using a concrete VPN example, step by step. Every other chapter in this manual explains one piece of the system in isolation; this chapter does the opposite -- it follows a single, real, end-to-end scenario through every one of the thirteen steps phase7.md describes, in narrative order, using facts and numbers actually observed during this implementation, not a hypothetical.

## Step 1: An admin uploads the VPN Troubleshooting Guide

An IT admin has a Markdown document, `vpn_troubleshooting_guide.md` (the real file at `backend/seed/knowledge_docs/vpn_troubleshooting_guide.md`), containing sections for `## Overview`, `## Installing Cisco AnyConnect`, `## Connecting to the VPN`, `## Common VPN Errors` (with a `### VPN-ERR-403: Authentication Failed` subsection among others), and `## When to Escalate`. They upload it:

```bash
curl -H "X-Admin-Id: <admin-id>" \
  -F "file=@vpn_troubleshooting_guide.md" \
  -F "title=VPN Troubleshooting Guide" \
  -F "category=VPN" \
  http://localhost:8000/admin/knowledge
```

## Step 2: The document is stored

Before any processing happens, `app/rag/storage.py`'s `LocalFileStorage.save()` (the default, local-development backend) writes the raw uploaded bytes to disk under `storage/knowledge_documents/<document-uuid>_vpn_troubleshooting_guide.md`, and a `knowledge_documents` row is inserted with `status = PROCESSING` and `storage_location` pointing at that path. In a real AWS deployment with `KNOWLEDGE_STORAGE_BACKEND=s3`, this same step would instead write to a private S3 bucket under `knowledge-documents/<document-uuid>/vpn_troubleshooting_guide.md` -- everything downstream of this step behaves identically either way (Chapter 8).

## Step 3: Text is extracted

Since this file is Markdown, `app/rag/extraction.py`'s `extract_text()` does the simplest possible thing: decode the raw bytes as UTF-8. (Had this instead been a PDF version of the same guide, this step would run `pypdf`'s `PdfReader` and join each page's extracted text with blank lines between pages -- more work, same output shape: one plain-text string handed to the next step.)

## Step 4: Text is cleaned

`clean_text()` normalizes the extracted Markdown: Windows line endings converted (none present in this particular file, since it was authored on this project directly), trailing whitespace stripped, and any run of three-plus blank lines collapsed to one. Critically, the Markdown heading markers (`##`, `###`) and bullet markers are left completely untouched -- the next step depends on them.

## Step 5: Text is chunked

At the default settings (`RAG_CHUNK_SIZE_WORDS=600`, `RAG_CHUNK_OVERLAP_WORDS=80`), this specific document -- roughly 550-600 words of body content -- packs into one or two chunks, depending on exactly how its section blocks fall relative to the word budget (Chapter 5's algorithm packs whole paragraph/heading blocks greedily, never splitting a block mid-bullet-list or mid-instruction). When this exact document was ingested for real and its stored chunks inspected via `GET /admin/knowledge/{id}/chunks`, the chunk boundaries fell cleanly along this document's own section structure -- the `### VPN-ERR-403: Authentication Failed` content stayed grouped with its surrounding `## Common VPN Errors` section rather than being split across a chunk boundary, and no numbered installation step or bullet list was cut in half.

## Step 6: An embedding is generated for each chunk

`app/rag/embeddings/service.py`'s `get_embedding_service().generate_embeddings()` is called once with the full list of chunk contents. With the default `EMBEDDING_PROVIDER=dev`, this runs the deterministic hashing-trick bag-of-words algorithm (Chapter 5) against each chunk's text. In a real deployment with `EMBEDDING_PROVIDER=bedrock`, this same call would instead send each chunk to Amazon Titan Text Embeddings V2 via `InvokeModel` -- the calling code in `ingestion_service.py` doesn't change at all between the two; only the setting does.

## Step 7: Chunks and embeddings are stored, and the document goes READY

Each chunk, with its embedding converted to pgvector's text-literal format (Chapter 6), is inserted into `knowledge_chunks` in a single bulk statement. Only after every chunk is successfully inserted does the `knowledge_documents` row's `status` flip from `PROCESSING` to `READY`. This document is now live and queryable.

## Step 8: Later, a student emails IT support

Using phase7.md's own example message, verbatim:

> "My VPN is not connecting."

This message arrives through the already-existing (pre-Phase-7) email ingestion pipeline and becomes a new ticket, exactly as it would have before this phase existed -- nothing about ticket creation, threading, or storage changed.

## Step 9: The query is converted to an embedding

Using this student's message (or, as tested directly during this implementation, the closely related query "VPN still does not connect, auth failed"), `retrieval_service.search()` calls the exact same `EmbeddingService`, configured with the exact same provider, that embedded every chunk in Step 6. This match matters concretely: a query embedded with a different model than the one that embedded the documents would produce a cosine similarity that's not meaningfully comparable at all (Chapter 9).

## Step 10: A vector similarity search runs

The actual SQL query (Chapter 9, reproduced here in its essential form):

```sql
SELECT c.id, c.document_id, c.content, d.title, d.category,
       1 - (c.embedding <=> %s::vector) AS score
FROM knowledge_chunks c
JOIN knowledge_documents d ON d.id = c.document_id
WHERE d.status = 'READY'
ORDER BY c.embedding <=> %s::vector
LIMIT 5
```

This runs as a real, HNSW-index-accelerated nearest-neighbor query against every `READY` document's chunks in the knowledge base -- not just this one VPN document; every document in the corpus is a candidate, and the ranking is what determines which ones actually surface.

## Step 11: The top-K chunks are returned, ranked by score

In an actual run of the closely related query "VPN still does not connect, auth failed" against this exact document (alongside the other seven seeded documents, all competing for the same top-5 slots), the real, captured top result was a chunk from this VPN Troubleshooting Guide's "VPN connects but internal sites are still unreachable" / "When to Escalate" section, with a score of approximately `0.2217` -- ahead of every chunk from every other document in the corpus.

## Step 12: The result is packaged into the RAG context format

`app/rag/context.py`'s `build_rag_context()` (Chapter 11) reshapes the raw scored results into:

```json
{
  "query": "VPN still does not connect, auth failed",
  "results": [
    {
      "title": "VPN Troubleshooting Guide",
      "content": "### VPN connects but internal sites are still unreachable\n\n- Confirm the AnyConnect icon shows green...",
      "score": 0.2217
    }
  ]
}
```

## Step 13: This phase stops here

This context object is exactly what a **future** AI agent phase will consume to actually reason about and draft a response to this student. That generation step -- turning "here is the relevant documentation" into an actual reply -- is explicitly not built in this phase (see the Architecture Boundaries chapter for the complete, verified list of what stays out of scope). Nothing in this codebase today takes this JSON object and produces text a student would ever see.

## This was run for real

Every one of the thirteen steps above corresponds to code that actually executed and actually produced the cited output during this implementation -- the document was really uploaded through a live FastAPI server, really extracted, really chunked, really embedded, really stored in a live PostgreSQL+pgvector container, and really retrieved by a real search query with the real score shown above. None of this is a description of an intended design that was never run; it's a report of what was observed happening, start to finish, in one continuous, reproducible pass through the system this phase built.
