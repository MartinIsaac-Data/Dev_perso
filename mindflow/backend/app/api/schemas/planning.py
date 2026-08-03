"""DTOs for agenda, tasks, reminders, notifications, search, stats and history.

Kept apart from `schemas/entries.py` so the phase-1 contract stays legible. The
one rule these all follow: a view model never leaks a database column name that
happens to differ from the API's vocabulary — the two are allowed to drift, and
pretending otherwise is how a schema migration becomes a breaking API change.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.entries import EntryView
from app.domain.enums import (
    ActivityAction,
    AgendaView,
    DevicePlatform,
    EntryStatus,
    EntryType,
    NotificationKind,
    Priority,
    PushProvider,
    ReminderChannel,
    ReminderStatus,
)


# --------------------------------------------------------------------------- #
# Subtasks
# --------------------------------------------------------------------------- #
class SubtaskView(BaseModel):
    object: str = "subtask"
    id: uuid.UUID
    entry_id: uuid.UUID
    title: str
    position: int
    completed_at: datetime | None = None
    origin: str = "user"

    @property
    def done(self) -> bool:
        return self.completed_at is not None


class CreateSubtaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class UpdateSubtaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    completed: bool | None = None


class ReorderRequest(BaseModel):
    """The full ordered list, not a (from, to) pair.

    Drag-and-drop on a flaky connection produces out-of-order deltas; replaying
    two of them gives an order nobody asked for. Sending the result the user is
    looking at is idempotent.
    """

    ordered_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
class TaskProgress(BaseModel):
    done: int = 0
    total: int = 0

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.done == self.total


class SnoozeRequest(BaseModel):
    until: datetime


class RescheduleRequest(BaseModel):
    """`null` clears the deadline; that is a legitimate act, not an omission."""

    due_at: datetime | None = None


class RecurrenceRequest(BaseModel):
    # RRULE subset — see domain.recurrence for what is actually supported.
    rule: str | None = Field(default=None, max_length=255)


class PinRequest(BaseModel):
    pinned: bool = True


class BulkUpdateRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    status: EntryStatus | None = None
    priority: Priority | None = None
    project_id: uuid.UUID | None = None
    clear_project: bool = False


class BulkResult(BaseModel):
    object: str = "bulk_result"
    matched: int
    requested: int


class CompletionView(BaseModel):
    object: str = "completion"
    entry: EntryView
    # Present when completing a recurring task created the next occurrence.
    # Returned so the interface can say "next: Monday" at the moment the user is
    # looking at it.
    next_occurrence: EntryView | None = None


# --------------------------------------------------------------------------- #
# Agenda and calendar
# --------------------------------------------------------------------------- #
class AgendaItemView(BaseModel):
    entry: EntryView
    day: date
    subtasks: TaskProgress | None = None


class AgendaDayView(BaseModel):
    day: date
    items: list[AgendaItemView] = Field(default_factory=list)


class AgendaResponse(BaseModel):
    object: str = "agenda"
    view: AgendaView
    start: date
    end: date
    timezone: str
    days: list[AgendaDayView]
    # Its own bucket rather than pinned to the day it was due: a task from three
    # weeks ago at the bottom of a scrolled-away day is a task nobody sees again.
    overdue: list[AgendaItemView] = Field(default_factory=list)
    unscheduled: list[AgendaItemView] = Field(default_factory=list)


class CalendarCellView(BaseModel):
    day: date
    total: int
    done: int
    pending: int
    overdue: int
    captures: int


class CalendarResponse(BaseModel):
    object: str = "calendar"
    start: date
    end: date
    timezone: str
    cells: list[CalendarCellView]


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #
class ReminderView(BaseModel):
    object: str = "reminder"
    id: uuid.UUID
    entry_id: uuid.UUID | None = None
    remind_at: datetime
    channel: ReminderChannel
    status: ReminderStatus
    # The wording that generated it ("-15m"), so the interface can show the rule
    # instead of a bare timestamp.
    offset_rule: str | None = None
    title: str | None = None
    body: str | None = None
    sent_at: datetime | None = None


class CreateReminderRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"entry_id": "018f…", "remind_at": "2026-08-12T07:45:00Z"}}
    )

    entry_id: uuid.UUID | None = None
    remind_at: datetime | None = None
    # Alternative to an absolute instant: an offset from the task's due date.
    offset_rule: str | None = Field(default=None, max_length=32)
    channel: ReminderChannel = ReminderChannel.PUSH
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# Notifications and devices
# --------------------------------------------------------------------------- #
class NotificationView(BaseModel):
    object: str = "notification"
    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str | None = None
    entry_id: uuid.UUID | None = None
    capture_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class NotificationSummary(BaseModel):
    object: str = "notification_summary"
    unread: int
    items: list[NotificationView] = Field(default_factory=list)


class RegisterDeviceRequest(BaseModel):
    # Stable per installation. Keyed on this rather than on the push token,
    # which rotates — keying on the token creates a duplicate row per rotation
    # and sends the same reminder five times to one phone.
    install_id: str = Field(min_length=8, max_length=64)
    platform: DevicePlatform
    push_token: str | None = Field(default=None, max_length=4096)
    push_provider: PushProvider = PushProvider.NONE
    name: str | None = Field(default=None, max_length=80)
    app_version: str | None = Field(default=None, max_length=32)
    os_version: str | None = Field(default=None, max_length=32)


class DeviceView(BaseModel):
    object: str = "device"
    id: uuid.UUID
    install_id: str
    platform: str
    push_provider: str
    name: str | None = None
    app_version: str | None = None
    last_seen_at: datetime | None = None
    # Never the token itself: it is a delivery credential, and an endpoint that
    # echoes it turns a read-only leak into a spoofing capability.
    push_enabled: bool = False


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
class ParsedQueryView(BaseModel):
    """What the server understood.

    Echoed back so the interface can show the filters as chips and — more
    importantly — say which tokens it ignored. A search box that silently drops
    `p:hgih` and returns everything teaches the user nothing.
    """

    text: str = ""
    types: list[EntryType] = Field(default_factory=list)
    statuses: list[EntryStatus] = Field(default_factory=list)
    priorities: list[Priority] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    overdue: bool = False
    recurring: bool = False
    pinned: bool = False
    ignored: list[str] = Field(default_factory=list)


class SearchHitView(BaseModel):
    entry: EntryView
    rank: float = 0.0
    # Server-rendered highlight, so the client does not re-implement the
    # tokeniser and disagree with the ranking about what matched.
    snippet: str | None = None


class SearchResponse(BaseModel):
    object: str = "search_results"
    query: ParsedQueryView
    hits: list[SearchHitView]
    total: int
    took_ms: int


class QuickHitView(BaseModel):
    kind: str
    id: str
    title: str
    subtitle: str | None = None
    icon: str | None = None


class QuickSearchResponse(BaseModel):
    object: str = "quick_results"
    entries: list[QuickHitView] = Field(default_factory=list)
    projects: list[QuickHitView] = Field(default_factory=list)
    tags: list[QuickHitView] = Field(default_factory=list)
    captures: list[QuickHitView] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
class DailyPointView(BaseModel):
    day: date
    created: int = 0
    completed: int = 0
    captured: int = 0


class BreakdownView(BaseModel):
    key: str
    label: str
    total: int
    done: int = 0
    completion_rate: float = 0.0
    color: str | None = None


class StreakView(BaseModel):
    current: int
    longest: int
    last_active_day: date | None = None


class StatisticsResponse(BaseModel):
    object: str = "statistics"
    window_days: int
    start: date
    end: date

    captures: int
    entries_created: int
    tasks_completed: int
    tasks_open: int
    tasks_overdue: int
    completion_rate: float
    median_completion_hours: float | None = None

    by_type: list[BreakdownView] = Field(default_factory=list)
    by_priority: list[BreakdownView] = Field(default_factory=list)
    by_project: list[BreakdownView] = Field(default_factory=list)
    top_tags: list[BreakdownView] = Field(default_factory=list)
    daily: list[DailyPointView] = Field(default_factory=list)
    streak: StreakView

    # The unflattering half. Reported because these are the numbers that say
    # whether the product is actually working.
    corrections: int = 0
    correction_rate: float = 0.0
    captures_without_entries: int = 0
    needs_review: int = 0
    ai_cost_micro_eur: int = 0
    busiest_hour: int | None = None


# --------------------------------------------------------------------------- #
# History / Timeline
# --------------------------------------------------------------------------- #
class ActivityView(BaseModel):
    object: str = "activity"
    id: int
    action: ActivityAction
    entry_id: uuid.UUID | None = None
    capture_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    # Denormalised at write time so the timeline survives the deletion of its
    # own subject. A history that goes blank is not a history.
    subject_label: str | None = None
    actor_type: str = "user"
    detail: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


# --------------------------------------------------------------------------- #
# Library: tags, saved filters, projects
# --------------------------------------------------------------------------- #
class TagView(BaseModel):
    object: str = "tag"
    id: uuid.UUID
    label: str
    normalized: str
    usage_count: int = 0
    color: str | None = None
    pinned: bool = False


class UpdateTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Renaming onto an existing tag merges into it rather than failing: that is
    # what the user means when they fix a duplicate.
    label: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    pinned: bool | None = None


class MergeTagRequest(BaseModel):
    target_id: uuid.UUID


class AttachTagsRequest(BaseModel):
    labels: list[str] = Field(min_length=1, max_length=20)


class SavedFilterView(BaseModel):
    object: str = "saved_filter"
    id: uuid.UUID
    name: str
    query: str
    icon: str | None = None
    color: str | None = None
    position: int = 0
    pinned: bool = False


class CreateSavedFilterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    query: str = Field(min_length=1, max_length=500)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    pinned: bool = False


class UpdateSavedFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=60)
    query: str | None = Field(default=None, min_length=1, max_length=500)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    pinned: bool | None = None


class ProjectDetailView(BaseModel):
    object: str = "project"
    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    aliases: list[str] = Field(default_factory=list)
    pinned: bool = False
    archived: bool = False
    open_count: int = 0
    total_count: int = 0


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    icon: str | None = Field(default=None, max_length=40)
    aliases: list[str] | None = Field(default=None, max_length=10)
    pinned: bool | None = None
    archived: bool | None = None
