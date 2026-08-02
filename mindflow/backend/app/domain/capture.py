"""Capture state machine (Architecture.md §10.4).

The central resilience mechanism: a capture never fails outright. Every failure
path leads to a terminal state where the audio is still playable and, where the
transcription succeeded, the text is still readable.
"""

from __future__ import annotations

from app.domain.enums import AudioFormat, CaptureStatus
from app.domain.errors import (
    CaptureTooLongError,
    InvalidStateTransitionError,
    UnsupportedAudioFormatError,
)

S = CaptureStatus

_ALLOWED: dict[CaptureStatus, frozenset[CaptureStatus]] = {
    S.PENDING_UPLOAD: frozenset({S.UPLOADED, S.ABANDONED}),
    S.UPLOADED: frozenset({S.TRANSCRIBING, S.ABANDONED}),
    S.TRANSCRIBING: frozenset({S.TRANSCRIBED, S.TRANSCRIPTION_FAILED}),
    S.TRANSCRIBED: frozenset({S.EXTRACTING}),
    S.EXTRACTING: frozenset({S.COMPLETED, S.PARTIALLY_PROCESSED}),
    # Reprocessing paths — a degraded capture can always be retried.
    S.TRANSCRIPTION_FAILED: frozenset({S.TRANSCRIBING}),
    S.PARTIALLY_PROCESSED: frozenset({S.EXTRACTING}),
    S.COMPLETED: frozenset({S.EXTRACTING}),
    S.ABANDONED: frozenset(),
}


def can_transition(current: CaptureStatus, target: CaptureStatus) -> bool:
    return target in _ALLOWED[current]


def assert_transition(current: CaptureStatus, target: CaptureStatus) -> None:
    if not can_transition(current, target):
        raise InvalidStateTransitionError(
            f"Transition impossible de '{current}' vers '{target}'.",
            current_status=str(current),
            target_status=str(target),
        )


def terminal_status_for_failure(stage: str) -> CaptureStatus:
    """Where a capture lands when a given stage gives up.

    Never `abandoned`: the audio exists and stays reachable.
    """
    return {
        "transcribe": S.TRANSCRIPTION_FAILED,
        "extract": S.PARTIALLY_PROCESSED,
    }.get(stage, S.PARTIALLY_PROCESSED)


def validate_declaration(
    *,
    duration_ms: int,
    audio_format: str,
    max_duration_ms: int,
) -> AudioFormat:
    """Checks applied when a client declares a capture, before any upload."""
    if duration_ms <= 0:
        raise CaptureTooLongError("La durée doit être strictement positive.")
    if duration_ms > max_duration_ms:
        raise CaptureTooLongError(
            f"Durée de {duration_ms} ms supérieure à la limite de {max_duration_ms} ms.",
            max_duration_ms=max_duration_ms,
        )
    try:
        return AudioFormat(audio_format)
    except ValueError as exc:
        raise UnsupportedAudioFormatError(
            f"Format '{audio_format}' non pris en charge.",
            allowed=[fmt.value for fmt in AudioFormat],
        ) from exc


def object_key(account_id: str, capture_id: str, audio_format: AudioFormat) -> str:
    """Tenant-prefixed so a GDPR deletion is a prefix delete, and so a leaked
    signed URL cannot be walked sideways into another tenant."""
    return f"{account_id}/captures/{capture_id}.{audio_format.value}"
