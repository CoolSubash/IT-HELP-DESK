"""
Chunking strategy (phase7.md #4-5).

Why chunk at all: an embedding model compresses a piece of text into one
fixed-size vector. Do that to an entire 20-page VPN guide and the vector
has to represent "installation instructions" AND "troubleshooting steps"
AND "common error codes" all at once -- averaged together, none of it is
retrievable precisely. A student asking "VPN authentication failed" needs
the *troubleshooting* section back, not a vector that's a blurry mix of
the whole document. Smaller, semantically coherent chunks mean each
embedding represents one idea, so a query about that idea scores that
chunk highly and leaves the rest of the document out of the way.

Why NOT chunk arbitrarily (e.g. every 500 characters): splitting in the
middle of a numbered instruction or a table row produces a chunk that is
syntactically valid text but semantically useless -- "3. Click OK. 4."
with no idea what step 4 actually is. Section 5 of phase7.md asks
explicitly for boundary-aware splitting; this module does it in two
passes: first split into whole *blocks* (heading/paragraph/bullet-list),
then pack whole blocks into chunks up to the target size, splitting a
single oversized block only as a last resort (at sentence boundaries).

Tokens vs. words: this project has no tokenizer dependency (no
`tiktoken`/`transformers`), and adding one just to count tokens more
precisely was judged not worth the extra dependency for a first
implementation. `count_tokens_approx()` uses `words * 1.3` as a stand-in
(English text averages roughly 0.75 words per GPT-style token, i.e.
~1.3 tokens per word) and every "tokens" concept in this module is in
that approximated unit. This is documented explicitly rather than
pretending it's exact, per phase7.md #5 ("do not blindly assume these
values are optimal") -- see docs/rag-manual for the tradeoff writeup and
how to swap in a real tokenizer later without changing any call site
(chunk_text()'s signature and Chunk shape stay the same).
"""
import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"\S+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# A block boundary is a heading line, or a blank line separating
# paragraphs/bullets. Splitting here first (before any size-based packing)
# is what keeps chunk boundaries out of the middle of an instruction.
_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")
_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 /,\-]{2,80}:?)\s*$")

WORDS_TO_TOKENS_RATIO = 1.3


def count_tokens_approx(text: str) -> int:
    words = len(_WORD_RE.findall(text))
    return max(1, round(words * WORDS_TO_TOKENS_RATIO))


@dataclass
class Chunk:
    content: str
    chunk_index: int
    token_count: int


def _split_into_blocks(text: str) -> list[str]:
    """First pass: whole paragraphs/headings/bullet groups, never split
    internally. A heading line is kept attached to the block that follows
    it (so "## VPN Errors\n\nAuth failures happen when..." stays one
    block) rather than becoming its own zero-content block."""
    raw_blocks = [b.strip() for b in _BLOCK_SPLIT_RE.split(text) if b.strip()]

    blocks: list[str] = []
    pending_heading: str | None = None
    for block in raw_blocks:
        first_line = block.splitlines()[0].strip()
        is_heading_only = len(block.splitlines()) == 1 and _HEADING_RE.match(first_line)
        if is_heading_only:
            pending_heading = block
            continue
        if pending_heading is not None:
            block = f"{pending_heading}\n\n{block}"
            pending_heading = None
        blocks.append(block)

    if pending_heading is not None:
        # A trailing heading with nothing after it -- rare, but keep it
        # rather than silently dropping content.
        blocks.append(pending_heading)

    return blocks


def _split_oversized_block(block: str, max_tokens: int) -> list[str]:
    """Last resort for a single block that alone exceeds the chunk size
    (e.g. one giant paragraph with no blank lines). Splits at sentence
    boundaries rather than mid-sentence, packing sentences greedily up to
    max_tokens."""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(block) if s.strip()]
    if len(sentences) <= 1:
        return [block]  # nothing sane to split on; keep it whole

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        sentence_tokens = count_tokens_approx(sentence)
        if current and current_tokens + sentence_tokens > max_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += sentence_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _overlap_prefix(previous_content: str, overlap_tokens: int) -> str:
    """The trailing `overlap_tokens` words of the previous chunk, used as
    a prefix for the next one. Overlap exists so a sentence like "Restart
    the VPN client, then try connecting again" isn't split so that "then
    try connecting again" ends up alone in the next chunk with no idea
    what "then" refers to -- the tail of the prior chunk gives the next
    one a small amount of context to stay coherent on its own, which
    matters because chunks are retrieved and shown to the AI agent
    independently, not read in original document order."""
    words = _WORD_RE.findall(previous_content)
    max_words = max(1, round(overlap_tokens / WORDS_TO_TOKENS_RATIO))
    if len(words) <= max_words:
        return previous_content
    return " ".join(words[-max_words:])


def chunk_text(
    text: str,
    chunk_size_tokens: int = 600,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    """Packs whole blocks (paragraphs/headings/bullet groups) into chunks
    up to ~chunk_size_tokens, carrying ~overlap_tokens of context forward
    from the end of one chunk to the start of the next.

    Defaults (600/80, in the ~1.3 tokens-per-word approximation above)
    sit inside phase7.md #5's suggested 500-1000/50-150 range without
    picking the extremes -- they are NOT claimed to be optimal; both are
    plain function parameters (in turn driven by
    settings.rag_chunk_size_words / rag_chunk_overlap_words) specifically
    so they're easy to tune per corpus without a code change. See
    docs/rag-manual's evaluation chapter for how Recall@K/Precision@K
    against the eval dataset (app/rag/eval.py) is the intended way to
    decide whether a different value actually helps, rather than
    guessing.

    Trade-off: larger chunks retain more surrounding context per chunk
    (fewer "which VPN error is this troubleshooting step even for"
    ambiguities) but dilute the embedding (more competing topics per
    vector, worse precision) and cost more tokens once a chunk is fed to
    an LLM. Smaller chunks are the opposite: sharper, more precise
    retrieval but more fragmented context, and more chunks to embed/store
    per document. More overlap reduces the chance a boundary falls
    exactly on the information a query needs, at the cost of redundant
    (and redundantly embedded/stored) text.
    """
    if not text or not text.strip():
        return []

    blocks = _split_into_blocks(text)

    normalized_blocks: list[str] = []
    for block in blocks:
        if count_tokens_approx(block) > chunk_size_tokens:
            normalized_blocks.extend(_split_oversized_block(block, chunk_size_tokens))
        else:
            normalized_blocks.append(block)

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0

    def _flush() -> None:
        if not current_parts:
            return
        content = "\n\n".join(current_parts)
        chunks.append(Chunk(content=content, chunk_index=len(chunks), token_count=count_tokens_approx(content)))

    for block in normalized_blocks:
        block_tokens = count_tokens_approx(block)
        if current_parts and current_tokens + block_tokens > chunk_size_tokens:
            _flush()
            prefix = _overlap_prefix(current_parts[-1], overlap_tokens) if overlap_tokens > 0 else None
            current_parts = [prefix, block] if prefix else [block]
            current_tokens = count_tokens_approx("\n\n".join(current_parts))
        else:
            current_parts.append(block)
            current_tokens += block_tokens

    _flush()
    return chunks
