"""A live meeting, end to end, against a real database and a scripted model.

The unit tests cover the arithmetic — stitching, cueing, deduplication. These
cover the promise the service makes and the domain cannot: **a live feature
degrades to a recording, never to a failure.** Somebody is in a room with other
people; if the speech provider hiccups or the model is slow, the meeting does
not pause to wait for us.

So the tests that matter most here are the unhappy ones. `test_a_failed_block…`
and `test_a_failed_analysis…` are the two that would let this feature lose what
somebody said, and they are the reason the service catches where it would
normally be tempting to raise.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.config import Settings
from app.domain.ports import (
    AiUsage,
    ChatChunk,
    ChatPort,
    ChatRequest,
    TranscriberPort,
    TranscriptionResult,
)
from app.infra.db.models.enterprise import MeetingSession
from app.services.identity_service import Principal
from app.services.meeting_service import MeetingService
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

# Long enough to clear the cue threshold on its own.
LONG_PASSAGE = " ".join(["on parle du sujet"] * 25)


class ScriptedChat(ChatPort):
    """Answers with a prepared payload, so the service is what is under test."""

    name = "scripted"
    supports_json_schema = True

    def __init__(self, *payloads: Any, refused: bool = False) -> None:
        self.model = "scripted"
        self._payloads = [
            item if isinstance(item, str) else json.dumps(item) for item in payloads
        ] or ["{}"]
        self._refused = refused
        self.calls = 0
        self.blocks: list[str] = []

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.blocks.append(request.messages[-1].content)
        index = min(self.calls, len(self._payloads) - 1)
        self.calls += 1
        yield ChatChunk(text=self._payloads[index])
        yield ChatChunk(
            done=True,
            usage=AiUsage(model=self.model),
            finish_reason="refusal" if self._refused else "stop",
        )


class BrokenChat(ChatPort):
    name = "broken"

    def __init__(self) -> None:
        self.model = "broken"
        self.calls = 0

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.calls += 1
        raise RuntimeError("provider down")
        yield ChatChunk()  # pragma: no cover - unreachable, satisfies the generator


class ScriptedTranscriber(TranscriberPort):
    name = "scripted"

    def __init__(self, *texts: str, fails: bool = False) -> None:
        self._texts = list(texts) or [""]
        self._fails = fails
        self.calls = 0

    async def transcribe(
        self, audio: bytes, *, media_type: str, language_hint: str | None = None
    ) -> TranscriptionResult:
        self.calls += 1
        if self._fails:
            raise RuntimeError("stt down")
        index = min(self.calls - 1, len(self._texts) - 1)
        return TranscriptionResult(
            text=self._texts[index],
            language="fr",
            confidence=0.9,
            engine="scripted",
            engine_version="1",
            duration_ms=30000,
        )


def _live(*suggestions: dict[str, Any]) -> dict[str, Any]:
    return {"suggestions": list(suggestions)}


def _action(text: str, owner: str | None = None) -> dict[str, Any]:
    return {"kind": "action", "text": text, "owner": owner, "confidence": 0.9}


def _principal(tenant: dict[str, Any]) -> Principal:
    return Principal(
        user_id=tenant["user_id"],
        account_id=tenant["account_id"],
        auth_subject="",
        email="test@example.test",
        timezone="Europe/Paris",
        locale="fr-FR",
        role="owner",
    )


@pytest_asyncio.fixture
async def room(session_factory, two_tenants, api_settings):  # type: ignore[no-untyped-def]
    """A tenant-scoped session plus the principal that owns it.

    Built by hand rather than through the API because these tests are about the
    service: going through HTTP would put the transport between the assertion
    and the behaviour it is checking.
    """
    tenant, other = two_tenants
    session = session_factory()
    await session.execute(
        text("SELECT set_config('app.account_id', :aid, true)"),
        {"aid": str(tenant["account_id"])},
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :uid, true)"),
        {"uid": str(tenant["user_id"])},
    )
    yield session, _principal(tenant), _principal(other), api_settings
    await session.rollback()
    await session.close()


def _service(
    session: Any,
    principal: Principal,
    settings: Settings,
    *,
    chat: ChatPort | None = None,
    transcriber: TranscriberPort | None = None,
) -> MeetingService:
    return MeetingService(
        session,
        principal=principal,
        settings=settings,
        chat=chat,
        transcriber=transcriber,
    )


class TestLifecycle:
    async def test_opening_creates_a_live_session(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        service = _service(db_session, principal, api_settings)

        meeting = await service.open(title="Point hebdo")

        assert meeting.status == "live"
        assert meeting.title == "Point hebdo"
        assert meeting.live_transcript == ""
        assert meeting.analysed_words == 0

    async def test_a_second_live_meeting_is_refused(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # One microphone, one meeting. Two would produce two half transcripts
        # of the same room, which is worse than refusing.
        service = _service(db_session, principal, api_settings)
        await service.open()

        with pytest.raises(Exception, match="déjà en cours"):
            await service.open()

    async def test_a_meeting_can_be_resumed_after_the_app_is_killed(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # The transcript lives on the server, so relaunching offers to resume
        # rather than silently starting over.
        service = _service(db_session, principal, api_settings)
        opened = await service.open(title="Comité")

        resumed = await _service(db_session, principal, api_settings).live()

        assert resumed is not None
        assert resumed.id == opened.id

    async def test_abandoning_leaves_nothing_behind(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        service = _service(db_session, principal, api_settings)
        meeting = await service.open()

        await service.abandon(meeting.id)

        assert (await service.get(meeting.id)).status == "abandoned"
        assert await service.live() is None


class TestIngest:
    async def test_text_accumulates_without_a_model_call(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # Short windows are not analysed. This is the whole cost discipline: a
        # forty-five minute meeting must not become two hundred calls.
        chat = ScriptedChat(_live())
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()

        await service.append_text(meeting.id, "bonjour à tous")
        await service.append_text(meeting.id, "on commence")

        assert chat.calls == 0
        assert "bonjour à tous on commence" in (await service.get(meeting.id)).live_transcript

    async def test_a_commitment_triggers_an_analysis_early(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        chat = ScriptedChat(_live(_action("relancer le DAF", owner="Marie")))
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()

        _, added = await service.append_text(
            meeting.id,
            " ".join(["on discute du budget"] * 8) + " il faut que Marie relance le DAF",
        )

        assert chat.calls == 1
        assert [item.text for item in added] == ["relancer le DAF"]
        assert (await service.get(meeting.id)).live_suggestions[0]["owner"] == "Marie"

    async def test_the_same_suggestion_is_not_surfaced_twice(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # The model re-proposes what it already proposed, because the sentence
        # is still in its window. The panel must not show it twice.
        chat = ScriptedChat(
            _live(_action("relancer le DAF")),
            _live(_action("Relancer le DAF")),
        )
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()

        await service.append_text(meeting.id, LONG_PASSAGE)
        # A *different* passage: an identical one would be swallowed by the
        # stitcher, which is correct and would test nothing here.
        _, second = await service.append_text(meeting.id, " ".join(["autre chose dite"] * 25))

        assert chat.calls == 2
        assert second == []
        assert len((await service.get(meeting.id)).live_suggestions) == 1

    async def test_only_the_new_window_is_sent_to_the_model(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # Re-sending the whole meeting every time would make the cost grow with
        # the square of its length.
        chat = ScriptedChat(_live(), _live())
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()

        await service.append_text(meeting.id, LONG_PASSAGE)
        await service.append_text(meeting.id, " ".join(["une suite différente"] * 25))

        assert "une suite différente" in chat.blocks[1]
        assert "on parle du sujet" not in chat.blocks[1]

    async def test_audio_is_transcribed_and_folded_in(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        transcriber = ScriptedTranscriber("le budget est validé")
        service = _service(
            db_session, principal, api_settings, chat=ScriptedChat(_live()), transcriber=transcriber
        )
        meeting = await service.open()

        await service.append_audio(meeting.id, b"\x00\x01", media_type="audio/webm")

        assert transcriber.calls == 1
        assert (await service.get(meeting.id)).live_transcript == "le budget est validé"

    async def test_overlapping_blocks_do_not_stutter(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # Blocks overlap by design (ADR-013), so the seam arrives twice.
        transcriber = ScriptedTranscriber(
            "on parle du budget et on décide de reporter",
            "on décide de reporter au 12 janvier",
        )
        service = _service(
            db_session, principal, api_settings, chat=ScriptedChat(_live()), transcriber=transcriber
        )
        meeting = await service.open()

        await service.append_audio(meeting.id, b"\x00", media_type="audio/webm")
        await service.append_audio(meeting.id, b"\x01", media_type="audio/webm")

        transcript = (await service.get(meeting.id)).live_transcript
        assert transcript == "on parle du budget et on décide de reporter au 12 janvier"


class TestDegradation:
    async def test_a_failed_block_does_not_end_the_meeting(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # The room did not stop talking. Losing one block is a gap in the
        # transcript; raising would end the meeting.
        service = _service(
            db_session,
            principal,
            api_settings,
            chat=ScriptedChat(_live()),
            transcriber=ScriptedTranscriber(fails=True),
        )
        meeting = await service.open()

        _, added = await service.append_audio(meeting.id, b"\x00", media_type="audio/webm")

        assert added == []
        assert (await service.get(meeting.id)).status == "live"

    async def test_a_failed_analysis_retries_the_same_window(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # `analysed_words` must not advance on failure. A window silently
        # skipped is a commitment silently lost.
        broken = BrokenChat()
        service = _service(db_session, principal, api_settings, chat=broken)
        meeting = await service.open()

        await service.append_text(meeting.id, LONG_PASSAGE)

        stored = await service.get(meeting.id)
        assert broken.calls == 1
        assert stored.analysed_words == 0
        assert stored.status == "live"

    async def test_a_refusal_advances_the_window_instead_of_looping(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # A refusal is not a transient failure: retrying the same window would
        # be refused again, for ever.
        chat = ScriptedChat(_live(), refused=True)
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()

        await service.append_text(meeting.id, LONG_PASSAGE)

        assert (await service.get(meeting.id)).analysed_words > 0

    async def test_a_meeting_with_no_model_still_records(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        service = _service(db_session, principal, api_settings, chat=None)
        meeting = await service.open()

        await service.append_text(meeting.id, LONG_PASSAGE)

        assert (await service.get(meeting.id)).live_transcript.startswith("on parle")


class TestClosing:
    async def test_closing_produces_a_report(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        chat = ScriptedChat(
            _live(_action("relancer le DAF")),
            {
                "summary": "Point budget.",
                "decisions": ["Reporter au 12 janvier"],
                "actions": [{"text": "relancer le DAF", "owner": "Marie", "due": "2026-06-12"}],
                "open_questions": ["Qui valide le devis ?"],
            },
        )
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open(title="Point hebdo")
        await service.append_text(meeting.id, LONG_PASSAGE)

        closed, report = await service.close(meeting.id)

        assert closed.status == "ended"
        assert closed.ended_at is not None
        assert report.summary == "Point budget."
        assert report.decisions == ["Reporter au 12 janvier"]
        assert report.actions[0]["owner"] == "Marie"
        assert report.degraded is False

    async def test_closing_runs_one_last_analysis(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # The last thirty seconds are where people agree what happens next.
        chat = ScriptedChat(
            _live(_action("envoyer le compte rendu")),
            {"summary": "Fin de réunion.", "decisions": [], "actions": [], "open_questions": []},
        )
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()
        # Long enough to be worth summarising, and ending on a commitment that
        # no earlier pass has seen.
        await service.append_text(
            meeting.id,
            " ".join(["on relit le compte rendu"] * 8)
            + " je m'en occupe avant vendredi et j'envoie le CR",
        )

        closed, _ = await service.close(meeting.id)

        assert chat.calls == 2  # the closing pass, then the summary
        assert [row["text"] for row in closed.live_suggestions] == ["envoyer le compte rendu"]

    async def test_a_failed_summary_still_reports_what_was_found(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room

        # The live pass already found real things. A degraded report that lists
        # them is far more useful than an apology — and it says it is degraded.
        class FailsOnSummary(ChatPort):
            name = "half-broken"
            supports_json_schema = True

            def __init__(self) -> None:
                self.model = "half-broken"
                self.calls = 0

            async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
                self.calls += 1
                if "transcription" in request.messages[-1].content:
                    raise RuntimeError("summary provider down")
                yield ChatChunk(text=json.dumps(_live(_action("relancer le DAF"))))
                yield ChatChunk(done=True, usage=AiUsage(model=self.model), finish_reason="stop")

        service = _service(db_session, principal, api_settings, chat=FailsOnSummary())
        meeting = await service.open()
        await service.append_text(meeting.id, LONG_PASSAGE)

        closed, report = await service.close(meeting.id)

        assert closed.status == "ended"
        assert report.degraded is True
        assert report.reason != ""
        assert [action["text"] for action in report.actions] == ["relancer le DAF"]

    async def test_a_meeting_too_short_to_summarise_says_so(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        # Three sentences of prose about a meeting that produced nothing is
        # worse than saying there was nothing.
        chat = ScriptedChat(_live())
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()
        await service.append_text(meeting.id, "bonjour, on annule")

        _, report = await service.close(meeting.id)

        assert report.degraded is True
        assert "courte" in report.reason

    async def test_a_closed_meeting_refuses_more_audio(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        chat = ScriptedChat(_live(), {"summary": "x"})
        service = _service(db_session, principal, api_settings, chat=chat)
        meeting = await service.open()
        await service.append_text(meeting.id, LONG_PASSAGE)
        await service.close(meeting.id)

        with pytest.raises(Exception, match="terminée"):
            await service.append_text(meeting.id, "encore un mot")


class TestIsolation:
    async def test_another_persons_meeting_is_not_found(self, room: Any) -> None:
        db_session, principal, other_principal, api_settings = room
        # A meeting is personal to the person recording it, so somebody else's
        # is not merely forbidden — it is not theirs to see.
        mine = await _service(db_session, principal, api_settings).open()

        with pytest.raises(Exception, match="introuvable"):
            await _service(db_session, other_principal, api_settings).get(mine.id)

    async def test_the_row_carries_the_tenant(self, room: Any) -> None:
        db_session, principal, _other, api_settings = room
        meeting = await _service(db_session, principal, api_settings).open()

        row = (
            await db_session.execute(select(MeetingSession).where(MeetingSession.id == meeting.id))
        ).scalar_one()
        assert row.account_id == principal.account_id
        assert row.user_id == principal.user_id
