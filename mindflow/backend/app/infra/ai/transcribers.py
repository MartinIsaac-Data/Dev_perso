"""Speech-to-text adapters (ADR-007, AI.md §3).

Three implementations behind one port:

* `FasterWhisperTranscriber` — self-hosted, the production default of ADR-007.
* `OpenAIWhisperTranscriber` — the hosted API, and the circuit-breaker fallback.
* `FakeTranscriber` — deterministic, for tests and local work without a GPU.

The anti-hallucination guards are **not** applied here: they live in the pipeline
orchestrator so that they apply to every engine, including any adapter added
later. See `app/infra/ai/guards.py` and AI.md §3.2.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.domain.errors import TranscriptionUnavailableError
from app.domain.ports import TranscriberPort, TranscriptionResult, TranscriptionSegment
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("ai.stt")


class FakeTranscriber(TranscriberPort):
    """Deterministic transcriber for tests and offline development."""

    name = "fake"

    def __init__(self, text: str | None = None, language: str = "fr") -> None:
        self._text = text or (
            "Faut que je rappelle le DAF de Vinci jeudi pour le budget Q3. "
            "Et penser à relire la clause RGPD avant."
        )
        self._language = language

    async def transcribe(
        self, audio: bytes, *, media_type: str, language_hint: str | None = None
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text=self._text,
            language=language_hint or self._language,
            confidence=0.94,
            engine="fake",
            engine_version="1",
            duration_ms=len(audio) // 32 or 1000,
            segments=(TranscriptionSegment(0, 14000, self._text, 0.94),),
        )


class FasterWhisperTranscriber(TranscriberPort):
    """Self-hosted faster-whisper (ADR-007).

    The model is loaded lazily and kept on the instance: loading `large-v3` takes
    tens of seconds, so it must happen once per worker process, never per request.
    """

    name = "faster_whisper"

    def __init__(
        self,
        *,
        model: str = "large-v3",
        device: str = "auto",
        compute_type: str = "int8_float16",
        timeout: float = 300.0,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._timeout = timeout
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_model(self) -> Any:
        # Double-checked locking. The fast path avoids the lock once loaded; the
        # slow path re-checks because another coroutine may have finished loading
        # while this one was suspended on the lock.
        model = self._model
        if model is not None:
            return model
        async with self._lock:
            model = self._model
            if model is not None:
                return model
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - deployment concern
                raise TranscriptionUnavailableError(
                    "faster-whisper n'est pas installé (extra 'whisper')."
                ) from exc
            self._model = await asyncio.to_thread(
                WhisperModel,
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
            return self._model

    async def transcribe(
        self, audio: bytes, *, media_type: str, language_hint: str | None = None
    ) -> TranscriptionResult:
        import io

        model = await self._ensure_model()
        started = time.perf_counter()

        def run() -> tuple[list[Any], Any]:
            segments, info = model.transcribe(
                io.BytesIO(audio),
                language=language_hint,
                # VAD strips silence: ~25% less compute, and it is the first line
                # of defence against hallucination on near-empty audio.
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                word_timestamps=True,
                beam_size=5,
            )
            return list(segments), info

        try:
            raw_segments, info = await asyncio.wait_for(
                asyncio.to_thread(run), timeout=self._timeout
            )
        except TimeoutError as exc:
            raise TranscriptionUnavailableError("Transcription trop longue.") from exc
        except Exception as exc:
            log.error("stt.failed", engine=self.name, error=type(exc).__name__)
            raise TranscriptionUnavailableError("Échec de la transcription.") from exc

        metrics.stt_duration_seconds.labels(self.name).observe(time.perf_counter() - started)

        segments = tuple(
            TranscriptionSegment(
                start_ms=int(seg.start * 1000),
                end_ms=int(seg.end * 1000),
                text=seg.text.strip(),
                confidence=_logprob_to_confidence(getattr(seg, "avg_logprob", None)),
            )
            for seg in raw_segments
        )
        words = [
            {"w": w.word, "s": int(w.start * 1000), "e": int(w.end * 1000), "c": w.probability}
            for seg in raw_segments
            for w in (getattr(seg, "words", None) or [])
        ]

        result = TranscriptionResult(
            text=" ".join(s.text for s in segments).strip(),
            language=getattr(info, "language", language_hint or "fr"),
            confidence=_mean_confidence(segments),
            engine=self.name,
            engine_version=self._model_name,
            duration_ms=int(getattr(info, "duration", 0) * 1000),
            segments=segments,
            words=words,
        )
        return result


class OpenAIWhisperTranscriber(TranscriberPort):
    """Hosted Whisper. Production fallback, and the default when no GPU exists."""

    name = "openai_whisper"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        timeout: float = 300.0,
        is_fallback: bool = False,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._is_fallback = is_fallback

    async def transcribe(
        self, audio: bytes, *, media_type: str, language_hint: str | None = None
    ) -> TranscriptionResult:
        started = time.perf_counter()
        extension = media_type.split("/")[-1].replace("mp4", "m4a").replace("mpeg", "mp3")
        data: dict[str, str] = {"model": self._model, "response_format": "verbose_json"}
        if language_hint:
            data["language"] = language_hint

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": (f"audio.{extension}", audio, media_type)},
                    data=data,
                )
        except httpx.HTTPError as exc:
            log.error("stt.transport_failed", engine=self.name, error=type(exc).__name__)
            raise TranscriptionUnavailableError("Service de transcription injoignable.") from exc

        if response.status_code >= 400:
            log.error("stt.failed", engine=self.name, status=response.status_code)
            raise TranscriptionUnavailableError("Échec de la transcription.")

        payload = response.json()
        metrics.stt_duration_seconds.labels(self.name).observe(time.perf_counter() - started)

        segments = tuple(
            TranscriptionSegment(
                start_ms=int(seg.get("start", 0) * 1000),
                end_ms=int(seg.get("end", 0) * 1000),
                text=str(seg.get("text", "")).strip(),
                confidence=_logprob_to_confidence(seg.get("avg_logprob")),
            )
            for seg in payload.get("segments", [])
        )
        return TranscriptionResult(
            text=str(payload.get("text", "")).strip(),
            language=payload.get("language", language_hint or "fr"),
            confidence=_mean_confidence(segments),
            engine=self.name,
            engine_version=self._model,
            duration_ms=int(float(payload.get("duration", 0)) * 1000),
            segments=segments,
            is_fallback=self._is_fallback,
        )


def _logprob_to_confidence(logprob: float | None) -> float | None:
    if logprob is None:
        return None
    import math

    return round(min(1.0, max(0.0, math.exp(logprob))), 3)


def _mean_confidence(segments: tuple[TranscriptionSegment, ...]) -> float | None:
    values = [s.confidence for s in segments if s.confidence is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)
