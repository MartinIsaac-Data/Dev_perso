"""Anti-hallucination guards (AI.md §3.2, Sprint02 epic 12.4)."""

from __future__ import annotations

import pytest

from app.domain.ports import TranscriptionResult, TranscriptionSegment
from app.infra.ai.guards import (
    apply_transcription_guards,
    has_pathological_repetition,
    is_known_artefact,
)


def result(text: str, *, speech_ms: int = 14000, confidence: float | None = 0.9):
    return TranscriptionResult(
        text=text,
        language="fr",
        confidence=confidence,
        engine="test",
        engine_version="1",
        duration_ms=speech_ms,
        segments=(TranscriptionSegment(0, speech_ms, text, confidence),),
    )


@pytest.mark.parametrize(
    "text",
    [
        "Sous-titres réalisés par la communauté d'Amara.org",
        "Merci d'avoir regardé cette vidéo",
        "Thanks for watching!",
        "Abonnez-vous à la chaîne",
    ],
)
def test_known_whisper_artefacts_are_detected(text: str) -> None:
    assert is_known_artefact(text)


def test_real_speech_is_not_flagged_as_an_artefact() -> None:
    assert not is_known_artefact("Faut que je rappelle le DAF de Vinci jeudi")


def test_decoder_loop_is_detected() -> None:
    looped = "je vais le faire " * 8
    assert has_pathological_repetition(looped)


def test_normal_repetition_is_not_flagged() -> None:
    text = (
        "Il faut rappeler le DAF de Vinci jeudi pour le budget Q3 "
        "et relire la clause RGPD avant la réunion"
    )
    assert not has_pathological_repetition(text)


def test_artefact_transcript_is_emptied() -> None:
    guarded = apply_transcription_guards(result("Sous-titres réalisés par Amara.org"))
    assert guarded.text == ""
    assert guarded.confidence == 0.0


def test_near_silent_audio_produces_no_text() -> None:
    """The core case: 200 ms of audio cannot contain a sentence."""
    guarded = apply_transcription_guards(
        TranscriptionResult(
            text="Merci beaucoup, à bientôt !",
            language="fr",
            confidence=0.8,
            engine="test",
            engine_version="1",
            duration_ms=200,
            segments=(TranscriptionSegment(0, 200, "Merci beaucoup, à bientôt !", 0.8),),
        )
    )
    assert guarded.text == ""


def test_looping_transcript_is_emptied() -> None:
    guarded = apply_transcription_guards(result("merci merci merci merci merci merci merci"))
    assert guarded.text == ""


def test_genuine_transcript_survives_untouched() -> None:
    text = "Faut que je rappelle le DAF de Vinci jeudi pour le budget Q3."
    guarded = apply_transcription_guards(result(text))
    assert guarded.text == text
    assert guarded.confidence == 0.9


def test_low_confidence_transcript_is_kept_not_discarded() -> None:
    """A noisy but genuine recording must reach the user; low confidence pushes
    the entry into needs_review instead."""
    text = "euh... faut que je... rappelle le DAF"
    guarded = apply_transcription_guards(result(text, confidence=0.2))
    assert guarded.text == text


def test_empty_input_stays_empty() -> None:
    assert apply_transcription_guards(result("")).text == ""


def test_single_word_loop_is_detected() -> None:
    """The most common Whisper loop shape — too short to form a repeated 4-gram."""
    assert has_pathological_repetition("merci merci merci merci merci merci merci")


def test_short_natural_repetition_is_not_a_loop() -> None:
    assert not has_pathological_repetition("oui oui")
    assert not has_pathological_repetition("non non non")


def test_emphatic_repetition_inside_real_speech_survives() -> None:
    text = "c'est vraiment vraiment important de rappeler le DAF avant jeudi prochain"
    assert not has_pathological_repetition(text)
