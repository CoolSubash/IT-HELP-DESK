"""
HTTP-level tests for app/routers/knowledge.py, via the real FastAPI app
(app/database.py's connection pool, not the `db` fixture) -- same pattern
as tests/test_tickets_api.py. Covers phase7.md #20's "Admin
authorization: Non-admin users must not manage the knowledge base" and
exercises the full request/response cycle (multipart upload, pagination
envelope, search response shape) that unit-level tests on
ingestion_service/retrieval_service don't touch.

Every document title here is prefixed with a per-module-run unique tag so
these tests never collide with tests/test_rag_ingestion.py's or
seed/seed_knowledge_base.py's documents when run in the same database
(see tests/conftest.py's docstring: API tests go through the real
connection pool, which commits, so nothing here is rolled back
automatically -- unlike the `db`-fixture tests).
"""
import io
import uuid

from fastapi.testclient import TestClient

from app.database import connection_pool
from app.main import app

client = TestClient(app)

_RUN_TAG = uuid.uuid4().hex[:8]


def _unique_title(base: str) -> str:
    return f"{base} {_RUN_TAG}"


def _create_admin() -> str:
    admin_id = uuid.uuid4()
    conn = connection_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO admins (id, name, email) VALUES (%s, %s, %s)",
                (admin_id, "API Test Admin", f"{admin_id}@university.edu"),
            )
        conn.commit()
    finally:
        connection_pool.putconn(conn)
    return str(admin_id)


def _upload(admin_id: str, title: str, content: bytes = b"Some test content for the knowledge base.", **extra):
    data = {"title": title, **extra}
    files = {"file": ("guide.txt", io.BytesIO(content), "text/plain")}
    return client.post("/admin/knowledge", data=data, files=files, headers={"X-Admin-Id": admin_id})


def test_missing_admin_header_is_rejected():
    response = client.get("/admin/knowledge")
    assert response.status_code == 401


def test_unknown_admin_id_is_rejected():
    response = client.get("/admin/knowledge", headers={"X-Admin-Id": str(uuid.uuid4())})
    assert response.status_code == 403


def test_upload_creates_ready_document():
    admin_id = _create_admin()
    response = _upload(admin_id, _unique_title("API TXT Guide"), category="OTHER")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "READY"
    assert body["error_message"] is None


def test_get_document_by_id():
    admin_id = _create_admin()
    created = _upload(admin_id, _unique_title("API Get Guide")).json()

    response = client.get(f"/admin/knowledge/{created['id']}", headers={"X-Admin-Id": admin_id})
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_document_not_found_is_404():
    admin_id = _create_admin()
    response = client.get(f"/admin/knowledge/{uuid.uuid4()}", headers={"X-Admin-Id": admin_id})
    assert response.status_code == 404


def test_list_chunks_for_document():
    admin_id = _create_admin()
    created = _upload(admin_id, _unique_title("API Chunks Guide")).json()

    response = client.get(f"/admin/knowledge/{created['id']}/chunks", headers={"X-Admin-Id": admin_id})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert "embedding" not in body["items"][0]  # phase7.md #18: never exposed over the API


def test_upload_with_unsupported_file_type_returns_422():
    admin_id = _create_admin()
    files = {"file": ("virus.exe", io.BytesIO(b"whatever"), "application/octet-stream")}
    response = client.post(
        "/admin/knowledge",
        data={"title": _unique_title("Bad Type")},
        files=files,
        headers={"X-Admin-Id": admin_id},
    )
    assert response.status_code == 422


def test_duplicate_title_upload_returns_409():
    admin_id = _create_admin()
    title = _unique_title("Duplicate API Guide")
    first = _upload(admin_id, title)
    assert first.status_code == 201

    second = _upload(admin_id, title)
    assert second.status_code == 409


def test_replace_document_id_creates_new_version_via_api():
    admin_id = _create_admin()
    title = _unique_title("Versioned API Guide")
    original = _upload(admin_id, title).json()

    new_version = _upload(admin_id, title, replace_document_id=original["id"]).json()
    assert new_version["version"] == 2
    assert new_version["previous_version_id"] == original["id"]

    original_after = client.get(f"/admin/knowledge/{original['id']}", headers={"X-Admin-Id": admin_id}).json()
    assert original_after["status"] == "ARCHIVED"


def test_delete_without_hard_archives_document():
    admin_id = _create_admin()
    created = _upload(admin_id, _unique_title("API Archive Guide")).json()

    response = client.delete(f"/admin/knowledge/{created['id']}", headers={"X-Admin-Id": admin_id})
    assert response.status_code == 204

    after = client.get(f"/admin/knowledge/{created['id']}", headers={"X-Admin-Id": admin_id}).json()
    assert after["status"] == "ARCHIVED"


def test_delete_with_hard_permanently_removes_document():
    admin_id = _create_admin()
    created = _upload(admin_id, _unique_title("API Hard Delete Guide")).json()

    response = client.delete(f"/admin/knowledge/{created['id']}?hard=true", headers={"X-Admin-Id": admin_id})
    assert response.status_code == 204

    after = client.get(f"/admin/knowledge/{created['id']}", headers={"X-Admin-Id": admin_id})
    assert after.status_code == 404


def test_search_endpoint_returns_results_and_rag_context():
    admin_id = _create_admin()
    title = _unique_title("API Search VPN Guide")
    _upload(admin_id, title, content=b"VPN authentication failed, error VPN-ERR-403.", category="VPN")

    response = client.post(
        "/admin/knowledge/search",
        json={"query": "VPN authentication failed", "top_k": 3},
        headers={"X-Admin-Id": admin_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "VPN authentication failed"
    assert any(r["title"] == title for r in body["results"])
    assert body["context"]["query"] == "VPN authentication failed"
    assert all({"title", "content", "score"} == set(r.keys()) for r in body["context"]["results"])


def test_search_without_admin_header_is_rejected():
    response = client.post("/admin/knowledge/search", json={"query": "vpn"})
    assert response.status_code == 401
