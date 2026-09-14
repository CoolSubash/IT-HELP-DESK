"""
Production embedding provider: Amazon Titan Text Embeddings V2 through
Bedrock's InvokeModel API. Selected by EMBEDDING_PROVIDER=bedrock.

Chosen per phase7.md #6 ("prefer an AWS-native approach... we are already
using AWS services and Amazon Bedrock elsewhere in the project" -- see
infra/lambda/email_ingestion and docs/05-tech-stack.md, which already
named Bedrock/Titan as the intended embedding path before this phase
existed). `boto3` is already a dependency (used for SES); this adds no
new AWS SDK, only a new service client.

Titan Text Embeddings V2 supports 256/512/1024-dimension output; this
project uses 1024 (settings.embedding_dimensions), matching the `vector(1024)`
column in migrations/0006_knowledge_chunks_and_vector.sql. `normalize:
true` asks Bedrock to return a unit-length vector, so cosine similarity
and dot-product scoring are equivalent -- retrieval_service.py's `<=>`
(cosine distance) works correctly either way, but requesting normalized
vectors avoids a class of scoring bugs where an un-normalized dot product
would be gameable by a document that's simply "longer text -> larger
vector magnitude."
"""
import json

from app.config import settings
from app.rag.embeddings.provider import EmbeddingError, EmbeddingProvider


class BedrockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_id: str | None = None, region: str | None = None, dimensions: int | None = None) -> None:
        self.model_id = model_id or settings.bedrock_embedding_model_id
        self.region = region or settings.aws_region
        self.dimensions = dimensions or settings.embedding_dimensions
        self._client = None  # lazily constructed -- see _get_client()

    def _get_client(self):
        if self._client is None:
            import boto3  # imported lazily so importing this module never requires boto3 credentials to be configured

            # Explicit credentials when configured, rather than trusting
            # boto3's default chain (which checks ~/.aws/credentials before
            # this app's own settings) -- see app/rag/storage.py's
            # S3FileStorage._client() for the concrete bug this avoids;
            # same fix, same reasoning, applied here too.
            credentials_kwargs = {}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                credentials_kwargs = {
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                }
            self._client = boto3.client("bedrock-runtime", region_name=self.region, **credentials_kwargs)
        return self._client

    def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise EmbeddingError("cannot embed empty text")

        try:
            response = self._get_client().invoke_model(
                modelId=self.model_id,
                body=json.dumps(
                    {
                        "inputText": text,
                        "dimensions": self.dimensions,
                        "normalize": True,
                    }
                ),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(response["body"].read())
        except Exception as exc:  # noqa: BLE001 -- botocore raises many
            # distinct exception classes (ClientError, EndpointConnectionError,
            # ThrottlingException, ...); ingestion_service.py only needs to
            # know "the embedding call failed," not which of Bedrock's many
            # failure modes it was, so all of them collapse to one type here.
            raise EmbeddingError(f"Bedrock embedding request failed: {exc}") from exc

        embedding = payload.get("embedding")
        if not embedding:
            raise EmbeddingError(f"Bedrock response did not include an embedding: {payload}")
        return embedding
