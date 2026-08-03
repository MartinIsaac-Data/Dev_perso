"""Capture lifecycle (API.md §5.2, ADR-009, ADR-026)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.capture import object_key, validate_declaration
from app.domain.enums import AudioFormat, CaptureKind, CaptureSource, CaptureStatus
from app.domain.errors import (
    CaptureAlreadyCompletedError,
    NotFoundError,
)
from app.domain.ports import ObjectStoragePort, SignedUpload
from app.infra.db.models.core import (
    Capture,
    Entry,
    Outbox,
    Plan,
    Subscription,
    Transcript,
    UsageCounter,
)
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.identity_service import Principal

log = get_logger("capture")

QUICK_CAPTURE_METRIC = "quick_captures"
# Absolute ceiling that applies even in degraded mode. Without it, ADR-026
# ("the quota never blocks a capture") would be an open door to abuse.
ABSOLUTE_MONTHLY_CEILING = 2000


@dataclass(slots=True)
class DeclaredCapture:
    capture: Capture
    upload: SignedUpload | None
    created: bool
    degraded: bool


class CaptureService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        storage: ObjectStoragePort,
        settings: Settings,
    ) -> None:
        self._session = session
        self._principal = principal
        self._storage = storage
        self._settings = settings

    async def declare(
        self,
        *,
        client_capture_id: uuid.UUID,
        duration_ms: int,
        audio_format: str,
        captured_at: datetime,
        capture_timezone: str,
        kind: CaptureKind = CaptureKind.QUICK,
        source: CaptureSource = CaptureSource.APP,
        language_hint: str | None = None,
        audio_bytes: int | None = None,
        audio_sample_rate: int | None = None,
    ) -> DeclaredCapture:
        """Declare a capture and hand back a signed upload URL.

        Replaying the same `client_capture_id` returns the existing capture: that
        is what makes offline retry safe (ADR-009).
        """
        existing = await self._find_by_client_id(client_capture_id)
        if existing is not None:
            upload = None
            if existing.status == CaptureStatus.PENDING_UPLOAD and existing.audio_object_key:
                upload = await self._storage.signed_upload(
                    existing.audio_object_key,
                    media_type=AudioFormat(existing.audio_format or "m4a").media_type,
                    max_bytes=self._settings.storage_max_audio_bytes,
                )
            return DeclaredCapture(existing, upload, created=False, degraded=False)

        plan = await self._plan()
        max_duration = min(self._settings.max_capture_duration_ms, plan.max_capture_duration_ms)
        fmt = validate_declaration(
            duration_ms=duration_ms, audio_format=audio_format, max_duration_ms=max_duration
        )

        degraded = await self._is_over_quota(plan)

        capture_id = uuid.uuid4()
        key = object_key(str(self._principal.account_id), str(capture_id), fmt)
        capture = Capture(
            id=capture_id,
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            client_capture_id=client_capture_id,
            kind=kind,
            status=CaptureStatus.PENDING_UPLOAD,
            audio_object_key=key,
            audio_bytes=audio_bytes,
            audio_format=fmt.value,
            audio_sample_rate=audio_sample_rate,
            duration_ms=duration_ms,
            captured_at=captured_at,
            capture_timezone=capture_timezone,
            source=source,
            language_hint=language_hint,
            processing_mode="degraded" if degraded else "normal",
        )
        self._session.add(capture)

        try:
            await self._session.flush()
        except IntegrityError:
            # Concurrent replay of the same client id — read the winner back.
            await self._session.rollback()
            winner = await self._find_by_client_id(client_capture_id)
            if winner is None:
                raise
            return DeclaredCapture(winner, None, created=False, degraded=False)

        await self._increment_usage(QUICK_CAPTURE_METRIC)
        metrics.captures_created_total.labels(str(source)).inc()

        upload = await self._storage.signed_upload(
            key,
            media_type=fmt.media_type,
            max_bytes=self._settings.storage_max_audio_bytes,
        )
        log.info("capture.created", capture_id=str(capture_id), degraded=degraded)
        return DeclaredCapture(capture, upload, created=True, degraded=degraded)

    async def _find_by_client_id(self, client_capture_id: uuid.UUID) -> Capture | None:
        """Look a capture up by its client-generated id.

        This is the whole idempotency mechanism (ADR-009): a client replaying a
        declaration after a lost response must get back the same capture, not a
        second one. The unique constraint on (user_id, client_capture_id) is the
        backstop for the race this cannot see.
        """
        result = await self._session.execute(
            select(Capture).where(
                Capture.user_id == self._principal.user_id,
                Capture.client_capture_id == client_capture_id,
                Capture.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def complete_upload(self, capture_id: uuid.UUID) -> Capture:
        """Mark the audio as uploaded and publish the processing event."""
        capture = await self.get(capture_id)
        status = CaptureStatus(capture.status)

        if status is not CaptureStatus.PENDING_UPLOAD:
            if status.is_terminal or status in (
                CaptureStatus.UPLOADED,
                CaptureStatus.TRANSCRIBING,
                CaptureStatus.TRANSCRIBED,
                CaptureStatus.EXTRACTING,
            ):
                # Replay of `complete` — idempotent, not an error.
                return capture
            raise CaptureAlreadyCompletedError("Capture déjà finalisée.")

        capture.status = CaptureStatus.UPLOADED
        # Written in the same transaction as the status change (ADR-010): the
        # event cannot be lost, and cannot exist without the state that justifies it.
        self._session.add(
            Outbox(
                account_id=self._principal.account_id,
                event_type="capture.uploaded",
                aggregate_type="capture",
                aggregate_id=capture.id,
                payload={
                    "capture_id": str(capture.id),
                    "account_id": str(self._principal.account_id),
                },
            )
        )
        await self._session.flush()
        log.info("capture.uploaded", capture_id=str(capture_id))
        return capture

    async def get(self, capture_id: uuid.UUID) -> Capture:
        result = await self._session.execute(
            select(Capture).where(Capture.id == capture_id, Capture.deleted_at.is_(None))
        )
        capture = result.scalar_one_or_none()
        if capture is None:
            # 404 rather than 403 for another tenant's row: a 403 would confirm
            # the row exists (API.md §3.1).
            raise NotFoundError(f"Capture {capture_id} introuvable.")
        return capture

    async def list(self, *, limit: int = 50, before: datetime | None = None) -> list[Capture]:
        query = (
            select(Capture)
            .where(Capture.deleted_at.is_(None))
            .order_by(Capture.captured_at.desc())
            .limit(min(limit, 200))
        )
        if before is not None:
            query = query.where(Capture.captured_at < before)
        return list((await self._session.execute(query)).scalars().all())

    async def transcript(self, capture_id: uuid.UUID) -> Transcript | None:
        await self.get(capture_id)
        result = await self._session.execute(
            select(Transcript).where(
                Transcript.capture_id == capture_id, Transcript.is_current.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def audio_url(self, capture_id: uuid.UUID) -> str | None:
        capture = await self.get(capture_id)
        if not capture.audio_object_key:
            return None
        if not await self._storage.exists(capture.audio_object_key):
            return None
        return await self._storage.signed_download(capture.audio_object_key)

    async def delete(
        self, capture_id: uuid.UUID, *, cascade: bool = False, audio_only: bool = False
    ) -> None:
        """Delete a capture.

        Default is **not** cascading (ADR-028): someone deleting a recording for
        privacy reasons wants the audio gone, not the tasks they drew from it.
        """
        capture = await self.get(capture_id)
        now = datetime.now(UTC)

        if capture.audio_object_key:
            await self._storage.delete(capture.audio_object_key)
            capture.audio_object_key = None

        if audio_only:
            await self._session.flush()
            log.info("capture.audio_deleted", capture_id=str(capture_id))
            return

        capture.deleted_at = now
        if cascade:
            entries = await self._session.execute(
                select(Entry).where(Entry.capture_id == capture_id)
            )
            for entry in entries.scalars().all():
                entry.deleted_at = now
        await self._session.flush()
        log.info("capture.deleted", capture_id=str(capture_id), cascade=cascade)

    # -- quota -------------------------------------------------------------
    async def _plan(self) -> Plan:
        result = await self._session.execute(
            select(Plan)
            .join(Subscription, Subscription.plan_code == Plan.code)
            .where(Subscription.account_id == self._principal.account_id)
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            free = await self._session.execute(select(Plan).where(Plan.code == "free"))
            plan = free.scalar_one()
        return plan

    async def _is_over_quota(self, plan: Plan) -> bool:
        if plan.max_quick_captures_month is None:
            return False
        used = await self._usage(QUICK_CAPTURE_METRIC)
        return used >= plan.max_quick_captures_month

    async def _usage(self, metric: str) -> int:
        period = date.today().replace(day=1)
        result = await self._session.execute(
            select(UsageCounter.value).where(
                UsageCounter.account_id == self._principal.account_id,
                UsageCounter.metric == metric,
                UsageCounter.period_start == period,
            )
        )
        return int(result.scalar_one_or_none() or 0)

    async def _increment_usage(self, metric: str) -> None:
        period = date.today().replace(day=1)
        counter = await self._session.get(
            UsageCounter, (self._principal.account_id, metric, period)
        )
        if counter is None:
            self._session.add(
                UsageCounter(
                    account_id=self._principal.account_id,
                    metric=metric,
                    period_start=period,
                    value=1,
                )
            )
        else:
            counter.value += 1
        await self._session.flush()

    async def usage_summary(self) -> dict[str, int | None]:
        plan = await self._plan()
        used = await self._usage(QUICK_CAPTURE_METRIC)
        return {
            "used": used,
            "limit": plan.max_quick_captures_month,
            "remaining": (
                None
                if plan.max_quick_captures_month is None
                else max(0, plan.max_quick_captures_month - used)
            ),
        }

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Capture).where(Capture.deleted_at.is_(None))
        )
        return int(result.scalar_one())
