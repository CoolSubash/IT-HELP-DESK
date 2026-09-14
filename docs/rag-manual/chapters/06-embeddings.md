# Embeddings

## The requirement: swappable, not hardcoded

phase7.md section 6 states the requirement precisely: *"Design the embedding service so that the provider can be changed later without rewriting the whole application... Do not hard-code embedding logic throughout the application."* The sketch it gives is minimal on purpose:

```text
EmbeddingService
      |
generate_embedding(text)
```

This implementation follows that sketch exactly, and follows an abstraction pattern that already existed elsewhere in this codebase for the identical problem: `app/email/provider.py`'s `EmailProvider` abstract base class, with `DevEmailProvider` and `AWSSESProvider` as swappable concrete implementations selected by a single setting (`EMAIL_PROVIDER`). The embeddings subsystem (`backend/app/rag/embeddings/`) mirrors that shape file-for-file:

```text
embeddings/
  provider.py          EmbeddingProvider (abstract base class) + EmbeddingError
  dev_provider.py       DevEmbeddingProvider -- local development, no credentials
  bedrock_provider.py    BedrockEmbeddingProvider -- production, Amazon Titan
  service.py              EmbeddingService + get_embedding_service()
```

Nothing outside this package -- not `ingestion_service.py`, not `retrieval_service.py` -- ever imports `DevEmbeddingProvider` or `BedrockEmbeddingProvider` directly. Every caller goes through `get_embedding_service()`, which reads a single setting (`EMBEDDING_PROVIDER`, `"dev"` or `"bedrock"`) and returns the matching concrete provider wrapped in an `EmbeddingService`. Adding a third provider later -- OpenAI's embeddings API, for instance -- means writing one new file and adding one branch to this one function. It does not mean touching the ingestion pipeline, the retrieval query, or any test that doesn't specifically test the embedding provider itself.

## The interface

```python
class EmbeddingProvider(ABC):
    dimensions: int

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]  # default; a provider may override
```

`embed_text()` must raise `EmbeddingError` on failure -- never return a zero vector, never return a partial or truncated result silently. This matters because phase7.md section 19 explicitly lists "Embedding API failure" as a named error case the ingestion pipeline must handle, and it can only handle it correctly if a failure is unambiguous (an exception) rather than something the pipeline would have to guess at (a suspiciously-all-zero vector that embedded successfully as far as the type system is concerned). `embed_batch()` has a default implementation that just calls `embed_text()` once per item -- correct for any provider, and overridable by a provider whose underlying API genuinely supports a real batch request for lower latency. Amazon Bedrock's Titan Text Embeddings model, as used here, does not support batching multiple inputs into a single `InvokeModel` call, so `BedrockEmbeddingProvider` doesn't override the default.

## `DevEmbeddingProvider`: the local development provider, and why it's more than a stub

Selected by `EMBEDDING_PROVIDER=dev`, which is the project's default -- this is what every test, the evaluation harness, and a plain local `uvicorn` run actually exercises. No AWS credentials are needed to develop, test, or demo any part of this phase.

The easy version of a "dev" embedding provider would just return a random vector. That would be enough to make the *types* line up and the pipeline run without crashing, but it would make vector search itself untestable in any meaningful way -- every retrieval test would either pass by pure luck or would have to mock the database query directly, which defeats the entire point of testing against a real `pgvector` index. Instead, `DevEmbeddingProvider` implements a real, if crude, embedding algorithm: a deterministic **hashing-trick bag-of-words** embedding.

The algorithm, concretely:

1. Lowercase the input text and split it into word tokens (a simple `[a-z0-9]+` regex).
2. For each token, compute its SHA-256 hash (deliberately *not* Python's built-in `hash()` function -- that's randomized per-process via `PYTHONHASHSEED` unless explicitly disabled, which would make the same text produce a *different* embedding on two separate runs of the same test suite; SHA-256 is stable across processes and machines).
3. Use the first 4 bytes of that hash, modulo the target dimension count, to pick one of `dimensions` "buckets" for that token.
4. Use one more byte of the same hash to decide a deterministic +1 or -1 sign, added into that bucket (the sign reduces a systematic bias that a pure "always +1" hashing scheme would otherwise introduce).
5. After every token has been added into its bucket, L2-normalize the resulting vector to unit length.

