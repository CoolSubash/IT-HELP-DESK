"""
Where an uploaded knowledge-base file's original bytes live, independent
of the extracted-text/chunk/embedding pipeline. Same provider-swap shape
as app/email/provider.py + dev_provider.py + ses_provider.py: one
abstract interface, one zero-infrastructure "local" implementation kept
around purely so the test suite never needs real AWS credentials (see
tests/conftest.py), one AWS implementation that is the real default
(KNOWLEDGE_STORAGE_BACKEND=s3, see app/config.py).

knowledge_documents.storage_location (existing column, phase1.md) holds
whatever save() returns -- an absolute local path or an `s3://bucket/key`
URI -- so app/routers/knowledge.py and app/rag/ingestion_service.py never
need to know which backend produced it.

presign_upload_url() exists for a second, separate upload path
(POST /admin/knowledge/presign + PUT <url> + POST .../complete -- see
app/rag/ingestion_service.py's create_pending_upload()/
complete_pending_upload() and app/routers/knowledge.py) that lets a
browser upload the file bytes directly to S3, never through this API
process at all -- only S3FileStorage implements it; presigned URLs are
an S3-native concept with no local-disk equivalent, so LocalFileStorage
raises NotImplementedError with a clear message instead of faking one.
The original POST /admin/knowledge (multipart, file bytes go through
this process) still exists unchanged alongside this -- see that
endpoint's docstring for when each is the better choice.
"""
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings


class StorageNotConfiguredError(Exception):
    """Raised when the selected storage backend can't actually run --
    right now, only S3FileStorage without KNOWLEDGE_STORAGE_S3_BUCKET set
    (LocalFileStorage has no equivalent missing-config state; it just
    creates its directory). Mapped to HTTP 503 by app/main.py, not 500 --
    this is a known, checkable configuration gap, not an unexpected
    server error."""


