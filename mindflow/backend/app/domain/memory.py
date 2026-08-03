"""What the assistant remembers between conversations.

Without memory, every conversation starts from zero: the user re-explains that
they run the Gabon forecast, that "le DAF" is Sylvie, that they want short
answers. That is tedious, and it is also *expensive* — the same context gets
re-established through retrieval on every single turn.

The design question is not "should we remember" but **what is safe to remember**.
A memory is written once and read on every subsequent conversation, so a wrong
one is not a wrong answer, it is a wrong answer repeated forever, silently, with
no obvious cause. Three rules follow:

* **Only durable facts.** "Je suis en déplacement cette semaine" is true today
  and misleading in ten days. Anything with an expiry is not a memory; it is a
  note, and the corpus already holds it.
* **Confidence decays.** A memory not confirmed in months is more likely stale
  than a memory confirmed yesterday. Retrieval weights by recency of
  confirmation rather than by original confidence.
* **Every memory is attributable and removable.** Each carries the conversation
  that produced it, so a user asking "why do you think that?" gets an answer,
  and deleting it is one row.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.analysis import harden_schema

MAX_MEMORIES = 6

# A memory unconfirmed for this long is half as trustworthy as a fresh one. Six
# months is roughly where job titles, tooling and team composition turn over.
HALF_LIFE_DAYS = 180


class MemoryKind(StrEnum):
    """Why a fact is worth keeping."""

    # "Je dirige le pôle forecast" — frames every answer.
    PROFILE = "profile"
    # "Réponds-moi toujours en français, sans préambule" — changes how we answer.
    PREFERENCE = "preference"
    # "Sylvie est la DAF" — resolves references in future questions.
    RELATION = "relation"
    # "Le point hebdo est le mardi matin" — recurring structure.
    ROUTINE = "routine"

    @property
    def label(self) -> str:
        return {
            MemoryKind.PROFILE: "Profil",
            MemoryKind.PREFERENCE: "Préférence",
            MemoryKind.RELATION: "Relation",
            MemoryKind.ROUTINE: "Habitude",
        }[self]


class MemoryCandidate(BaseModel):
    """A fact the model proposes keeping. Proposal, not decision."""

    model_config = ConfigDict(extra="forbid")

    kind: MemoryKind
    # Written as a standalone sentence: it will be read months later with no
    # surrounding conversation to disambiguate it.
    statement: str = Field(min_length=3, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("statement")
    @classmethod
    def _tidy(cls, value: str) -> str:
        return " ".join(value.split())

    @property
    def dedupe_key(self) -> str:
        """Lower-cased statement — enough to stop the same fact being stored on
        every turn of a long conversation, which is the common failure."""
        return f"{self.kind.value}:{self.statement.strip().lower()}"


class MemoryExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memories: list[MemoryCandidate] = Field(default_factory=list, max_length=MAX_MEMORIES)

    def worth_keeping(self, *, min_confidence: float = 0.7) -> list[MemoryCandidate]:
        """Only high-confidence candidates survive.

        The threshold is deliberately higher than anywhere else in the product.
        A doubtful extraction shows up once and is forgotten; a doubtful memory
        shapes every future answer.
        """
        kept: dict[str, MemoryCandidate] = {}
        for candidate in self.memories:
            if candidate.confidence < min_confidence:
                continue
            kept.setdefault(candidate.dedupe_key, candidate)
        return list(kept.values())


def decayed_weight(confirmed_at: datetime, *, now: datetime) -> float:
    """How much to trust a memory, given when it was last confirmed.

    Exponential half-life rather than a hard expiry: a cliff would make a memory
    vanish between two turns of the same conversation, which reads as the
    assistant developing amnesia mid-sentence.
    """
    age = now - confirmed_at
    if age <= timedelta(0):
        return 1.0
    return float(0.5 ** (age.total_seconds() / (HALF_LIFE_DAYS * 86400)))


def json_schema_for_llm() -> dict[str, object]:
    schema = MemoryExtraction.model_json_schema()
    harden_schema(schema)
    return schema
