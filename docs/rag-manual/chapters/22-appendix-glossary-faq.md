# Appendix C: Glossary and FAQ

## Glossary

**Bedrock.** Amazon's managed foundation-model service. Used in this phase only for embeddings (Titan Text Embeddings V2), never for text generation.

**Chunk.** One piece of a document, sized to represent one coherent idea, stored as a `knowledge_chunks` row with its own embedding. See Chapter 5.

**Chunking.** The process of splitting a document's text into chunks before embedding, preserving paragraph/heading/bullet boundaries. See Chapter 5.

**Cosine Distance.** `1 - cosine similarity`; what pgvector's `<=>` operator computes. Smaller means more relevant. See Chapter 6.

**Cosine Similarity.** A measure of the angle between two vectors, ignoring magnitude; ranges from -1 to 1. See Chapter 6.

**Document Versioning.** Re-uploading a document under the same title with `replace_document_id` creates a new version and archives the old one only after the new one succeeds. See Chapter 8.

**Embedding.** A fixed-length numeric vector representing a piece of text's meaning, produced by an embedding model.

**Embedding Provider.** The swappable component that turns text into an embedding -- `DevEmbeddingProvider` or `BedrockEmbeddingProvider` in this project. See Chapter 5.

**Hashing Trick (bag-of-words embedding).** The algorithm behind `DevEmbeddingProvider`: hash each word into one of N buckets with a deterministic sign, then normalize. A genuine, testable, non-semantic stand-in embedding. See Chapter 5.

**HNSW.** Hierarchical Navigable Small World -- the graph-based approximate-nearest-neighbor index type used on `knowledge_chunks.embedding`. Chosen over IVFFlat for this project's scale. See Chapter 6.

**Hybrid Search.** Combining keyword/full-text search with vector search. Not built in this phase; see Chapter 11.

**Ingestion Pipeline.** The full upload-to-searchable flow: store, extract, clean, chunk, embed, store. See Chapter 8.

**IVFFlat.** The other pgvector index type; requires a training step against existing data, making it a poor fit for this project's near-empty-at-creation table. See Chapter 6.

**Knowledge Chunk.** A `knowledge_chunks` row: one chunk's text, position, token count, and embedding.

**Knowledge Document.** A `knowledge_documents` row: metadata for one uploaded piece of IT documentation.

**Metadata Filtering.** Restricting a search to documents matching a metadata value -- `category`, in this implementation. See Chapter 9.

**Precision@K.** Of the K results returned, the fraction belonging to the expected document. See Chapter 16.

**RAG (Retrieval-Augmented Generation).** An architecture pattern where relevant documents are retrieved and handed to a language model as context, rather than relying on the model's own memorized knowledge. This phase builds only the "Retrieval" half.

**RAG Context.** The clean `{query, results: [{title, content, score}]}` JSON shape produced by `build_rag_context()`, meant for a future AI agent to consume. See Chapter 11.

**Recall@K.** Whether the expected document appears anywhere in the top K results (0 or 1, given one relevant document per question). See Chapter 16.

**Savepoint.** A Postgres transaction marker allowing a partial rollback (`ROLLBACK TO SAVEPOINT`) without discarding the whole transaction. Used in `ingestion_service.py` so a failure mid-pipeline can be recorded without corrupting the surrounding transaction. See Chapter 8.

**Titan Text Embeddings.** Amazon's embedding model family, accessed via Bedrock. This project uses V2 at 1024 dimensions.

**Top-K.** The K highest-scoring results returned by a search.

**Vector.** A fixed-length list of numbers; here, always 1024 floats representing one chunk's or one query's embedding.

**Vector Similarity Search.** Finding the chunks whose embeddings are closest to a query's embedding, via pgvector's `<=>` operator and an HNSW index. See Chapter 9.

## FAQ

**Why doesn't retrieval understand synonyms if `EMBEDDING_PROVIDER=dev`?** Because the dev provider is a word-overlap hashing-trick embedding (Chapter 5), not a semantic one -- it has no notion that "can't connect" and "authentication failed" are related unless they share literal vocabulary. `EMBEDDING_PROVIDER=bedrock` uses a genuinely semantic model instead.

**What happens if I upload the same document twice by accident?** The second upload is rejected with `409 Conflict` unless `replace_document_id` is explicitly given. See Chapter 13.

**Can I change the chunk size without losing existing data?** Yes -- `RAG_CHUNK_SIZE_WORDS`/`RAG_CHUNK_OVERLAP_WORDS` only affect future ingestions. Existing chunks stay as they are until their document is re-ingested as a new version.

**What happens to a document's chunks when I archive it?** They remain in the database, excluded from search, not deleted. There is no endpoint to un-archive a document -- see the next question for why.

**Why is there no endpoint to re-activate an archived document?** phase7.md doesn't ask for one, and re-activating an old version while a newer version is `READY` would conflict with the "one `READY` document per title" invariant the duplicate-title check enforces (Chapter 8) -- doing this correctly needs explicit design work this phase didn't scope in.

**Does deleting a document delete its file from disk or S3?** No. `DELETE ?hard=true` removes the database row and cascades to its chunks, but does not delete the underlying stored file. This is a real, honest current limitation, not a hidden bug -- a natural follow-up improvement, not built here because it wasn't asked for.

**How do I know if my Bedrock IAM permissions are set up correctly?** Switch `EMBEDDING_PROVIDER=bedrock` and attempt any ingestion. A permissions problem surfaces as an `EmbeddingError` wrapping the underlying `botocore` access-denied exception, landing the document as `FAILED` with that detail in `error_message` -- not a silent failure or a generic crash. See Chapter 13.

**Is the `X-Admin-Id` admin check safe to expose to the public internet?** No -- explicitly not. See Chapter 12. It's a development-phase stand-in, and this API should sit behind a private network or real authentication before any public exposure.

**Why exactly 8 example documents?** They're phase7.md's own example document list -- enough to meaningfully exercise chunking, embedding, retrieval, and evaluation across genuinely distinct topics, without requiring a large synthetic corpus that wouldn't add real signal to the evaluation.

**How would I add a 9th knowledge document to the seed set?** Add a new `.md` file under `seed/knowledge_docs/`, add an entry to `DOCUMENTS` in `seed_knowledge_base.py` with its title/category, optionally add a labeled question to `EVAL_DATASET` in `app/rag/eval.py`, and re-run the seed script.

**Does this system currently generate any AI response to a student?** No -- explicitly not. This phase stops at retrieval. See Chapter 18 (Architecture Boundaries).

**What's the very next phase likely to build?** An AI agent that combines this phase's retrieved knowledge with ticket history and the student's current message to actually reason and respond. Not built or designed in detail here -- only the interface (`retrieval_service.search()`, `build_rag_context()`) this phase hands it. See Chapter 18.
