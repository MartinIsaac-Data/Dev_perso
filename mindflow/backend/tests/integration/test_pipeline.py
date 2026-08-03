"""End-to-end pipeline (Sprint02 §7: the demonstration that closes the sprint).

    voice → Whisper → text → LLM → typed JSON → PostgreSQL

The second half of this file is the part that matters most: the failure paths.
Sprint02 asks for two demonstrations, and the one where the LLM is switched off
is as important as the happy path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

AUDIO = b"\x00\x01" * 8000  # placeholder bytes; the fake transcriber ignores them


async def declare(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "client_capture_id": str(uuid.uuid4()),
        "kind": "quick",
        "duration_ms": 14320,
        "audio_format": "m4a",
        "audio_bytes": len(AUDIO),
        "captured_at": datetime.now(UTC).isoformat(),
        "capture_timezone": "Europe/Paris",
        "source": "app",
        "language_hint": "fr",
        **overrides,
    }
    response = await client.post("/v1/captures", json=payload, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


async def upload(client: AsyncClient, declared: dict) -> None:
    """Follow the signed URL exactly as a real client would."""
    url = declared["upload"]["url"].replace("http://localhost:8000", "")
    response = await client.put(url, content=AUDIO, headers={"content-type": "audio/mp4"})
    assert response.status_code == 204, response.text


async def run_capture(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    declared = await declare(client, headers, **overrides)
    await upload(client, declared)
    completed = await client.post(f"/v1/captures/{declared['id']}/complete", headers=headers)
    assert completed.status_code == 202, completed.text
    detail = await client.get(f"/v1/captures/{declared['id']}", headers=headers)
    assert detail.status_code == 200
    return detail.json()["data"]


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
async def test_voice_to_structured_entries(client: AsyncClient, auth_headers) -> None:
    capture = await run_capture(client, auth_headers)

    assert capture["status"] == "completed"
    assert capture["transcript"]["text"]
    assert capture["transcript"]["language"] == "fr"
    assert capture["audio"]["available"] is True
    assert len(capture["entries"]) >= 1


async def test_the_account_is_provisioned_on_first_call(client: AsyncClient, auth_headers) -> None:
    response = await client.get("/v1/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["timezone"] == "Europe/Paris"
    assert body["role"] == "owner"


async def test_declaration_is_idempotent(client: AsyncClient, auth_headers) -> None:
    """ADR-009: replaying an upload declaration must not create a duplicate."""
    client_id = str(uuid.uuid4())
    first = await client.post(
        "/v1/captures",
        json={
            "client_capture_id": client_id,
            "duration_ms": 14320,
            "audio_format": "m4a",
            "captured_at": datetime.now(UTC).isoformat(),
            "capture_timezone": "Europe/Paris",
        },
        headers=auth_headers,
    )
    second = await client.post(
        "/v1/captures",
        json={
            "client_capture_id": client_id,
            "duration_ms": 14320,
            "audio_format": "m4a",
            "captured_at": datetime.now(UTC).isoformat(),
            "capture_timezone": "Europe/Paris",
        },
        headers=auth_headers,
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]

    listing = await client.get("/v1/captures", headers=auth_headers)
    assert len(listing.json()["data"]) == 1


async def test_completing_twice_is_idempotent(client: AsyncClient, auth_headers) -> None:
    declared = await declare(client, auth_headers)
    await upload(client, declared)
    first = await client.post(f"/v1/captures/{declared['id']}/complete", headers=auth_headers)
    second = await client.post(f"/v1/captures/{declared['id']}/complete", headers=auth_headers)
    assert first.status_code == 202
    assert second.status_code == 202


async def test_transcription_is_not_re_run_on_replay(client: AsyncClient, auth_headers) -> None:
    """The expensive stage must not repeat: one transcript, one ai_run."""
    capture = await run_capture(client, auth_headers)
    transcript_id = capture["transcript"]["id"]

    await client.post(f"/v1/captures/{capture['id']}/complete", headers=auth_headers)
    again = await client.get(f"/v1/captures/{capture['id']}", headers=auth_headers)
    assert again.json()["data"]["transcript"]["id"] == transcript_id
    assert len(again.json()["data"]["entries"]) == len(capture["entries"])


# --------------------------------------------------------------------------- #
# Typed extraction
# --------------------------------------------------------------------------- #
async def test_the_llm_output_becomes_typed_rows(client: AsyncClient, auth_headers) -> None:
    from app.domain.analysis import NoteAnalysis

    analysis = NoteAnalysis.model_validate(
        {
            "language": "fr",
            "summary": "Deux actions pour Vinci.",
            "tasks": [
                {
                    "title": "Rappeler le DAF de Vinci",
                    "body": None,
                    "due": {"expression": "jeudi", "kind": "due"},
                    "priority": "high",
                    "assignee": None,
                    "project_hint": "Vinci",
                    "confidence": 0.95,
                    "source_span": {"start": 0, "end": 40},
                }
            ],
            "ideas": [
                {
                    "title": "Refondre la proposition commerciale",
                    "body": None,
                    "project_hint": None,
                    "confidence": 0.8,
                    "source_span": {"start": 41, "end": 80},
                }
            ],
            "notes": [],
            "categories": ["client"],
            "people": ["DAF"],
            "projects": ["Vinci"],
            "tags": ["budget"],
            "dates": [{"expression": "jeudi", "kind": "due"}],
            "priority": "high",
            "overall_confidence": 0.9,
            "unprocessed_remainder": None,
        }
    )

    import app.infra.ai.factory as factory
    from app.infra.ai.analyzers import FakeAnalyzer

    original = factory.build_analyzer
    factory.build_analyzer = lambda settings: FakeAnalyzer(analysis)  # type: ignore[assignment]
    try:
        capture = await run_capture(client, auth_headers)
    finally:
        factory.build_analyzer = original  # type: ignore[assignment]

    entries = await client.get("/v1/entries", headers=auth_headers)
    data = entries.json()["data"]
    by_type = {e["entry_type"]: e for e in data}

    assert "task" in by_type
    assert by_type["task"]["title"] == "Rappeler le DAF de Vinci"
    assert by_type["task"]["task"]["priority"] == "high"
    # ADR-020: the model said "jeudi"; the deterministic resolver produced a date.
    assert by_type["task"]["task"]["due_at"] is not None
    assert by_type["task"]["task"]["due_raw_expression"] == "jeudi"
    assert "idea" in by_type
    assert "budget" in by_type["task"]["tags"]
    assert capture["status"] == "completed"


async def test_low_confidence_lands_in_needs_review(client: AsyncClient, auth_headers) -> None:
    from app.domain.analysis import NoteAnalysis

    analysis = NoteAnalysis.model_validate(
        {
            "language": "fr",
            "summary": "Quelque chose de flou.",
            "tasks": [],
            "ideas": [],
            "notes": [
                {
                    "title": "on verra pour le recrutement",
                    "body": None,
                    "entry_type": "note",
                    "confidence": 0.35,
                    "source_span": {"start": 0, "end": 20},
                }
            ],
            "categories": [],
            "people": [],
            "projects": [],
            "tags": [],
            "dates": [],
            "priority": "normal",
            "overall_confidence": 0.35,
            "unprocessed_remainder": None,
        }
    )

    import app.infra.ai.factory as factory
    from app.infra.ai.analyzers import FakeAnalyzer

    original = factory.build_analyzer
    factory.build_analyzer = lambda settings: FakeAnalyzer(analysis)  # type: ignore[assignment]
    try:
        await run_capture(client, auth_headers)
    finally:
        factory.build_analyzer = original  # type: ignore[assignment]

    entries = await client.get("/v1/entries?status=needs_review", headers=auth_headers)
    assert len(entries.json()["data"]) == 1


# --------------------------------------------------------------------------- #
# Failure paths — no failure destroys data (ADR-011)
# --------------------------------------------------------------------------- #
async def test_llm_outage_keeps_the_audio_and_the_transcript(
    client: AsyncClient, auth_headers
) -> None:
    """Sprint02's second demonstration: cut the LLM, lose nothing."""
    import app.infra.ai.factory as factory
    from app.domain.errors import ExtractionUnavailableError
    from app.domain.ports import AnalyzerPort

    class BrokenAnalyzer(AnalyzerPort):
        name = "broken"

        async def analyze(self, transcript, *, context):  # type: ignore[no-untyped-def]
            raise ExtractionUnavailableError("service down")

    original = factory.build_analyzer
    factory.build_analyzer = lambda settings: BrokenAnalyzer()  # type: ignore[assignment]
    try:
        capture = await run_capture(client, auth_headers)
    finally:
        factory.build_analyzer = original  # type: ignore[assignment]

    assert capture["status"] == "partially_processed"
    assert capture["transcript"]["text"], "the transcript must survive"
    assert capture["audio"]["available"] is True, "the audio must survive"
    assert capture["failure_code"] == "extraction_unavailable"


