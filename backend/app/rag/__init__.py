"""
Phase 7 (claudeprompt/phase7.md): RAG knowledge base and retrieval.

Everything in this package is about ONE thing -- "what does the IT
department's documentation say" -- and deliberately knows nothing about
tickets, users, or messages. See docs/rag-manual/ for the full design
writeup; the short version (phase7.md #22):

    PostgreSQL      = application state + ticket history
    Knowledge Base   = official IT documentation
    RAG (this package) = find relevant knowledge
    Future AI Agent  = reason + decide + use tools + respond (NOT built yet)

Module map:
    extraction.py         PDF/TXT/MD/DOCX -> plain text
    chunking.py            plain text -> list[Chunk]
    storage.py              raw uploaded file bytes -> local disk or S3
    embeddings/              text -> vector, behind a swappable provider
    ingestion_service.py    orchestrates all of the above end to end
    retrieval_service.py    query -> top-K relevant chunks (vector search)
    context.py               top-K chunks -> the JSON shape a future AI
                              agent will consume (phase7.md #16)
    eval.py                   retrieval quality measurement (Recall@K/
                              Precision@K) against a small labeled dataset
"""
