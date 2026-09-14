"""
The abstraction phase7.md #6 explicitly asks for: "design the embedding
service so the provider can be changed later without rewriting the whole
application." Mirrors app/email/provider.py's EmailProvider shape exactly
-- ingestion_service.py and retrieval_service.py depend only on this
interface (via EmbeddingService, see service.py), never on
DevEmbeddingProvider or BedrockEmbeddingProvider directly.
"""
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    dimensions: int

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embeds one piece of text. Must raise EmbeddingError if the
        provider fails or rejects the input -- never return a zero vector
        or partial result silently (phase7.md #19: "Embedding API
        failure" is a named error case ingestion_service.py must catch and
        turn into a FAILED document, not a corrupt-but-"successful" one)."""
        raise NotImplementedError

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Default implementation just calls embed_text() per item --
        correct for any provider, but a provider whose API genuinely
        supports batched requests (lower latency, fewer calls) can
        override this for one. Bedrock's Titan Text Embeddings model does
        not support batching a single invoke_model call as of this
        writing, so BedrockEmbeddingProvider doesn't override this."""
        return [self.embed_text(text) for text in texts]


class EmbeddingError(Exception):
    """Raised by an EmbeddingProvider when embedding fails -- network
    error, API throttling, malformed response. Caught by
    app/rag/ingestion_service.py, which stops the pipeline for that
    document and records the failure (see that module's docstring)."""
