"""
Tests for the presigned-upload path (app/rag/ingestion_service.py's
create_pending_upload()/complete_pending_upload(), app/routers/knowledge.py's
POST /admin/knowledge/presign + POST /admin/knowledge/{id}/complete).

There is no real S3 bucket available in this environment (or in CI), so
these tests patch S3FileStorage's boto3 client with an in-memory fake
that implements exactly the three calls this code path makes
(generate_presigned_url, put_object, get_object) -- everything else
(the document-row lifecycle, versioning, duplicate-title checks, the
SAVEPOINT-protected pipeline, idempotency) is the real, unmocked
application code. This deliberately does not test that a real HTTP PUT
to a real presigned URL works -- that's a property of AWS's S3
implementation, not this codebase's, and isn't something a unit/
integration test in this repo can verify without live AWS credentials
(see docs/rag-manual's AWS deployment chapter).
"""
import uuid

import pytest

from app.errors import ConflictError, NotFoundError, ValidationError
from app.rag import ingestion_service
from app.rag.storage import FileStorage, S3FileStorage


class FakeS3Client:
    """Enough of boto3's S3 client surface for presign_upload_url()/
    save()/read() to run against, backed by a plain dict instead of a
    network call."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):  # noqa: N803 -- matches boto3's real signature
        assert ClientMethod == "put_object"
        return f"https://fake-s3.test/{Params['Bucket']}/{Params['Key']}?X-Fake-Signature=1&expires={ExpiresIn}"

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[f"{Bucket}/{Key}"] = Body if isinstance(Body, bytes) else Body.encode()

    def get_object(self, Bucket, Key):  # noqa: N803
        key = f"{Bucket}/{Key}"
        if key not in self.objects:
            raise KeyError(f"no such key: {key}")  # stands in for botocore's NoSuchKey
        return {"Body": _FakeBody(self.objects[key])}

    def delete_object(self, Bucket, Key):  # noqa: N803
        # Real S3 DeleteObject is idempotent -- succeeds whether or not
        # the key existed. .pop(..., None) mirrors that: no KeyError for
        # a key that's already gone.
        self.objects.pop(f"{Bucket}/{Key}", None)


class _FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


@pytest.fixture()
def fake_s3_storage(monkeypatch) -> tuple[S3FileStorage, FakeS3Client]:
    storage = S3FileStorage(bucket="test-bucket", region="us-east-1")
    fake_client = FakeS3Client()
    storage._boto_client = fake_client  # bypass the lazy boto3.client(...) construction entirely
    monkeypatch.setattr(ingestion_service, "get_storage_backend", lambda: storage)
    return storage, fake_client


def _simulate_browser_put(fake_client: FakeS3Client, storage_location: str, file_bytes: bytes) -> None:
    """What the browser's direct PUT to the presigned URL does, minus the
    actual HTTP hop -- writes the bytes into the fake bucket at the same
    key presign_upload_url() already committed to in storage_location."""
    assert storage_location.startswith("s3://")
    _, _, rest = storage_location.partition("s3://")
    bucket, _, key = rest.partition("/")
    fake_client.put_object(Bucket=bucket, Key=key, Body=file_bytes)


def test_presign_returns_a_url_and_a_processing_document(db, fake_s3_storage):
    document, upload_url = ingestion_service.create_pending_upload(
        db, title="Presigned Doc", description=None, category="OTHER",
        file_name="guide.txt", file_type="txt",
    )
    assert document["status"] == "PROCESSING"
    assert upload_url.startswith("https://fake-s3.test/test-bucket/knowledge-documents/")
    assert document["storage_location"] == f"s3://test-bucket/knowledge-documents/{document['id']}/guide.txt"


def test_full_presign_then_complete_flow_reaches_ready(db, fake_s3_storage):
    _, fake_client = fake_s3_storage
    document, _ = ingestion_service.create_pending_upload(
        db, title="Presigned Complete Doc", description=None, category="OTHER",
        file_name="guide.txt", file_type="txt",
    )
    _simulate_browser_put(fake_client, document["storage_location"], b"Restart the VPN client and try again.")

    completed = ingestion_service.complete_pending_upload(db, document["id"])
    assert completed["status"] == "READY"

    chunks, total = ingestion_service.list_chunks(db, document["id"], limit=20, offset=0)
    assert total == 1
    assert "VPN client" in chunks[0]["content"]


def test_complete_before_the_file_arrives_lands_failed_not_500(db, fake_s3_storage):
    document, _ = ingestion_service.create_pending_upload(
        db, title="Never Uploaded Doc", description=None, category=None,
        file_name="guide.txt", file_type="txt",
    )
    # Deliberately skip _simulate_browser_put -- the object never lands in the fake bucket.
    completed = ingestion_service.complete_pending_upload(db, document["id"])
    assert completed["status"] == "FAILED"
    assert "storage" in completed["error_message"].lower()


def test_complete_is_idempotent_for_an_already_ready_document(db, fake_s3_storage):
    _, fake_client = fake_s3_storage
    document, _ = ingestion_service.create_pending_upload(
        db, title="Idempotent Doc", description=None, category=None,
        file_name="guide.txt", file_type="txt",
    )
    _simulate_browser_put(fake_client, document["storage_location"], b"some content for this document")
    first = ingestion_service.complete_pending_upload(db, document["id"])
    assert first["status"] == "READY"

    # Calling complete() again must not reprocess (which would insert a
    # second set of chunks with colliding chunk_index values) -- it
    # should just return the already-READY document as-is.
    second = ingestion_service.complete_pending_upload(db, document["id"])
    assert second["status"] == "READY"
    assert second["id"] == first["id"]

    _, total = ingestion_service.list_chunks(db, document["id"], limit=20, offset=0)
    assert total == 1


def test_presign_unsupported_file_type_raises_before_any_row_created(db, fake_s3_storage):
    with pytest.raises(ValidationError):
        ingestion_service.create_pending_upload(
            db, title="Bad Type", description=None, category=None,
            file_name="malware.exe", file_type="exe",
        )
    _, total = ingestion_service.list_documents(db, limit=20, offset=0, search="Bad Type")
    assert total == 0


def test_presign_duplicate_title_without_replace_raises_conflict(db, fake_s3_storage):
    _, fake_client = fake_s3_storage
    document, _ = ingestion_service.create_pending_upload(
        db, title="Presign Duplicate Doc", description=None, category=None,
        file_name="a.txt", file_type="txt",
    )
    _simulate_browser_put(fake_client, document["storage_location"], b"first version content")
    ingestion_service.complete_pending_upload(db, document["id"])

    with pytest.raises(ConflictError):
        ingestion_service.create_pending_upload(
            db, title="Presign Duplicate Doc", description=None, category=None,
            file_name="b.txt", file_type="txt",
        )


def test_presign_with_replace_document_id_versions_and_archives_original(db, fake_s3_storage):
    _, fake_client = fake_s3_storage
    original, _ = ingestion_service.create_pending_upload(
        db, title="Presign Versioned Doc", description=None, category=None,
        file_name="v1.txt", file_type="txt",
    )
    _simulate_browser_put(fake_client, original["storage_location"], b"version one content")
    ingestion_service.complete_pending_upload(db, original["id"])

    new_version, _ = ingestion_service.create_pending_upload(
        db, title="Presign Versioned Doc", description=None, category=None,
        file_name="v2.txt", file_type="txt", replace_document_id=original["id"],
    )
    assert new_version["version"] == 2
    assert new_version["previous_version_id"] == original["id"]

    _simulate_browser_put(fake_client, new_version["storage_location"], b"version two content")
    completed = ingestion_service.complete_pending_upload(db, new_version["id"])
    assert completed["status"] == "READY"

    archived_original = ingestion_service.get_document(db, original["id"])
    assert archived_original["status"] == "ARCHIVED"


def test_presign_replace_document_id_for_missing_document_raises_not_found(db, fake_s3_storage):
    with pytest.raises(NotFoundError):
        ingestion_service.create_pending_upload(
            db, title="Anything", description=None, category=None,
            file_name="a.txt", file_type="txt", replace_document_id=uuid.uuid4(),
        )


def test_hard_delete_removes_the_s3_object_too(db, fake_s3_storage):
    """Regression test for the gap this stack's IAM policy used to have
    (no s3:DeleteObject) -- hard delete must remove the object from S3,
    not just the database row. See ingestion_service.delete_document()'s
    docstring."""
    _, fake_client = fake_s3_storage
    document, _ = ingestion_service.create_pending_upload(
        db, title="S3 Delete Test Doc", description=None, category=None,
        file_name="guide.txt", file_type="txt",
    )
    _simulate_browser_put(fake_client, document["storage_location"], b"some content")
    ingestion_service.complete_pending_upload(db, document["id"])

    bucket_key = document["storage_location"].removeprefix("s3://")
    assert bucket_key in fake_client.objects  # sanity check: the fake bucket really has it

    ingestion_service.delete_document(db, document["id"])

    assert bucket_key not in fake_client.objects


def test_local_storage_does_not_support_presigned_uploads(db):
    """The other half of the presign/local split -- LocalFileStorage
    (what tests otherwise use for every other ingestion test in this
    suite) deliberately has no presigned-URL concept. Confirms
    create_pending_upload() lets that NotImplementedError propagate
    rather than silently doing something else."""
    with pytest.raises(NotImplementedError):
        ingestion_service.create_pending_upload(
            db, title="Local Presign Attempt", description=None, category=None,
            file_name="a.txt", file_type="txt",
        )
