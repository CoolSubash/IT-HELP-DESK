"""
Chunking tests (phase7.md #20's "Chunking: verify chunk count, chunk size,
overlap, metadata"). Pure unit tests -- app/rag/chunking.py has no I/O, so
these don't need the `db` fixture at all.
"""
from app.rag.chunking import chunk_text, count_tokens_approx


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_produces_one_chunk_with_correct_metadata():
    text = "## VPN\n\nThe VPN client needs to be restarted after a password change."
    chunks = chunk_text(text, chunk_size_tokens=600, overlap_tokens=80)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content.strip() == text.strip()
    assert chunks[0].token_count == count_tokens_approx(text)


def test_long_text_splits_into_multiple_chunks_respecting_target_size():
    # 10 distinct paragraphs, each ~40 words (~52 tokens) -- with a
    # chunk_size of 100 tokens, roughly 2 paragraphs should pack per chunk.
    paragraphs = [
        f"## Section {i}\n\n" + " ".join([f"word{i}_{j}" for j in range(40)]) for i in range(10)
    ]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, chunk_size_tokens=100, overlap_tokens=10)

    assert len(chunks) > 1
    # No chunk should wildly exceed the target -- some slack is expected
    # since whole blocks are never split unless a single block alone
    # exceeds the target (see chunking.py's docstring).
    for chunk in chunks:
        assert chunk.token_count <= 150
    # chunk_index is sequential starting at 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunks_carry_overlap_from_the_previous_chunk():
    paragraphs = [f"## Section {i}\n\n" + " ".join([f"word{i}_{j}" for j in range(50)]) for i in range(6)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, chunk_size_tokens=80, overlap_tokens=30)
    assert len(chunks) >= 2

    # The tail words of chunk N should reappear at the start of chunk N+1
    # (see chunking.py's _overlap_prefix) -- confirms overlap isn't just
    # configured but actually applied.
    first_chunk_tail_words = chunks[0].content.split()[-5:]
    second_chunk_words = chunks[1].content.split()
    assert any(word in second_chunk_words[:20] for word in first_chunk_tail_words)


def test_does_not_split_a_bullet_list_block_across_chunks_when_it_fits():
    text = (
        "## Common VPN Errors\n\n"
        "- Expired password causes authentication failures.\n"
        "- MFA push not approved in time causes authentication failures.\n"
        "- Account not yet provisioned causes authentication failures.\n"
    )
    chunks = chunk_text(text, chunk_size_tokens=600, overlap_tokens=80)
    assert len(chunks) == 1
    assert "Expired password" in chunks[0].content
    assert "Account not yet provisioned" in chunks[0].content


def test_oversized_single_block_splits_at_sentence_boundaries_not_mid_sentence():
    # One giant paragraph (no blank lines) that alone exceeds chunk_size --
    # chunking.py's last-resort sentence-boundary split.
    sentences = [f"This is sentence number {i} about VPN troubleshooting steps." for i in range(40)]
    text = " ".join(sentences)

    chunks = chunk_text(text, chunk_size_tokens=100, overlap_tokens=0)
    assert len(chunks) > 1
    for chunk in chunks:
        # Every chunk should end on a sentence boundary (a period), not
        # mid-sentence.
        assert chunk.content.strip().endswith(".")
