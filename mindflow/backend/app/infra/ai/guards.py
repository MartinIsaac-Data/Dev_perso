"""Anti-hallucination guards for transcription (AI.md §3.2).

Whisper is trained on 30-second windows and fabricates fluent text on short or
near-silent input — typically a polite phrase that was never spoken. It is the
most dangerous failure mode in the product: the output is syntactically perfect
and entirely invented, so nothing downstream can tell it apart from a real
transcript.

These guards run on every engine, not just the self-hosted one.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.domain.ports import TranscriptionResult

# Known Whisper hallucinations, normalised (lowercase, no accents). These are
# training-data artefacts — subtitle credits and channel outros.
_KNOWN_ARTEFACTS = (
    "sous titres realises par",
    "sous titrage",
    "merci d avoir regarde cette video",
    "abonnez vous",
    "subtitles by",
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "amara.org",
    "www.",
)

MIN_SPEECH_MS = 400
MAX_NGRAM_REPEATS = 3
LOW_CONFIDENCE_THRESHOLD = 0.35
# A single word taking 60%+ of a transcript is a loop, not speech. Below five
# words the ratio is meaningless ("oui oui" is a normal thing to say).
MIN_WORDS_FOR_UNIGRAM_CHECK = 5
UNIGRAM_DOMINANCE_THRESHOLD = 0.6


def _normalise(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]+", " ", stripped)


def is_known_artefact(text: str) -> bool:
    normalised = _normalise(text)
    return any(artefact in normalised for artefact in _KNOWN_ARTEFACTS)


def has_pathological_repetition(text: str, *, n: int = 4) -> bool:
    """A repeated n-gram is the signature of a decoder stuck in a loop.

    Two shapes are checked, because they fail differently:

    * a repeated *phrase* ("je vais le faire je vais le faire …") — caught by the
      n-gram counter;
    * a repeated *single token* ("merci merci merci …") — too short to form a
      repeated 4-gram, so it needs its own check. This one is the more common
      Whisper loop.
    """
    words = _normalise(text).split()
    if not words:
        return False

    if len(words) >= MIN_WORDS_FOR_UNIGRAM_CHECK:
        most_common_share = Counter(words).most_common(1)[0][1] / len(words)
        if most_common_share >= UNIGRAM_DOMINANCE_THRESHOLD:
            return True

    if len(words) < n * 2:
        return False
    ngrams = Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    return max(ngrams.values()) > MAX_NGRAM_REPEATS


def apply_transcription_guards(result: TranscriptionResult) -> TranscriptionResult:
    """Return the result, emptied if it is judged fabricated.

    An empty transcript is an honest outcome the pipeline knows how to handle.
    Invented text is not: it would be classified, turned into a task, and shown
    to the user as something they said.
    """
    from dataclasses import replace

    text = result.text.strip()

    if not text:
        return replace(result, text="", confidence=result.confidence)

    speech_ms = sum(seg.end_ms - seg.start_ms for seg in result.segments) or result.duration_ms
    if speech_ms < MIN_SPEECH_MS:
        return replace(result, text="", confidence=0.0)

    if is_known_artefact(text):
        return replace(result, text="", confidence=0.0)

    if has_pathological_repetition(text):
        return replace(result, text="", confidence=0.0)

    if result.confidence is not None and result.confidence < LOW_CONFIDENCE_THRESHOLD:
        # Kept, but flagged: low confidence pushes the entry into needs_review
        # rather than discarding what may be a genuine but noisy recording.
        return result

    return result
