"""
Retrieval / vector-search tests (phase7.md #20: "Vector search: insert
test vectors and verify relevant chunks are returned", "Metadata
filtering: verify ARCHIVED documents are excluded", and the literal
"VPN query -> VPN chunks / Password query -> Password chunks / WiFi
query -> WiFi chunks" retrieval test). Ingests real documents through
ingestion_service (real chunking + the real DevEmbeddingProvider) into
the real `db` fixture connection, then queries through
retrieval_service.search() -- an actual pgvector nearest-neighbor query,
not a mocked result.

`_TAG`, mixed into every seeded document's content and every query below,
exists for the same reason tests/test_tickets_api.py uses unique emails:
this file's `db` fixture connection sees every row already committed by
OTHER tests too (Postgres READ COMMITTED -- a fresh transaction sees
prior committed writes from any connection, including
tests/test_knowledge_api.py's, which goes through the real connection
pool and therefore commits instead of rolling back). Without something
that guarantees this test's intended document actually outranks whatever
else happens to be in the table when the full suite runs, "the VPN
query's top result is the VPN document" would be flaky depending on test
run order -- not because retrieval is wrong, but because a *different*
VPN document seeded by another test file can legitimately be an equally
good (or better) match for a generic query. Real IT documents obviously
wouldn't have this marker; it's a test-isolation device, not a feature
of the ranking itself, the same way `xyzzy123` further below is.
"""
import uuid

from app.rag import ingestion_service, retrieval_service

_TAG = uuid.uuid4().hex[:10]


def _ingest(db, title: str, category: str, content: str) -> dict:
    return ingestion_service.ingest_document(
        db,
        title=title,
        description=None,
        category=category,
        file_name=f"{title}.txt",
        file_type="txt",
        file_bytes=content.encode("utf-8"),
    )


def _seed_three_documents(db) -> None:
    _ingest(
        db,
        f"Retrieval Test VPN Guide {_TAG}",
        "VPN",
        f"{_TAG} VPN authentication failed error VPN-ERR-403. Restart Cisco AnyConnect and check your password.",
    )
    _ingest(
        db,
        f"Retrieval Test Password Guide {_TAG}",
        "PASSWORD",
        f"{_TAG} Forgot your password? Reset it at password.university.edu using MFA verification.",
    )
    _ingest(
        db,
        f"Retrieval Test WiFi Guide {_TAG}",
        "WIFI",
        f"{_TAG} Campus WiFi CampusSecure keeps disconnecting? Forget the network and reconnect.",
    )


def test_vpn_query_returns_vpn_document_first(db):
    _seed_three_documents(db)
    results = retrieval_service.search(db, f"{_TAG} My VPN authentication keeps failing", top_k=3)
    assert results
    assert results[0]["title"] == f"Retrieval Test VPN Guide {_TAG}"


def test_password_query_returns_password_document_first(db):
    _seed_three_documents(db)
    results = retrieval_service.search(db, f"{_TAG} I forgot my password and need to reset it", top_k=3)
    assert results
    assert results[0]["title"] == f"Retrieval Test Password Guide {_TAG}"


def test_wifi_query_returns_wifi_document_first(db):
    _seed_three_documents(db)
    results = retrieval_service.search(db, f"{_TAG} Campus WiFi disconnects constantly", top_k=3)
    assert results
    assert results[0]["title"] == f"Retrieval Test WiFi Guide {_TAG}"


def test_results_are_ordered_by_descending_score(db):
    _seed_three_documents(db)
    results = retrieval_service.search(db, f"{_TAG} VPN connection problem", top_k=3)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_archived_documents_are_excluded_from_search(db):
    document = _ingest(
        db, f"Retrieval Test Archived Guide {_TAG}", "OTHER", f"{_TAG} Some very specific unique archived content xyzzy123."
    )
    ingestion_service.archive_document(db, document["id"])

    results = retrieval_service.search(db, f"{_TAG} unique archived content xyzzy123", top_k=5)
    titles = [r["title"] for r in results]
    assert f"Retrieval Test Archived Guide {_TAG}" not in titles


def test_category_filter_restricts_results_to_matching_category(db):
    _seed_three_documents(db)
    results = retrieval_service.search(db, f"{_TAG} connection problem", top_k=10, category="WIFI")
    assert results
    assert all(r["category"] == "WIFI" for r in results)
    assert any(r["title"] == f"Retrieval Test WiFi Guide {_TAG}" for r in results)


def test_top_k_limits_number_of_results(db):
    _seed_three_documents(db)
    results = retrieval_service.search(db, f"{_TAG} IT support issue", top_k=1)
    assert len(results) <= 1


def test_category_with_no_matching_documents_returns_no_results(db):
    _seed_three_documents(db)
    nonexistent_category = f"NO-SUCH-CATEGORY-{uuid.uuid4().hex}"
    results = retrieval_service.search(db, f"{_TAG} anything at all", top_k=5, category=nonexistent_category)
    assert results == []
