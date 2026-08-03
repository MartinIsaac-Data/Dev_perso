"""The capture pipeline (Architecture.md §3.4, §4.1).

    audio → Whisper → text → LLM → typed JSON → PostgreSQL

Two properties matter more than anything else here, and both are tested:

1. **Every stage is idempotent and resumes from persisted state.** A failure
   during extraction must not re-run transcription — the most expensive step.
2. **No failure destroys data.** Every error path ends in a terminal state where
   the audio is still playable and, where transcription succeeded, the text is
   still readable (ADR-011, Architecture.md §10.4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.capture import assert_transition, terminal_status_for_failure
from app.domain.enums import AiOperation, AiRunStatus, CaptureStatus
from app.domain.errors import (
    ExtractionUnavailableError,
    LlmRefusalError,
    LlmSchemaViolationError,
    TranscriptionUnavailableError,
)
from app.domain.ports import AnalysisContext, AnalyzerPort, ObjectStoragePort, TranscriberPort
from app.infra.ai.guards import apply_transcription_guards
from app.infra.db.models.core import AiRun, Capture, Entry, Transcript, TranscriptSegment
from app.infra.db.session import set_tenant_context, tenant_session
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.analysis_mapper import AnalysisMapper

log = get_logger("pipeline")

_WEEKDAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


class CapturePipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: ObjectStoragePort,
        transcriber: TranscriberPort,
        analyzer: AnalyzerPort,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._transcriber = transcriber
        self._analyzer = analyzer

    async def run(self, capture_id: uuid.UUID, account_id: uuid.UUID) -> CaptureStatus:
        """Drive one capture as far as it can go, resuming where it stopped."""
        async with tenant_session(account_id) as session:
            capture = await self._load(session, capture_id)
            if capture is None:
                log.warning("pipeline.capture_missing", capture_id=str(capture_id))
                return CaptureStatus.ABANDONED

            status = CaptureStatus(capture.status)
            if status in (CaptureStatus.COMPLETED, CaptureStatus.ABANDONED):
                return status  # already done — replaying is a no-op

            if capture.processing_started_at is None:
                capture.processing_started_at = datetime.now(UTC)

        # Stage 1 — transcription. Skipped when a current transcript exists.
        transcript_text = await self._stage_transcribe(capture_id, account_id)
        if transcript_text is None:
            return CaptureStatus.TRANSCRIPTION_FAILED

        # A guarded-empty transcript is a legitimate outcome, not a failure:
        # there was nothing to hear (AI.md §3.2).
        if not transcript_text.strip():
            return await self._finish(
                capture_id, account_id, CaptureStatus.PARTIALLY_PROCESSED, "empty_transcript"
            )

        # Stage 2 — extraction.
        return await self._stage_extract(capture_id, account_id, transcript_text)

    # -- stages ------------------------------------------------------------
    async def _stage_transcribe(self, capture_id: uuid.UUID, account_id: uuid.UUID) -> str | None:
        async with tenant_session(account_id) as session:
            capture = await self._load(session, capture_id)
            assert capture is not None

            existing = await self._current_transcript(session, capture_id)
            if existing is not None:
                return existing.text  # idempotent: never re-transcribe

            if CaptureStatus(capture.status) in (
                CaptureStatus.UPLOADED,
                CaptureStatus.TRANSCRIPTION_FAILED,
            ):
                assert_transition(CaptureStatus(capture.status), CaptureStatus.TRANSCRIBING)
                capture.status = CaptureStatus.TRANSCRIBING
            object_key = capture.audio_object_key
            language_hint = capture.language_hint
            audio_format = capture.audio_format or "m4a"

        if not object_key:
            await self._fail(capture_id, account_id, "transcribe", "missing_audio")
            return None

        try:
            audio = await self._storage.download(object_key)
            media_type = {
                "m4a": "audio/mp4",
                "opus": "audio/ogg",
                "wav": "audio/wav",
                "mp3": "audio/mpeg",
                "webm": "audio/webm",
            }.get(audio_format, "audio/mp4")
            raw = await self._transcriber.transcribe(
                audio, media_type=media_type, language_hint=language_hint
            )
            # Applied here, once, for every engine. Whisper fabricates fluent
            # text on near-silent input and the result looks perfect — it must
            # never reach the extraction stage.
            result = apply_transcription_guards(raw)
        except TranscriptionUnavailableError as exc:
            log.error("pipeline.transcription_failed", capture_id=str(capture_id))
            await self._fail(capture_id, account_id, "transcribe", exc.code)
            return None
        except Exception as exc:
            log.error(
                "pipeline.transcription_error",
                capture_id=str(capture_id),
                error=type(exc).__name__,
            )
            await self._fail(capture_id, account_id, "transcribe", "transcription_error")
            return None

        async with tenant_session(account_id) as session:
            capture = await self._load(session, capture_id)
            assert capture is not None

            transcript = Transcript(
                id=uuid.uuid4(),
                account_id=account_id,
                capture_id=capture_id,
                engine=result.engine,
                engine_version=result.engine_version,
                is_fallback=result.is_fallback,
                language=result.language,
                confidence=result.confidence,
                text=result.text,
                word_count=result.word_count,
                words={"words": result.words} if result.words else None,
                revision=1,
                is_current=True,
            )
            session.add(transcript)
            await session.flush()

            for index, segment in enumerate(result.segments):
                session.add(
                    TranscriptSegment(
                        id=uuid.uuid4(),
                        account_id=account_id,
                        transcript_id=transcript.id,
                        seq=index,
                        start_ms=segment.start_ms,
                        end_ms=max(segment.end_ms, segment.start_ms + 1),
                        speaker_label=segment.speaker_label,
                        text=segment.text,
                        confidence=segment.confidence,
                    )
                )

            session.add(
                AiRun(
                    id=uuid.uuid4(),
                    account_id=account_id,
                    capture_id=capture_id,
                    operation=AiOperation.TRANSCRIBE,
                    model_id=result.engine_version,
                    provider=result.engine,
                    status=AiRunStatus.SUCCEEDED,
                    latency_ms=None,
                )
            )
            capture.status = CaptureStatus.TRANSCRIBED

        log.info("capture.transcription.completed", capture_id=str(capture_id))
        return result.text

    async def _stage_extract(
        self, capture_id: uuid.UUID, account_id: uuid.UUID, transcript_text: str
    ) -> CaptureStatus:
        async with tenant_session(account_id) as session:
            capture = await self._load(session, capture_id)
            assert capture is not None

            # Quota exceeded: audio and transcript are kept, enrichment deferred
            # (ADR-026). The capture is never lost for a commercial reason.
            if capture.processing_mode == "degraded":
                capture.status = CaptureStatus.PARTIALLY_PROCESSED
                capture.processing_finished_at = datetime.now(UTC)
                return CaptureStatus.PARTIALLY_PROCESSED

            already = await session.execute(
                select(Entry.id).where(Entry.capture_id == capture_id).limit(1)
            )
            if already.scalar_one_or_none() is not None:
                return CaptureStatus(capture.status)  # idempotent

            if CaptureStatus(capture.status) is CaptureStatus.TRANSCRIBED:
                capture.status = CaptureStatus.EXTRACTING

            context = await self._build_context(session, capture)
            user_id = capture.user_id
            captured_at = capture.captured_at
            timezone = capture.capture_timezone

        try:
            analysis_result = await self._analyzer.analyze(transcript_text, context=context)
        except LlmRefusalError:
            log.info("capture.extraction.refused", capture_id=str(capture_id))
            await self._record_run(
                capture_id, account_id, AiRunStatus.REFUSED, "content_not_processed"
            )
            return await self._finish(
                capture_id, account_id, CaptureStatus.PARTIALLY_PROCESSED, "content_not_processed"
            )
        except LlmSchemaViolationError as exc:
            await self._record_run(capture_id, account_id, AiRunStatus.SCHEMA_VIOLATION, exc.code)
            return await self._finish(
                capture_id, account_id, CaptureStatus.PARTIALLY_PROCESSED, exc.code
            )
        except ExtractionUnavailableError as exc:
            await self._record_run(capture_id, account_id, AiRunStatus.FAILED, exc.code)
            return await self._finish(
                capture_id, account_id, CaptureStatus.PARTIALLY_PROCESSED, exc.code
            )

        async with tenant_session(account_id) as session:
            capture = await self._load(session, capture_id)
            assert capture is not None

            usage = analysis_result.usage
            ai_run = AiRun(
                id=uuid.uuid4(),
                account_id=account_id,
                capture_id=capture_id,
                prompt_name=analysis_result.prompt_name,
                prompt_version=analysis_result.prompt_version,
                operation=AiOperation.EXTRACT,
                model_id=usage.model,
                provider=self._analyzer.name,
                status=AiRunStatus.SUCCEEDED,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_micro_eur=usage.cost_micro_eur,
                latency_ms=usage.latency_ms,
            )
            session.add(ai_run)
            await session.flush()

            mapper = AnalysisMapper(session, account_id=account_id, user_id=user_id)
            mapped = await mapper.map(
                analysis_result.analysis,
                capture_id=capture_id,
                captured_at=captured_at,
                timezone=timezone,
                ai_run_id=ai_run.id,
            )
            session.add_all(mapped.entries)
            await session.flush()
            session.add_all(mapped.tasks)
            session.add_all(mapped.entry_tags)

            capture.status = CaptureStatus.COMPLETED
            capture.processing_finished_at = datetime.now(UTC)
            if capture.processing_started_at:
                metrics.capture_time_to_publish_seconds.observe(
                    (capture.processing_finished_at - capture.processing_started_at).total_seconds()
                )

        log.info(
            "capture.completed",
            capture_id=str(capture_id),
            entry_count=len(mapped.entries),
            needs_review=mapped.needs_review_count,
            unresolved_dates=len(mapped.unresolved_dates),
        )
        return CaptureStatus.COMPLETED

    # -- helpers -----------------------------------------------------------
    async def _load(self, session: AsyncSession, capture_id: uuid.UUID) -> Capture | None:
        result = await session.execute(
            select(Capture).where(Capture.id == capture_id, Capture.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def _current_transcript(
        self, session: AsyncSession, capture_id: uuid.UUID
    ) -> Transcript | None:
        result = await session.execute(
            select(Transcript).where(
                Transcript.capture_id == capture_id, Transcript.is_current.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def _build_context(self, session: AsyncSession, capture: Capture) -> AnalysisContext:
        from app.infra.db.models.core import AppUser, Project, Tag

        user = (
            await session.execute(select(AppUser).where(AppUser.id == capture.user_id))
        ).scalar_one()
        projects = (
            (
                await session.execute(
                    select(Project.name).where(Project.archived_at.is_(None)).limit(20)
                )
            )
            .scalars()
            .all()
        )
        tags = (
            (await session.execute(select(Tag.label).order_by(Tag.usage_count.desc()).limit(20)))
            .scalars()
            .all()
        )
        recent = (
            (await session.execute(select(Entry.title).order_by(Entry.occurred_at.desc()).limit(5)))
            .scalars()
            .all()
        )

        local = capture.captured_at.astimezone(ZoneInfo(user.timezone))
        return AnalysisContext(
            timezone=user.timezone,
            locale=user.locale,
            captured_at_local=local.strftime("%Y-%m-%d %H:%M"),
            weekday=_WEEKDAYS_FR[local.weekday()],
            known_projects=tuple(projects),
            known_tags=tuple(tags),
            recent_titles=tuple(recent),
        )

    async def _record_run(
        self, capture_id: uuid.UUID, account_id: uuid.UUID, status: AiRunStatus, code: str
    ) -> None:
        async with tenant_session(account_id) as session:
            session.add(
                AiRun(
                    id=uuid.uuid4(),
                    account_id=account_id,
                    capture_id=capture_id,
                    operation=AiOperation.EXTRACT,
                    model_id=self._settings.llm_model,
                    provider=self._analyzer.name,
                    status=status,
                    error_code=code,
                )
            )

    async def _fail(
        self, capture_id: uuid.UUID, account_id: uuid.UUID, stage: str, code: str
    ) -> None:
        await self._finish(capture_id, account_id, terminal_status_for_failure(stage), code)

    async def _finish(
        self,
        capture_id: uuid.UUID,
        account_id: uuid.UUID,
        status: CaptureStatus,
        code: str | None,
    ) -> CaptureStatus:
        async with tenant_session(account_id) as session:
            await set_tenant_context(session, account_id=account_id)
            await session.execute(
                update(Capture)
                .where(Capture.id == capture_id)
                .values(
                    status=status.value,
                    failure_code=code,
                    processing_finished_at=datetime.now(UTC),
                )
            )
        return status
