"""
Application configuration, loaded from environment variables.

We use pydantic-settings so configuration is validated at startup -- if
DATABASE_URL is missing or malformed, the app fails immediately with a clear
error instead of failing later with a confusing error deep inside SQLAlchemy.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    environment: str = "development"

    # Comma-separated list of origins the dashboard is served from --
    # see app/main.py's CORSMiddleware. Defaults cover local `next dev`
    # (3001 included because it silently falls back there when 3000 is
    # taken). infra/cdk/stacks/compute_stack.py sets this to the
    # deployed frontend's ALB DNS name (or custom domain) in production.
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    # --- Email (Phase 4) ---
    # "dev" (default) logs emails instead of sending them -- see
    # app/email/dev_provider.py -- so the whole inbound/outbound loop can
    # be exercised without real AWS credentials. Set to "ses" in any
    # environment that should actually deliver email.
    email_provider: str = "dev"
    it_support_email: str = "it-support@university.edu"
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # POST /email/inbound has no real caller identity to check (no SES/SNS
    # signature verification is wired up in this project) -- in dev mode it
    # accepts requests unconditionally; everywhere else it requires
    # `email_webhook_secret` to be sent back as a header (see
    # app/routers/email.py). This is a stand-in for real SNS message
    # signature verification, not a replacement for it in production.
    email_webhook_dev_mode: bool = True
    email_webhook_secret: str | None = None

    # --- RAG / knowledge base (Phase 7, claudeprompt/phase7.md) ---
    # "dev" (default) generates deterministic hashing-trick embeddings
    # locally -- see app/rag/embeddings/dev_provider.py -- so ingestion,
    # chunking, and vector search can all be exercised (and actually
    # produce meaningful similarity scores, not just random ones) without
    # AWS credentials. Set to "bedrock" to call Amazon Titan Text
    # Embeddings through Bedrock -- see app/rag/embeddings/bedrock_provider.py.
    embedding_provider: str = "dev"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    # Must match the `vector(N)` dimension hardcoded in
    # migrations/0006_knowledge_chunks_and_vector.sql -- see that file's
    # comment for why changing this after data exists is a migration, not
    # a config change.
    embedding_dimensions: int = 1024

    # Chunking (app/rag/chunking.py). Counted in words, not real
    # tokenizer tokens -- see that module's docstring for why, and for the
    # word-to-token conversion this project assumes. phase7.md #5
    # explicitly asks these to be configurable rather than hardcoded, since
    # the "500-1000 tokens / 50-150 overlap" starting point is not claimed
    # to be optimal.
    rag_chunk_size_words: int = 600
    rag_chunk_overlap_words: int = 80

    rag_default_top_k: int = 5

    # Where an uploaded knowledge-base file's original bytes are kept.
    # "s3" (default) uploads to knowledge_storage_s3_bucket (private, no
    # public access -- phase7.md #18) -- this is the real, intended
    # deployment target. "local" writes under knowledge_storage_local_dir
    # on the API server's own disk instead; it still exists (and still
    # implements the same FileStorage interface -- see app/rag/storage.py)
    # purely so the test suite can upload documents without needing real
    # AWS credentials -- tests/conftest.py forces it on for every test,
    # regardless of this default. Running the app for real with the
    # default "s3" and no knowledge_storage_s3_bucket configured will
    # raise a clear StorageNotConfiguredError (-> HTTP 503) on the first
    # upload attempt -- see app/rag/storage.py's get_storage_backend().
    knowledge_storage_backend: str = "s3"
    knowledge_storage_local_dir: str = "storage/knowledge_documents"
    knowledge_storage_s3_bucket: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