The result is a genuine bag-of-words vector: two pieces of text that share vocabulary end up with a demonstrably higher cosine similarity than two pieces of text that share none. That property -- not randomness, not a mock -- is what lets `tests/test_rag_embeddings.py` assert, and actually verify, that "VPN authentication failed" scores closer to "VPN authentication failure and connection troubleshooting steps" than to "printer paper jam and toner replacement instructions." It's also what makes the retrieval evaluation numbers in Chapter 15 real numbers about a real (if simple) retrieval mechanism, not numbers about a mock.

To be direct about the limitation, because this manual does not overstate what this provider does: `DevEmbeddingProvider` has no notion of synonyms, no understanding that "can't connect" and "authentication failed" are related concepts unless they happen to share literal vocabulary. It is not a semantic embedding. It is a deliberate, honestly-labeled stand-in for local development and testing, in exactly the same spirit as `DevEmailProvider`'s fabricated `Message-ID` is not a real one -- good enough to prove the *pipeline* works correctly end to end, not a claim about production retrieval quality.

## `BedrockEmbeddingProvider`: the production provider

Selected by `EMBEDDING_PROVIDER=bedrock`. Calls Amazon Bedrock's `InvokeModel` API against `amazon.titan-embed-text-v2:0` (configurable via `BEDROCK_EMBEDDING_MODEL_ID`), using `boto3`'s `bedrock-runtime` client -- `boto3` is already a project dependency (used by the existing SES email integration from an earlier phase), so this adds no new AWS SDK, only a new service client.

The request body sent to Bedrock:

```json
{
  "inputText": "the chunk or query text",
  "dimensions": 1024,
  "normalize": true
}
```

`dimensions: 1024` matches the `vector(1024)` column defined in the schema (Chapter 4) -- Titan Text Embeddings V2 supports 256, 512, or 1024-dimension output, and this project uses the largest of the three. `normalize: true` asks Bedrock to return an already unit-length vector, which matters for a specific, concrete reason: with normalized vectors, cosine similarity and a plain dot product become mathematically equivalent, which avoids an entire class of scoring bugs where an un-normalized embedding could be gamed simply by being "longer text -> larger vector magnitude -> higher raw dot-product score" regardless of actual relevance. Requesting normalization from Bedrock directly, rather than normalizing client-side after the fact, means this guarantee holds even if the raw API response is ever consumed in some other context later.

Any failure from the Bedrock call -- a throttling exception, a network error, a malformed response missing the expected `embedding` field -- is caught and re-raised as a single `EmbeddingError`, deliberately collapsing botocore's many distinct exception types into one the rest of the pipeline only has to know how to handle once. `boto3`'s client construction is deferred (imported lazily inside the class, not at module import time), so importing this module -- which happens automatically whenever `EMBEDDING_PROVIDER=dev` is selected, since `service.py` imports both provider modules at startup -- never requires AWS credentials to be configured at all when Bedrock isn't the active provider.

## `EmbeddingService`: the thin wrapper everything actually calls

```python
class EmbeddingService:
    def generate_embedding(self, text: str) -> list[float]: ...
    def generate_embeddings(self, texts: list[str]) -> list[list[float]]: ...

def get_embedding_service() -> EmbeddingService:
    if settings.embedding_provider == "bedrock":
        from app.rag.embeddings.bedrock_provider import BedrockEmbeddingProvider
        return EmbeddingService(BedrockEmbeddingProvider())
    return EmbeddingService(DevEmbeddingProvider())
```

This is the entire surface area `ingestion_service.py` and `retrieval_service.py` interact with -- `generate_embedding()` for a single query string during retrieval, `generate_embeddings()` for a batch of chunk contents during ingestion. Exactly the shape phase7.md section 6 asked for, and exactly the mechanism that makes the provider swap a one-line environment variable change rather than a code change.

## What this is tested against

`tests/test_rag_embeddings.py` (6 tests) verifies, directly against `DevEmbeddingProvider`: determinism (embedding the same text twice produces an identical vector -- proving no hidden randomness leaks in); that the output has exactly the requested dimension count; that the output is genuinely unit-length (L2 norm within floating-point tolerance of 1.0); that `embed_batch()` produces results identical to calling `embed_text()` once per item; that even empty-string input still produces a valid unit vector rather than crashing or dividing by zero; and, most importantly, that semantically similar text scores a measurably higher cosine similarity than dissimilar text -- the one property that makes this provider a genuine, testable stand-in rather than noise dressed up as an embedding.
