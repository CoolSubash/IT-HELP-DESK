"""
Local-development embedding provider. Selected by EMBEDDING_PROVIDER=dev,
the default (see app/config.py) -- this is what tests, the eval dataset
(app/rag/eval.py), and local `uvicorn` runs actually exercise; a real
Bedrock account isn't needed to develop or test any part of the RAG
pipeline. Mirrors app/email/dev_provider.py's role exactly: a provider
that needs no external credentials, chosen so the rest of the pipeline
can be exercised end to end.

Unlike DevEmailProvider (which only needs to *look* like a send
succeeded), a fake embedding that's genuinely random would make vector
search meaningless to test -- every retrieval test would either pass by
luck or need to mock the DB query itself, defeating the point of testing
against a real pgvector index. Instead this is a deterministic "hashing
trick" bag-of-words embedding: each lowercased word token is hashed
(SHA-256, not Python's `hash()` -- the latter is randomized per-process
via PYTHONHASHSEED unless disabled, which would make embeddings differ
between two runs of the same test suite) into one of `dimensions`
buckets, with a deterministic +1/-1 sign per token to reduce collision
bias, then the whole vector is L2-normalized. The result is a real (if
crude) bag-of-words vector: two texts sharing vocabulary end up with
higher cosine similarity, two texts sharing none end up near-orthogonal.
That's exactly the property retrieval tests need -- "a VPN query scores
VPN chunks higher than password-reset chunks" is genuinely true of these
vectors, not just asserted against a mock.

This is NOT a semantic embedding (no notion of synonyms, no understanding
that "can't connect" and "authentication failed" are related) -- it is a
stand-in for local development and testing only, the same way
DevEmailProvider's fabricated Message-ID is not a real one. Production
uses BedrockEmbeddingProvider (bedrock_provider.py).
"""
import hashlib
import math
import re

from app.config import settings
from app.rag.embeddings.provider import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class DevEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.embedding_dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _TOKEN_RE.findall(text.lower()) or ["__empty__"]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            vector[0] = 1.0
            norm = 1.0
        return [component / norm for component in vector]