class FileStorage(ABC):
    @abstractmethod
    def save(self, document_id: uuid.UUID, file_name: str, file_bytes: bytes) -> str:
        """Persists the file and returns its storage_location string."""
        raise NotImplementedError

    @abstractmethod
    def read(self, storage_location: str) -> bytes:
        """Round-trip of save() -- used by re-extraction/re-embedding
        tooling (docs/rag-manual's operational runbook) that needs the
        original file back, not just the already-extracted text."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_location: str) -> None:
        """Removes the underlying file. Called by
        app/rag/ingestion_service.py's delete_document() (hard delete
        only -- archive_document() never touches storage, see that
        function). Must be idempotent: deleting a storage_location that's
        already gone (a retried request, a location that was never
        actually written) is a no-op, not an error -- both
        implementations below rely on their backend's own delete already
        being idempotent (S3's DeleteObject) or make it so explicitly
        (Path.unlink(missing_ok=True))."""
        raise NotImplementedError

    def presign_upload_url(self, document_id: uuid.UUID, file_name: str, expires_in: int = 900) -> tuple[str, str]:
        """Returns (upload_url, storage_location) for a client to PUT the
        file's raw bytes to directly, bypassing this API process for the
        (potentially large) file transfer entirely. Not every backend can
        support this -- LocalFileStorage doesn't override it, so calling
        this against a "local" backend raises NotImplementedError; callers
        (app/rag/ingestion_service.py) let that propagate as a clear error
        rather than silently falling back to something else."""
        raise NotImplementedError(f"{type(self).__name__} does not support presigned uploads")


class LocalFileStorage(FileStorage):
    """Writes under settings.knowledge_storage_local_dir, relative to the
    backend/ working directory the app is run from. Filenames are
    prefixed with the document's UUID so two uploads named "guide.pdf"
    never collide (and so the file on disk is traceable back to its
    knowledge_documents row without opening the database)."""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.knowledge_storage_local_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document_id: uuid.UUID, file_name: str, file_bytes: bytes) -> str:
        safe_name = Path(file_name).name  # strips any directory components -- never trust a client-supplied path
        path = self.base_dir / f"{document_id}_{safe_name}"
        path.write_bytes(file_bytes)
        return str(path)

    def read(self, storage_location: str) -> bytes:
        return Path(storage_location).read_bytes()

    def delete(self, storage_location: str) -> None:
        Path(storage_location).unlink(missing_ok=True)


class S3FileStorage(FileStorage):
    """Uploaded with no public ACL (phase7.md #18: "S3 objects are
    private if S3 is used") -- the bucket itself is expected to have
    public access blocked at the bucket-policy level (see
    docs/rag-manual's AWS deployment chapter); this class additionally
    never passes an ACL that could override that, relying on the bucket
    default (private) instead of trusting per-object ACLs, which is the
    AWS-recommended posture since S3 started deprecating ACLs generally.
    """

    def __init__(self, bucket: str | None = None, region: str | None = None) -> None:
        self.bucket = bucket or settings.knowledge_storage_s3_bucket
        if not self.bucket:
            raise StorageNotConfiguredError(
                "KNOWLEDGE_STORAGE_BACKEND=s3 but KNOWLEDGE_STORAGE_S3_BUCKET is not set -- "
                "set it to a real bucket name (see .env.example and docs/rag-manual's AWS deployment chapter)"
            )
        self.region = region or settings.aws_region
        self._boto_client = None  # constructed lazily, cached -- see _client()

    def _client(self):
        if self._boto_client is None:
            import boto3  # imported lazily so "local" (the test default) never needs boto3 credentials resolved

            # Explicit credentials when this app's own settings.aws_access_key_id/
            # aws_secret_access_key are set (the normal case -- see .env.example):
            # boto3's own default credential chain checks environment variables,
            # then ~/.aws/credentials, then EC2/ECS instance metadata, BEFORE it
            # would ever consider this app's config -- on a machine that happens
            # to have its own `aws configure`'d profile (a developer's laptop, a
            # CI runner with an unrelated default profile), that chain silently
            # wins over whatever KNOWLEDGE_STORAGE_S3_BUCKET's credentials were
            # actually meant to be, signing requests as the wrong identity with
            # no error at all -- verified hitting exactly this during manual
            # testing: a presigned URL came back signed with an ambient
            # ~/.aws/credentials admin key instead of the scoped
            # KnowledgeBaseApiUser key this app was actually configured with.
            # Falling back to boto3's default chain only when neither is set
            # keeps this working for a real deployment using an IAM role
            # (ECS task role, EC2 instance profile -- see docs/rag-manual's AWS
            # deployment chapter), where there deliberately are no static keys
            # to put in settings at all.
            credentials_kwargs = {}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                credentials_kwargs = {
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                }
            # Explicit SigV4 -- verified necessary the hard way: without
            # this, botocore's default signer for us-east-1 produced a
            # legacy SigV2 presigned URL (recognizable by
            # ?AWSAccessKeyId=...&Signature=...&Expires=... in the query
            # string, instead of SigV4's ?X-Amz-Signature=...). SigV2's
            # signature is computed over a fixed Content-Type (empty,
            # here, since none was passed to generate_presigned_url), so
            # ANY client that sends a Content-Type header on the PUT --
            # which the browser upload path always does
            # (lib/api/knowledge.ts's uploadDocumentViaPresignedUrl) --
            # gets back 403 SignatureDoesNotMatch. This was caught by an
            # actual end-to-end PUT against the real bucket during
            # testing, not found by inspection. SigV4 presigned URLs
            # don't have this failure mode (Content-Type isn't part of
            # the signature unless explicitly added to SignedHeaders),
            # and are AWS's current recommended signature version anyway.
            from botocore.config import Config

            self._boto_client = boto3.client(
                "s3", region_name=self.region, config=Config(signature_version="s3v4"), **credentials_kwargs
            )
        return self._boto_client

    def _key_for(self, document_id: uuid.UUID, file_name: str) -> str:
        safe_name = Path(file_name).name  # strips any directory components -- never trust a client-supplied path
        return f"knowledge-documents/{document_id}/{safe_name}"

    def save(self, document_id: uuid.UUID, file_name: str, file_bytes: bytes) -> str:
        key = self._key_for(document_id, file_name)
        self._client().put_object(Bucket=self.bucket, Key=key, Body=file_bytes)
        return f"s3://{self.bucket}/{key}"

    def read(self, storage_location: str) -> bytes:
        assert storage_location.startswith("s3://")
        _, _, rest = storage_location.partition("s3://")
        bucket, _, key = rest.partition("/")
        response = self._client().get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def delete(self, storage_location: str) -> None:
        # S3's DeleteObject returns success whether or not the key
        # existed -- no existence check needed here to stay idempotent.
        assert storage_location.startswith("s3://")
        _, _, rest = storage_location.partition("s3://")
        bucket, _, key = rest.partition("/")
        self._client().delete_object(Bucket=bucket, Key=key)

    def presign_upload_url(self, document_id: uuid.UUID, file_name: str, expires_in: int = 900) -> tuple[str, str]:
        """A presigned PUT URL: a normal S3 object PUT, but the
        credentials proving "this caller may write this exact key" are
        embedded in the URL's query string (signed with this server's own
        AWS credentials) instead of requiring the browser to have any AWS
        credentials of its own. Valid for `expires_in` seconds (default
        15 minutes -- long enough for a large PDF on a slow connection,
        short enough that a leaked/logged URL doesn't stay exploitable
        indefinitely). No ACL is requested here either, for the same
        reason save() doesn't request one -- see this class's docstring.
        """
        key = self._key_for(document_id, file_name)
        url = self._client().generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url, f"s3://{self.bucket}/{key}"


def get_storage_backend() -> FileStorage:
    if settings.knowledge_storage_backend == "s3":
        return S3FileStorage()
    return LocalFileStorage()
