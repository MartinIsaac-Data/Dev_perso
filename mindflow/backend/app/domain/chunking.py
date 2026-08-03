"""Splitting text into retrievable pieces.

This is the least glamorous part of a RAG system and the one that decides
whether it works. Three properties matter, and each is a decision:

1. **A chunk must be self-contained.** A fragment that reads "…il faut valider
   avant vendredi" retrieves well and answers nothing, because the model has no
   idea what "il" refers to. So chunks break on sentence boundaries and carry a
   small overlap.

2. **A chunk must be big enough to say something and small enough to be about
   one thing.** Too small and the vector averages nothing; too large and it
   averages everything, which in embedding space is the same as saying nothing.
   The window here is tuned for spoken French: a voice note sentence runs long.

3. **Chunking must be deterministic.** The same text must produce the same
   chunks with the same identifiers, or every re-index duplicates the corpus.
   Hence the content hash: re-embedding is a no-op when nothing changed, which
   is what makes reprocessing affordable.

No tokeniser dependency. Token counts are estimated from characters — French
averages about 3.6 characters per token on the families we use. An estimate that
is 10 % off changes a batch size; a tokeniser dependency pins us to one vendor's
vocabulary, which is exactly what phase 3 is trying to avoid.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

# Tuned for spoken French. Below ~200 characters a chunk is a fragment; above
# ~1200 it stops being about one thing.
TARGET_CHARS = 900
MIN_CHARS = 180
MAX_CHARS = 1400

# Enough to carry a pronoun's antecedent into the next chunk without duplicating
# half the corpus.
OVERLAP_CHARS = 140

# Rough, and deliberately so — see the module docstring.
CHARS_PER_TOKEN = 3.6

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n{2,}")
_WHITESPACE = re.compile(r"[ \t]+")


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable piece of text, with its place in the original."""

    text: str
    index: int
    start_char: int
    end_char: int
    content_hash: str

    @property
    def estimated_tokens(self) -> int:
        return max(1, round(len(self.text) / CHARS_PER_TOKEN))


def normalise(text: str) -> str:
    """Collapse whitespace without touching the words.

    NFC rather than NFD: `é` written as one code point and as two must hash
    identically, or the same sentence typed on two platforms re-embeds forever.
    """
    normalised = unicodedata.normalize("NFC", text)
    normalised = _WHITESPACE.sub(" ", normalised)
    return "\n".join(line.strip() for line in normalised.splitlines()).strip()


def content_hash(text: str) -> str:
    """Stable identity of a piece of text.

    Computed on the normalised form, so re-indexing after a whitespace-only edit
    is free. This is what makes re-embedding a corpus affordable: nothing that
    has not changed is sent to a provider twice.
    """
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:32]


def split(text: str, *, target: int = TARGET_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Split into chunks on sentence boundaries.

    Short text yields exactly one chunk — a voice note of two sentences must not
    be cut in half, which would make both halves retrieve worse than the whole.
    """
    cleaned = normalise(text)
    if not cleaned:
        return []
    if len(cleaned) <= MAX_CHARS:
        return [
            Chunk(
                text=cleaned,
                index=0,
                start_char=0,
                end_char=len(cleaned),
                content_hash=content_hash(cleaned),
            )
        ]

    sentences = _sentences(cleaned)
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0
    start = 0
    cursor = 0

    for sentence in sentences:
        sentence_len = len(sentence) + 1

        # A single sentence longer than the ceiling — a monologue with no full
        # stop, which spoken French produces constantly. Split it on width; a
        # hard cut beats dropping it or letting it swamp the window.
        if sentence_len > MAX_CHARS:
            if buffer:
                chunks.append(_build(buffer, len(chunks), start, cursor))
                buffer, buffer_len = [], 0
            for piece_start in range(0, len(sentence), target):
                piece = sentence[piece_start : piece_start + target]
                chunks.append(
                    _build(
                        [piece],
                        len(chunks),
                        cursor + piece_start,
                        cursor + piece_start + len(piece),
                    )
                )
            cursor += sentence_len
            start = cursor
            continue

        if buffer_len + sentence_len > target and buffer_len >= MIN_CHARS:
            chunks.append(_build(buffer, len(chunks), start, cursor))
            # Carry the tail forward so a pronoun keeps its antecedent.
            tail = _tail(buffer, overlap)
            buffer = list(tail)
            buffer_len = sum(len(part) + 1 for part in tail)
            start = cursor - buffer_len

        buffer.append(sentence)
        buffer_len += sentence_len
        cursor += sentence_len

    if buffer:
        # A trailing fragment is merged into the previous chunk rather than
        # emitted alone: a five-word chunk retrieves noise.
        if chunks and buffer_len < MIN_CHARS:
            merged = f"{chunks[-1].text} {' '.join(buffer)}".strip()
            previous = chunks.pop()
            chunks.append(
                Chunk(
                    text=merged,
                    index=previous.index,
                    start_char=previous.start_char,
                    end_char=cursor,
                    content_hash=content_hash(merged),
                )
            )
        else:
            chunks.append(_build(buffer, len(chunks), start, cursor))

    return chunks


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_END.split(text)]
    return [part for part in parts if part]


def _tail(buffer: list[str], overlap: int) -> list[str]:
    """The last sentences of a chunk, up to the overlap budget."""
    kept: list[str] = []
    total = 0
    for sentence in reversed(buffer):
        if total + len(sentence) > overlap and kept:
            break
        kept.insert(0, sentence)
        total += len(sentence)
    return kept


def _build(parts: list[str], index: int, start: int, end: int) -> Chunk:
    text = " ".join(parts).strip()
    return Chunk(
        text=text,
        index=index,
        start_char=start,
        end_char=end,
        content_hash=content_hash(text),
    )


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def fit_to_budget(texts: list[str], *, budget_tokens: int) -> list[str]:
    """Take as many pieces as fit, in order.

    Truncating the *last* piece rather than dropping it is deliberate: the
    retrieval order is by relevance, so the tail is the least useful text — but a
    partial paragraph still contributes, and an abrupt cut is visible to the
    model, which handles it better than a silent absence.
    """
    kept: list[str] = []
    used = 0
    for text in texts:
        cost = estimate_tokens(text)
        if used + cost <= budget_tokens:
            kept.append(text)
            used += cost
            continue
        remaining = budget_tokens - used
        if remaining > 40:
            kept.append(text[: int(remaining * CHARS_PER_TOKEN)] + " […]")
        break
    return kept
