"""Shared response envelopes (API.md §3.2).

Collections are always wrapped in `data` with a `page` object: a bare array at
the root leaves no room to add metadata later without a breaking change.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 50


class Envelope(BaseModel, Generic[T]):
    data: T


class Collection(BaseModel, Generic[T]):
    data: list[T]
    page: Page = Field(default_factory=Page)


class Problem(BaseModel):
    """RFC 9457 — documented so it appears in the OpenAPI schema."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "https://api.mindflow.ai/errors/entry_version_conflict",
                "title": "La ressource a été modifiée ailleurs",
                "status": 409,
                "detail": "La version fournie ne correspond pas à la version courante (5).",
                "instance": "/v1/entries/018f2c20-…",
                "code": "entry_version_conflict",
                "request_id": "req_01J8XKQ2M9",
                "current_version": 5,
            }
        }
    )

    type: str
    title: str
    status: int
    detail: str
    code: str
    instance: str | None = None
    request_id: str | None = None


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": Problem, "description": "Jeton absent, invalide ou expiré"},
    403: {"model": Problem, "description": "Périmètre insuffisant"},
    404: {"model": Problem, "description": "Ressource introuvable ou hors périmètre"},
    422: {"model": Problem, "description": "Validation échouée"},
}
