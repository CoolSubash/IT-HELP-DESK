"""
Embedding tests (phase7.md #20: "Embeddings: mock the embedding
provider"). DevEmbeddingProvider (app/rag/embeddings/dev_provider.py) IS
the mock -- there's no real Bedrock provider to fake here, since the
whole point of that module is to be a deterministic, credential-free
stand-in usable in exactly this kind of test. No `db` fixture needed --
pure Python, no I/O.
"""
import math

from app.rag.embeddings.dev_provider import DevEmbeddingProvider


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def test_embedding_is_deterministic():
    provider = DevEmbeddingProvider(dimensions=64)
    first = provider.embed_text("VPN authentication failed")
    second = provider.embed_text("VPN authentication failed")
    assert first == second


def test_embedding_has_requested_dimensions():
    provider = DevEmbeddingProvider(dimensions=128)
    vector = provider.embed_text("password reset")
    assert len(vector) == 128


def test_embedding_is_unit_length():
    provider = DevEmbeddingProvider(dimensions=64)
    vector = provider.embed_text("some IT support text about printers")
    norm = math.sqrt(sum(component * component for component in vector))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_similar_text_scores_higher_than_dissimilar_text():
    provider = DevEmbeddingProvider(dimensions=256)

    vpn_query = provider.embed_text("My VPN authentication failed, connection error")
    vpn_doc = provider.embed_text("VPN authentication failure and connection troubleshooting steps")
    printer_doc = provider.embed_text("Printer paper jam and toner replacement instructions")

    similarity_to_vpn_doc = _cosine_similarity(vpn_query, vpn_doc)
    similarity_to_printer_doc = _cosine_similarity(vpn_query, printer_doc)

    assert similarity_to_vpn_doc > similarity_to_printer_doc


def test_embed_batch_matches_embed_text_per_item():
    provider = DevEmbeddingProvider(dimensions=32)
    texts = ["VPN issue", "password issue", "printer issue"]
    batch_result = provider.embed_batch(texts)
    individual_result = [provider.embed_text(t) for t in texts]
    assert batch_result == individual_result


def test_empty_text_still_produces_a_valid_unit_vector():
    provider = DevEmbeddingProvider(dimensions=32)
    vector = provider.embed_text("")
    assert len(vector) == 32
    norm = math.sqrt(sum(component * component for component in vector))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)
