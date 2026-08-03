"""Error taxonomy (Architecture.md §10.2, API.md §6.2).

The domain raises these; the API layer is the only place that knows about HTTP.
Every error carries a *stable applicative code* — that code, not the HTTP status,
is the contract clients branch on.
"""

from __future__ import annotations

from typing import Any


class MindFlowError(Exception):
    """Root of every expected error. Anything else is a bug and becomes a 500."""

    code = "internal_error"
    title = "Erreur interne"
    status = 500

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)

    def as_problem(self) -> dict[str, Any]:
        problem: dict[str, Any] = {
            "type": f"https://api.mindflow.ai/errors/{self.code}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }
        problem.update(self.extra)
        return problem


# --------------------------------------------------------------------------- #
# 4xx — the user can act
# --------------------------------------------------------------------------- #
class DomainError(MindFlowError):
    status = 400


class ValidationError(DomainError):
    code = "validation_failed"
    title = "Requête invalide"
    status = 422


class NotFoundError(DomainError):
    code = "resource_not_found"
    title = "Ressource introuvable"
    status = 404


class ConflictError(DomainError):
    code = "duplicate_resource"
    title = "Conflit"
    status = 409


class VersionConflictError(ConflictError):
    code = "entry_version_conflict"
    title = "La ressource a été modifiée ailleurs"

    def __init__(self, current_version: int, **extra: Any) -> None:
        super().__init__(
            detail=(
                f"La version fournie ne correspond pas à la version courante ({current_version})."
            ),
            current_version=current_version,
            **extra,
        )


class ForbiddenError(DomainError):
    code = "insufficient_scope"
    title = "Accès refusé"
    status = 403


class PermissionDeniedError(ForbiddenError):
    """The caller is authenticated and simply may not do this (Phase 4).

    Distinct from `ForbiddenError` by its applicative code, because the two mean
    different things to a client: an insufficient *scope* is a token problem to
    be solved by re-authenticating, an insufficient *role* is an organisational
    problem to be solved by asking an administrator. Sending the same code for
    both would make the client offer the wrong remedy.
    """

    code = "permission_denied"
    title = "Permission insuffisante"


class InvalidStateTransitionError(DomainError):
    code = "invalid_state_transition"
    title = "Transition d'état invalide"
    status = 400


class QuotaExceededError(DomainError):
    code = "quota_exceeded"
    title = "Quota du plan atteint"
    status = 402


class CaptureTooLongError(ValidationError):
    code = "capture_too_long"
    title = "Capture trop longue"


class UnsupportedAudioFormatError(ValidationError):
    code = "unsupported_audio_format"
    title = "Format audio non pris en charge"


class CaptureAlreadyCompletedError(ConflictError):
    code = "capture_already_completed"
    title = "Capture déjà finalisée"


class AudioUnavailableError(NotFoundError):
    code = "capture_audio_unavailable"
    title = "Audio indisponible"


# --------------------------------------------------------------------------- #
# 401 — authentication
# --------------------------------------------------------------------------- #
class AuthError(MindFlowError):
    code = "unauthenticated"
    title = "Authentification requise"
    status = 401


class TokenExpiredError(AuthError):
    code = "token_expired"
    title = "Jeton expiré"


class TokenInvalidError(AuthError):
    code = "token_invalid"
    title = "Jeton invalide"


# --------------------------------------------------------------------------- #
# 5xx — the user can do nothing
# --------------------------------------------------------------------------- #
class InfrastructureError(MindFlowError):
    code = "internal_error"
    title = "Erreur interne"
    status = 500


class StorageError(InfrastructureError):
    code = "storage_error"
    title = "Erreur de stockage"


# --------------------------------------------------------------------------- #
# 502/503 — upstream dependency
#
# These never destroy data: a capture whose transcription or extraction failed
# keeps its audio and lands in a terminal-but-degraded state (ADR-011).
# --------------------------------------------------------------------------- #
class UpstreamError(MindFlowError):
    code = "service_unavailable"
    title = "Service indisponible"
    status = 503


class TranscriptionUnavailableError(UpstreamError):
    code = "transcription_unavailable"
    title = "Transcription indisponible"


class ExtractionUnavailableError(UpstreamError):
    code = "extraction_unavailable"
    title = "Analyse indisponible"


class LlmRefusalError(UpstreamError):
    """The model declined to process the content.

    Deliberately *not* retried — retrying would be circumvention. The capture is
    kept in `partially_processed` with its transcript intact (AI.md §9.2).
    """

    code = "content_not_processed"
    title = "Contenu non structuré automatiquement"
    status = 200


class LlmSchemaViolationError(UpstreamError):
    code = "llm_schema_violation"
    title = "Réponse du modèle non conforme au schéma"
