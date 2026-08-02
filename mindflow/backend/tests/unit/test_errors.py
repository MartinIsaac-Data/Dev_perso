from __future__ import annotations

import pytest

from app.domain import errors


def test_problem_document_shape() -> None:
    problem = errors.NotFoundError("Aucune capture 018f").as_problem()
    assert problem == {
        "type": "https://api.mindflow.ai/errors/resource_not_found",
        "title": "Ressource introuvable",
        "status": 404,
        "detail": "Aucune capture 018f",
        "code": "resource_not_found",
    }


def test_extra_fields_are_merged_into_the_problem() -> None:
    problem = errors.QuotaExceededError(
        "Quota atteint", metric="quick_captures", used=60, limit=60
    ).as_problem()
    assert problem["metric"] == "quick_captures"
    assert problem["status"] == 402


def test_version_conflict_exposes_the_current_version() -> None:
    problem = errors.VersionConflictError(current_version=5).as_problem()
    assert problem["current_version"] == 5
    assert problem["code"] == "entry_version_conflict"


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (errors.CaptureTooLongError, "capture_too_long", 422),
        (errors.QuotaExceededError, "quota_exceeded", 402),
        (errors.TokenExpiredError, "token_expired", 401),
        (errors.TranscriptionUnavailableError, "transcription_unavailable", 503),
        (errors.LlmSchemaViolationError, "llm_schema_violation", 503),
    ],
)
def test_codes_and_statuses_match_the_api_contract(
    error: type[errors.MindFlowError], code: str, status: int
) -> None:
    assert error.code == code
    assert error.status == status


def test_llm_refusal_is_not_an_http_error() -> None:
    """A refusal degrades the entry, it does not fail the request (AI.md §9.2)."""
    assert errors.LlmRefusalError.status == 200
    assert errors.LlmRefusalError.code == "content_not_processed"


def test_every_error_carries_a_distinct_stable_code() -> None:
    classes = [
        obj
        for obj in vars(errors).values()
        if isinstance(obj, type) and issubclass(obj, errors.MindFlowError)
    ]
    codes = [c.code for c in classes]
    # Subclasses may deliberately reuse a parent code (DomainError/MindFlowError);
    # what matters is that no two *leaf* errors collide accidentally.
    leaves = [
        c for c in classes if not any(other is not c and issubclass(other, c) for other in classes)
    ]
    leaf_codes = [c.code for c in leaves]
    assert len(leaf_codes) == len(set(leaf_codes)), sorted(codes)
