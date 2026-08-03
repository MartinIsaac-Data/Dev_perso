"""Entry and project DTOs (API.md §5.3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DuePrecision, EntryStatus, EntryType, Priority


class TaskView(BaseModel):
    due_at: datetime | None = None
    due_precision: DuePrecision | None = None
    # The user's own words, kept so a bad resolution can be audited (ADR-020).
    due_raw_expression: str | None = None
    priority: Priority = Priority.NORMAL
    completed_at: datetime | None = None
    snoozed_until: datetime | None = None
    assignee_label: str | None = None
    recurrence_rule: str | None = None


class SourceView(BaseModel):
    capture_id: uuid.UUID | None = None
    span_start: int | None = None
    span_end: int | None = None


class EntryView(BaseModel):
    object: str = "entry"
    id: uuid.UUID
    entry_type: EntryType
    title: str
    body: str | None = None
    status: EntryStatus
    occurred_at: datetime
    project_id: uuid.UUID | None = None
    origin: str
    confidence: float | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    edited_by_user_at: datetime | None = None
    source: SourceView | None = None
    task: TaskView | None = None
    tags: list[str] = Field(default_factory=list)


class CreateEntryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entry_type": "task",
                "title": "Rappeler le DAF de Vinci",
                "due_expression": "jeudi",
                "priority": "normal",
            }
        }
    )

    entry_type: EntryType = EntryType.NOTE
    title: str = Field(min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    project_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    # A raw expression, not a date: the same deterministic resolver used by the
    # pipeline handles it (ADR-020).
    due_expression: str | None = Field(default=None, max_length=120)
    priority: Priority = Priority.NORMAL


class UpdateEntryRequest(BaseModel):
    """Partial update. An absent field means "unchanged"; an explicit `null`
    means "clear" for the nullable fields (API.md §2.2)."""

    model_config = ConfigDict(extra="forbid")

    entry_type: EntryType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    status: EntryStatus | None = None
    project_id: uuid.UUID | None = None
    due_expression: str | None = Field(default=None, max_length=120)
    priority: Priority | None = None

    def as_changes(self) -> dict[str, object]:
        return {
            key: (value.value if hasattr(value, "value") else value)
            for key, value in self.model_dump(exclude_unset=True).items()
        }


class TransformEntryRequest(BaseModel):
    target_type: EntryType


class ProjectView(BaseModel):
    object: str = "project"
    id: uuid.UUID
    name: str
    slug: str
    color: str | None = None
    aliases: list[str] = Field(default_factory=list)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    # Spoken aliases: "le client Vinci", "VNC" — used for project matching.
    aliases: list[str] = Field(default_factory=list, max_length=10)


class DashboardView(BaseModel):
    object: str = "dashboard"
    capture_count: int
    entries_by_type: dict[str, int]
    entries_by_status: dict[str, int]
    needs_review: int
    due_soon: list[EntryView]
    quota: dict[str, int | None]


class MeView(BaseModel):
    object: str = "user"
    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    timezone: str
    locale: str
    role: str
