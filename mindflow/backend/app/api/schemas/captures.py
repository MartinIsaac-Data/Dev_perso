"""Capture DTOs (API.md §5.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AudioFormat, CaptureKind, CaptureSource, CaptureStatus


class UploadInstructions(BaseModel):
    url: str
    method: str = "PUT"
    headers: dict[str, str]
    expires_at: str
    object_key: str


class DeclareCaptureRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_capture_id": "018f2c1e-4a2b-7c3d-9e1f-a5b6c7d8e9f0",
                "kind": "quick",
                "duration_ms": 14320,
                "audio_format": "m4a",
                "audio_bytes": 143200,
                "captured_at": "2026-06-09T11:47:03.221Z",
                "capture_timezone": "Europe/Paris",
                "source": "app",
                "language_hint": "fr",
            }
        }
    )

    # Generated client-side *before* recording. This is the idempotency key that
    # makes offline retry safe (ADR-009).
    client_capture_id: uuid.UUID
    kind: CaptureKind = CaptureKind.QUICK
    duration_ms: int = Field(gt=0, le=6 * 60 * 60 * 1000)
    audio_format: AudioFormat = AudioFormat.M4A
    audio_bytes: int | None = Field(default=None, ge=0)
    audio_sample_rate: int | None = Field(default=None, ge=8000, le=192000)
    captured_at: datetime
    capture_timezone: str = Field(default="Europe/Paris", max_length=64)
    source: CaptureSource = CaptureSource.APP
    language_hint: str | None = Field(default=None, max_length=8)


class TranscriptView(BaseModel):
    id: uuid.UUID
    language: str
    confidence: float | None
    text: str
    word_count: int
    engine: str
    is_fallback: bool


class EntrySummary(BaseModel):
    id: uuid.UUID
    entry_type: str
    title: str
    status: str


class AudioView(BaseModel):
    available: bool
    url: str | None = None


class CaptureView(BaseModel):
    object: str = "capture"
    id: uuid.UUID
    status: CaptureStatus
    kind: CaptureKind
    duration_ms: int
    captured_at: datetime
    source: CaptureSource
    language_hint: str | None = None
    # "degraded" means the quota was exceeded: stored and transcribed, AI
    # enrichment deferred. The capture is never refused (ADR-026).
    processing_mode: str = "normal"
    failure_code: str | None = None
    created_at: datetime
    processing_started_at: datetime | None = None
    processing_finished_at: datetime | None = None
    audio: AudioView | None = None
    transcript: TranscriptView | None = None
    entries: list[EntrySummary] = Field(default_factory=list)


class DeclaredCaptureView(CaptureView):
    upload: UploadInstructions | None = None
    quota_warning: str | None = None
