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