async def test_a_model_refusal_is_neutral_and_keeps_everything(
    client: AsyncClient, auth_headers
) -> None:
    """AI.md §9.2: a content refusal is never retried and never judged."""
    import app.infra.ai.factory as factory
    from app.domain.errors import LlmRefusalError
    from app.domain.ports import AnalyzerPort

    class RefusingAnalyzer(AnalyzerPort):
        name = "refusing"

        async def analyze(self, transcript, *, context):  # type: ignore[no-untyped-def]
            raise LlmRefusalError("declined")

    original = factory.build_analyzer
    factory.build_analyzer = lambda settings: RefusingAnalyzer()  # type: ignore[assignment]
    try:
        capture = await run_capture(client, auth_headers)
    finally:
        factory.build_analyzer = original  # type: ignore[assignment]

    assert capture["status"] == "partially_processed"
    assert capture["failure_code"] == "content_not_processed"
    assert capture["transcript"]["text"]


async def test_transcription_outage_keeps_the_audio(client: AsyncClient, auth_headers) -> None:
    import app.infra.ai.factory as factory
    from app.domain.errors import TranscriptionUnavailableError
    from app.domain.ports import TranscriberPort

    class BrokenTranscriber(TranscriberPort):
        name = "broken"

        async def transcribe(self, audio, *, media_type, language_hint=None):  # type: ignore[no-untyped-def]
            raise TranscriptionUnavailableError("gpu down")

    original = factory.build_transcriber
    factory.build_transcriber = lambda settings: BrokenTranscriber()  # type: ignore[assignment]
    try:
        capture = await run_capture(client, auth_headers)
    finally:
        factory.build_transcriber = original  # type: ignore[assignment]

    assert capture["status"] == "transcription_failed"
    assert capture["audio"]["available"] is True, "the audio must remain playable"
    assert capture["transcript"] is None


