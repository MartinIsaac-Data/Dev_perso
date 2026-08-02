"""The strongly-typed contract the LLM must satisfy (AI.md §4.2).

Two rules make this schema what it is:

* **Nothing verifiable is left to the model** (ADR-020). The model *spots* a
  temporal expression and returns it verbatim in `expression`; a deterministic
  resolver turns it into a date. Same for projects: the model returns a hint, the
  code matches it against the user's real projects.
* **A non-conforming output is a failure, not an approximation** (AI.md, I3).
  Every field is constrained here so that validation either passes or the run is
  rejected — there is no best-effort parsing path.

`source_span` is what lets the client highlight the exact words an item came from,
and — more importantly — lets the server verify the model did not invent content.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import EntryType, Priority

MAX_ITEMS = 10
MAX_TAGS = 8
MAX_PEOPLE = 10


class SourceSpan(BaseModel):
    """Character offsets into the transcript this item was derived from."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> SourceSpan:
        if self.end <= self.start:
            raise ValueError("source_span.end must be greater than source_span.start")
        return self


class TemporalHint(BaseModel):
    """A date *as the user said it* — never resolved by the model (ADR-020)."""

    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="due", pattern="^(due|event|mention|reminder)$")


class AnalysisTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=2000)
    due: TemporalHint | None = None
    priority: Priority = Priority.NORMAL
    assignee: str | None = Field(default=None, max_length=120)
    project_hint: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: SourceSpan | None = None

    @field_validator("title")
    @classmethod
    def _no_preamble(cls, value: str) -> str:
        return value.strip()


class AnalysisIdea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=2000)
    project_hint: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: SourceSpan | None = None


class AnalysisNote(BaseModel):
    """Anything that is neither an actionable task nor a distinct idea:
    observations, decisions in the making, open questions."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=4000)
    entry_type: EntryType = EntryType.NOTE
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: SourceSpan | None = None


class NoteAnalysis(BaseModel):
    """The complete JSON the LLM returns for one capture."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(pattern="^[a-z]{2}$")
    summary: str = Field(min_length=1, max_length=2000)

    tasks: list[AnalysisTask] = Field(default_factory=list, max_length=MAX_ITEMS)
    ideas: list[AnalysisIdea] = Field(default_factory=list, max_length=MAX_ITEMS)
    notes: list[AnalysisNote] = Field(default_factory=list, max_length=MAX_ITEMS)

    categories: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    people: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    projects: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    dates: list[TemporalHint] = Field(default_factory=list, max_length=MAX_TAGS)

    priority: Priority = Priority.NORMAL
    overall_confidence: float = Field(ge=0.0, le=1.0)

    # Anything the model chose not to attach to an item. Surfacing it is better
    # than silently dropping it (AI.md §4.2).
    unprocessed_remainder: str | None = Field(default=None, max_length=4000)

    @field_validator("categories", "people", "projects", "tags", mode="after")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for raw in values:
            item = raw.strip()
            if item and len(item) <= 120:
                seen.setdefault(item, None)
        return list(seen)

    @property
    def item_count(self) -> int:
        return len(self.tasks) + len(self.ideas) + len(self.notes)

    def is_empty(self) -> bool:
        return self.item_count == 0


def json_schema_for_llm() -> dict[str, object]:
    """The schema handed to the provider for constrained decoding.

    Providers require `additionalProperties: false` and every property listed in
    `required` for strict structured output, so optional fields are expressed as
    nullable unions rather than omitted keys.
    """
    schema = NoteAnalysis.model_json_schema()
    _harden(schema)
    return schema


def _harden(node: object) -> None:
    """Walk the generated schema and make every object strict."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _harden(value)
    elif isinstance(node, list):
        for value in node:
            _harden(value)
