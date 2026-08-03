"""Closed value sets.

Mirrors the `VARCHAR + CHECK` enumerations of Database.md §5 — a PostgreSQL ENUM
cannot be altered without a lock, so the database stores plain strings and these
classes are the single source of truth on the Python side (Database.md, M6).
"""

from __future__ import annotations

from enum import StrEnum


class CaptureKind(StrEnum):
    QUICK = "quick"
    MEETING = "meeting"
    DICTATION = "dictation"
    IMPORTED = "imported"


class CaptureSource(StrEnum):
    APP = "app"
    WIDGET = "widget"
    WATCH = "watch"
    CARPLAY = "carplay"
    SHORTCUT = "shortcut"
    WEB = "web"
    API = "api"


class CaptureStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    PARTIALLY_PROCESSED = "partially_processed"
    TRANSCRIPTION_FAILED = "transcription_failed"
    ABANDONED = "abandoned"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_CAPTURE_STATUSES


_TERMINAL_CAPTURE_STATUSES = frozenset(
    {
        CaptureStatus.COMPLETED,
        CaptureStatus.PARTIALLY_PROCESSED,
        CaptureStatus.TRANSCRIPTION_FAILED,
        CaptureStatus.ABANDONED,
    }
)


class AudioFormat(StrEnum):
    M4A = "m4a"
    OPUS = "opus"
    WAV = "wav"
    MP3 = "mp3"
    WEBM = "webm"

    @property
    def media_type(self) -> str:
        return _MEDIA_TYPES[self]


_MEDIA_TYPES = {
    AudioFormat.M4A: "audio/mp4",
    AudioFormat.OPUS: "audio/ogg",
    AudioFormat.WAV: "audio/wav",
    AudioFormat.MP3: "audio/mpeg",
    AudioFormat.WEBM: "audio/webm",
}


class EntryType(StrEnum):
    TASK = "task"
    IDEA = "idea"
    NOTE = "note"
    DECISION = "decision"
    QUESTION = "question"
    MEETING = "meeting"
    REMINDER = "reminder"


class EntryStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    ACTIVE = "active"
    DONE = "done"
    ARCHIVED = "archived"
    SNOOZED = "snoozed"


class EntryOrigin(StrEnum):
    AI = "ai"
    USER = "user"
    INTEGRATION = "integration"
    TRANSFORM = "transform"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DuePrecision(StrEnum):
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"


class AiOperation(StrEnum):
    CLASSIFY = "classify"
    EXTRACT = "extract"
    SUMMARIZE = "summarize"
    ANSWER = "answer"
    EMBED = "embed"
    TRANSCRIBE = "transcribe"
    LINK = "link"


class AiRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUSED = "refused"
    SCHEMA_VIOLATION = "schema_violation"
    TIMEOUT = "timeout"


# --------------------------------------------------------------------------- #
# Phase 2 — planning, reminders, notifications, history
# --------------------------------------------------------------------------- #
class DevicePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"
    WATCHOS = "watchos"
    WEAROS = "wearos"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class PushProvider(StrEnum):
    """Which service actually delivers the payload.

    Kept separate from the platform: an Android phone and a Chrome tab both go
    through FCM, and a Windows desktop can be reached either by WNS (packaged
    app) or by a local scheduled toast (unpackaged). The platform says *what the
    device is*; the provider says *how to reach it*.
    """

    FCM = "fcm"
    WNS = "wns"
    LOCAL = "local"
    NONE = "none"


class ReminderChannel(StrEnum):
    PUSH = "push"
    # Scheduled by the device itself; the server records it so the two views of
    # "what is scheduled" cannot drift apart.
    LOCAL = "local"
    EMAIL = "email"


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISMISSED = "dismissed"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_REMINDER_STATUSES


_TERMINAL_REMINDER_STATUSES = frozenset(
    {
        ReminderStatus.SENT,
        ReminderStatus.CANCELLED,
        ReminderStatus.DISMISSED,
    }
)


class NotificationKind(StrEnum):
    REMINDER = "reminder"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    CAPTURE_READY = "capture_ready"
    CAPTURE_FAILED = "capture_failed"
    REVIEW_PENDING = "review_pending"
    DIGEST = "digest"
    SYSTEM = "system"


class ActivityAction(StrEnum):
    """The user-visible history (Timeline).

    Distinct from `audit_log`, which is a security record nobody browses, and
    from `correction_event`, which measures model quality. This one exists to
    answer "what happened to this task?" — and its vocabulary is chosen for that
    question, not for compliance.
    """

    CREATED = "created"
    EDITED = "edited"
    COMPLETED = "completed"
    REOPENED = "reopened"
    ARCHIVED = "archived"
    DELETED = "deleted"
    RESTORED = "restored"
    SNOOZED = "snoozed"
    RESCHEDULED = "rescheduled"
    PRIORITY_CHANGED = "priority_changed"
    PROJECT_CHANGED = "project_changed"
    TAGGED = "tagged"
    UNTAGGED = "untagged"
    SUBTASK_ADDED = "subtask_added"
    SUBTASK_COMPLETED = "subtask_completed"
    REMINDER_SET = "reminder_set"
    REMINDER_FIRED = "reminder_fired"
    RECURRED = "recurred"
    CAPTURED = "captured"


class AgendaView(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class Recurrence(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