async def test_a_hallucinated_transcript_does_not_become_an_entry(
    client: AsyncClient, auth_headers
) -> None:
    """The guard chain must stop invented text before it reaches the user."""
    import app.infra.ai.factory as factory
    from app.infra.ai.transcribers import FakeTranscriber

    original = factory.build_transcriber
    factory.build_transcriber = lambda settings: FakeTranscriber(  # type: ignore[assignment]
        text="Sous-titres réalisés par la communauté d'Amara.org"
    )
    try:
        capture = await run_capture(client, auth_headers)
    finally:
        factory.build_transcriber = original  # type: ignore[assignment]

    assert capture["status"] == "partially_processed"
    assert capture["failure_code"] == "empty_transcript"
    assert capture["entries"] == []


# --------------------------------------------------------------------------- #
# Quota — never blocks a capture (ADR-026)
# --------------------------------------------------------------------------- #
async def test_over_quota_the_capture_is_accepted_in_degraded_mode(
    client: AsyncClient, auth_headers
) -> None:
    from sqlalchemy import text as sql
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import TEST_DATABASE_URL

    await client.get("/v1/me", headers=auth_headers)  # provision the account

    # Written through the admin connection: the application role is NOBYPASSRLS
    # by design (ADR-033), so it cannot seed another tenant's counter.
    admin = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with admin.begin() as conn:
        await conn.execute(
            sql(
                "INSERT INTO usage_counter (account_id, metric, period_start, value) "
                "SELECT account_id, 'quick_captures', date_trunc('month', now())::date, 999 "
                "FROM app_user ORDER BY created_at DESC LIMIT 1 "
                "ON CONFLICT (account_id, metric, period_start) DO UPDATE SET value = 999"
            )
        )
    await admin.dispose()

    declared = await declare(client, auth_headers)
    assert declared["processing_mode"] == "degraded"
    assert declared["quota_warning"] is not None
    assert declared["upload"] is not None, "the capture is still accepted and uploadable"


# --------------------------------------------------------------------------- #
# Isolation, at the API level
# --------------------------------------------------------------------------- #
async def test_a_user_cannot_read_another_users_capture(
    client: AsyncClient, auth_headers, other_auth_headers
) -> None:
    capture = await run_capture(client, auth_headers)

    response = await client.get(f"/v1/captures/{capture['id']}", headers=other_auth_headers)
    # 404, not 403: a 403 would confirm the resource exists (API.md §3.1).
    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"


async def test_entries_are_scoped_to_the_caller(
    client: AsyncClient, auth_headers, other_auth_headers
) -> None:
    await run_capture(client, auth_headers)
    response = await client.get("/v1/entries", headers=other_auth_headers)
    assert response.json()["data"] == []
