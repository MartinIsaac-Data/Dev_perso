"""The knowledge graph contract: who, what, and what was decided.

Phase 3 asks the product to detect seven things automatically — personnes,
produits, entreprises, projets, décisions, risques, actions. Grouping them into
one `entity` table with a `kind` rather than seven tables is a deliberate trade:

* every one of them has the same shape — a name, an optional detail, mentions
  pointing back at captures — and seven near-identical tables would mean seven
  near-identical queries for « quels sujets reviennent souvent ? »;
* the set will grow (a `location` kind is obvious, a `contract` kind is likely),
  and growth should be an enum value, not a migration and five new endpoints.

The cost is that a kind-specific column has nowhere to go, which is why `detail`
is a single free-text field rather than a per-kind structure. That is enough for
« risque : rupture de stock sur le trimestre » and honest about the rest.

**Resolution is deterministic, extraction is not.** The model spots "Jean-Marc
Ondo" and "jean marc ondo" in two different captures; deciding those are one
person is done here, in code, by a normalised key — not by asking the model,
which would give a different answer on Tuesday. Same principle as ADR-020 for
dates and as `app.domain.intent` for routing: what can be computed exactly is
never guessed.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.analysis import SourceSpan, harden_schema

MAX_ENTITIES = 24
MAX_TOPICS = 8


class EntityKind(StrEnum):
    """The seven things worth remembering across captures."""

    PERSON = "person"
    PRODUCT = "product"
    COMPANY = "company"
    PROJECT = "project"
    DECISION = "decision"
    RISK = "risk"
    ACTION = "action"

    @property
    def label(self) -> str:
        return _KIND_LABELS[self]

    @property
    def is_nameable(self) -> bool:
        """Whether two mentions of the same string are the same thing.

        A person named twice is one person. Two risks phrased identically in
        March and in July are *not* obviously the same risk — statements are not
        proper nouns, so they resolve on a tighter key and merge far less
        eagerly. Treating them alike would collapse a project's whole history
        into a handful of rows.
        """
        return self in (
            EntityKind.PERSON,
            EntityKind.PRODUCT,
            EntityKind.COMPANY,
            EntityKind.PROJECT,
        )


_KIND_LABELS: dict[EntityKind, str] = {
    EntityKind.PERSON: "Personne",
    EntityKind.PRODUCT: "Produit",
    EntityKind.COMPANY: "Entreprise",
    EntityKind.PROJECT: "Projet",
    EntityKind.DECISION: "Décision",
    EntityKind.RISK: "Risque",
    EntityKind.ACTION: "Action",
}

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")

# Dropped before building a resolution key. "La société Total" and "Total" are
# one company; "le projet Forecast Gabon" and "Forecast Gabon" are one project.
_LEADING_NOISE = re.compile(
    r"^(le|la|les|l|un|une|des|du|de|d|monsieur|madame|mr|mme|dr|"
    r"societe|entreprise|projet|produit|equipe|client)\s+",
)


def normalise_name(name: str) -> str:
    """Fold a name to its comparison form: lower, unaccented, unpunctuated.

    Accents go because dictation and phone keyboards drop them constantly, and
    "Théo" appearing as a second person from "Theo" is a visible bug in a
    contact list. Punctuation goes because "Jean-Marc" and "Jean Marc" are one
    person.
    """
    decomposed = unicodedata.normalize("NFD", name.strip().lower())
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    cleaned = _SPACES.sub(" ", _PUNCTUATION.sub(" ", stripped)).strip()

    previous = ""
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = _LEADING_NOISE.sub("", cleaned).strip()
    # Stripping every word would leave nothing to key on; keep the fold instead.
    return cleaned or _SPACES.sub(" ", stripped).strip()


def resolution_key(kind: EntityKind, name: str) -> str:
    """The key two mentions must share to be the same entity.

    Nameable kinds key on the normalised name alone, so a person recurs across
    months. Statement kinds (decision, risk, action) key on the full normalised
    text, so only a verbatim repetition merges — the conservative choice, since
    wrongly merging two decisions loses one of them irrecoverably while wrongly
    splitting them merely shows two rows.
    """
    folded = normalise_name(name)
    if kind.is_nameable:
        return f"{kind.value}:{folded}"
    return f"{kind.value}:{folded[:200]}"


class ExtractedEntity(BaseModel):
    """One thing the model found in a capture."""

    model_config = ConfigDict(extra="forbid")

    kind: EntityKind
    # Verbatim as it appeared, so the UI can show the user's own words. The
    # normalised form is computed here, never returned by the model.
    name: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=600)
    # "DAF", "fournisseur", "bloquant" — a qualifier, not a taxonomy.
    role: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: SourceSpan | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str) -> str:
        return _SPACES.sub(" ", value.strip())

    @property
    def resolution_key(self) -> str:
        return resolution_key(self.kind, self.name)

    @property
    def normalised_name(self) -> str:
        return normalise_name(self.name)


class KnowledgeExtraction(BaseModel):
    """Everything the model found in one capture."""

    model_config = ConfigDict(extra="forbid")

    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=MAX_ENTITIES)
    # Short thematic labels, used to answer « quels sujets reviennent souvent ? »
    # alongside entity frequency.
    topics: list[str] = Field(default_factory=list, max_length=MAX_TOPICS)

    @field_validator("topics", mode="after")
    @classmethod
    def _clean_topics(cls, values: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for raw in values:
            topic = _SPACES.sub(" ", raw.strip())
            if topic and len(topic) <= 80:
                seen.setdefault(topic, None)
        return list(seen)

    def is_empty(self) -> bool:
        return not self.entities and not self.topics

    def deduplicated(self, *, min_confidence: float = 0.4) -> list[ExtractedEntity]:
        """Collapse repeats within a single capture, keeping the best.

        A model naming the same person in three sentences returns three
        entities; storing three mentions of one entity is correct, storing three
        entities is not. Highest confidence wins so the richest phrasing — the
        one with a role or a detail — is usually the survivor.
        """
        best: dict[str, ExtractedEntity] = {}
        for entity in self.entities:
            if entity.confidence < min_confidence:
                continue
            key = entity.resolution_key
            current = best.get(key)
            if current is None or entity.confidence > current.confidence:
                best[key] = entity
        return list(best.values())


def json_schema_for_llm() -> dict[str, object]:
    """The hardened schema handed to the provider for constrained decoding."""
    schema = KnowledgeExtraction.model_json_schema()
    harden_schema(schema)
    return schema
