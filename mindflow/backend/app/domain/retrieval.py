"""Fusing two rankings into one.

Hybrid retrieval means running a lexical search and a vector search and
combining them. The naive combination — normalise both scores and add them — is
wrong for a reason worth stating: **the two scores are not commensurable**.
`ts_rank_cd` is unbounded and corpus-dependent; cosine similarity is bounded and
distribution-dependent. Adding them makes the weighting an accident of whichever
happens to have the larger spread today.

Reciprocal Rank Fusion sidesteps that entirely by using only the *positions*.
A document ranked third by one retriever and twentieth by the other scores the
same regardless of what either retriever thought the numbers meant. It is
embarrassingly simple, has no parameters to tune beyond `k`, and beats score
normalisation on every published comparison the authors ran.

    RRF(d) = Σ  1 / (k + rank_i(d))

`k = 60` is the constant from the original paper. Its job is to flatten the head:
without it, the top result of either list would dominate any consensus among the
rest, which is exactly the failure mode hybrid search exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

RRF_K = 60

# Lexical and semantic contribute equally by default. Neither is reliably better:
# vector search finds "le patron" from "directeur", lexical search finds an exact
# reference number that no embedding will ever place nearby.
DEFAULT_LEXICAL_WEIGHT = 1.0
DEFAULT_SEMANTIC_WEIGHT = 1.0


class Retriever(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    RECENCY = "recency"


@dataclass(slots=True)
class Candidate:
    """One retrieved item, with where each retriever placed it."""

    ref: str
    ranks: dict[Retriever, int] = field(default_factory=dict)
    scores: dict[Retriever, float] = field(default_factory=dict)
    fused: float = 0.0

    @property
    def found_by(self) -> tuple[Retriever, ...]:
        return tuple(self.ranks)

    @property
    def is_consensus(self) -> bool:
        """Found by more than one retriever.

        Worth surfacing: agreement between a lexical and a semantic match is a
        much stronger signal than a high score from either alone.
        """
        return len(self.ranks) > 1


def reciprocal_rank_fusion(
    rankings: dict[Retriever, list[str]],
    *,
    weights: dict[Retriever, float] | None = None,
    k: int = RRF_K,
    limit: int | None = None,
) -> list[Candidate]:
    """Fuse ranked lists of references into one ranking.

    Input lists are ordered best-first and may overlap or be empty. An empty
    input is not an error — a semantic search with no index yet is exactly that,
    and the lexical ranking alone is a perfectly good answer.
    """
    weight_for = weights or {
        Retriever.LEXICAL: DEFAULT_LEXICAL_WEIGHT,
        Retriever.SEMANTIC: DEFAULT_SEMANTIC_WEIGHT,
    }

    merged: dict[str, Candidate] = {}
    for retriever, refs in rankings.items():
        weight = weight_for.get(retriever, 1.0)
        if weight <= 0:
            continue
        for position, ref in enumerate(refs, start=1):
            candidate = merged.setdefault(ref, Candidate(ref=ref))
            # First occurrence wins: a retriever that returns a duplicate must
            # not double-count it.
            if retriever in candidate.ranks:
                continue
            candidate.ranks[retriever] = position
            candidate.fused += weight / (k + position)

    ordered = sorted(
        merged.values(),
        # Ties broken by the best single rank, then by reference: a stable order
        # matters because an unstable one makes the same query return results in
        # a different order on every call.
        key=lambda item: (-item.fused, min(item.ranks.values()), item.ref),
    )
    return ordered[:limit] if limit else ordered


def attach_scores(
    candidates: list[Candidate],
    retriever: Retriever,
    scores: dict[str, float],
) -> None:
    """Record the raw scores for explanation, never for ranking.

    Kept because "why did this come up?" is a question users ask, and answering
    it with a rank alone is unsatisfying. They do not participate in the fusion —
    that is the whole point of RRF.
    """
    for candidate in candidates:
        value = scores.get(candidate.ref)
        if value is not None:
            candidate.scores[retriever] = value


@dataclass(frozen=True, slots=True)
class Citation:
    """Where an answer came from.

    Every generated sentence in this product is traceable to a capture. A RAG
    answer without citations is indistinguishable from a hallucination, and the
    user has no way to tell which one they are reading.
    """

    ref: str
    entry_id: str | None
    capture_id: str | None
    title: str
    excerpt: str
    occurred_at: str | None = None
    score: float = 0.0


def deduplicate_citations(citations: list[Citation], *, limit: int = 8) -> list[Citation]:
    """One citation per source entry.

    Three chunks of the same long meeting are one source to a reader, and a
    citation list that repeats the same title three times looks broken even when
    it is technically correct.
    """
    seen: set[str] = set()
    kept: list[Citation] = []
    for citation in citations:
        key = citation.entry_id or citation.capture_id or citation.ref
        if key in seen:
            continue
        seen.add(key)
        kept.append(citation)
        if len(kept) >= limit:
            break
    return kept
