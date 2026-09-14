"""
EmbeddingService -- the one thing the rest of app/rag/ (and, later, the AI
agent) actually imports. Exactly the shape phase7.md #6 sketches:

    EmbeddingService
          |
    generate_embedding(text)

get_embedding_service() mirrors app/email/service.py's get_email_provider():
a single function that reads settings.embedding_provider and returns the
matching concrete provider, wrapped in EmbeddingService. Nothing in
ingestion_service.py or retrieval_service.py imports DevEmbeddingProvider
or BedrockEmbeddingProvider directly -- changing providers later, or
adding a third one, never requires touching either of those files (only
this function).
"""
from app.config import settings
from app.rag.embeddings.dev_provider import DevEmbeddingProvider
from app.rag.embeddings.provider import EmbeddingProvider


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self.dimensions = provider.dimensions

    def generate_embedding(self, text: str) -> list[float]:
        return self._provider.embed_text(text)

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_batch(texts)


def get_embedding_service() -> EmbeddingService:
    if settings.embedding_provider == "bedrock":
        # Imported lazily so boto3's bedrock-runtime client construction
        # only happens when Bedrock is actually selected -- same reasoning
        # as app/email/service.py's lazy import of AWSSESProvider.
        from app.rag.embeddings.bedrock_provider import BedrockEmbeddingProvider

        return EmbeddingService(BedrockEmbeddingProvider())
    return EmbeddingService(DevEmbeddingProvider())
