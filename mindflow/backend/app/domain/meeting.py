"""Live meetings: stitching a transcript, and deciding when to spend a model call.

Everything here is pure. That is not tidiness — it is the only way this feature
can be tested at all, because the alternative is a test that needs a microphone,
a speech provider and forty-five minutes.

Three problems, and each has exactly one interesting decision.

**Stitching.** Audio is sent in overlapping blocks (ADR-013), so consecutive
transcripts repeat their seam: `…on décide de reporter` then `de reporter au 12`.
Concatenating gives `on décide de reporter de reporter au 12`, which reads as a
stutter and poisons everything downstream. `stitch` finds the longest suffix of
what we have that is also a prefix of what arrived, and joins there.

**Cueing.** A forty-five minute meeting must not become two hundred model calls.
ADR-047's rule applies unchanged: do not spend a call unless there is something
new worth analysing. `should_analyse` is deterministic and cheap, and it is what
keeps the feature affordable.

**Deduplication.** Incremental extraction re-proposes the same action every
window, because the sentence that produced it is still in the context. A
suggestion list that repeats itself is a list nobody reads to the end.
"""

from __future__ import annotations

import contextlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

# --------------------------------------------------------------------------- #
# Stitching
# --------------------------------------------------------------------------- #

# How far back to look for the seam. Blocks overlap by a few seconds, so the
# repeated text is short; searching the whole transcript would be quadratic in
# the length of a meeting for no gain.
MAX_OVERLAP_CHARS = 400

# Below this, an apparent overlap is a coincidence rather than a seam. "de" is a
# suffix of almost everything; joining on it would delete a real word.
MIN_OVERLAP_CHARS = 12

_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Casefolded, unaccented, whitespace-collapsed — for comparison only.

    Never stored: the transcript keeps its accents and its capitals. This exists
    so that `Reporter au 12` and `reporter au 12` are recognised as the same
    seam, which they are.
    """
    stripped = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    return _WHITESPACE.sub(" ", without_marks).strip().casefold()


def overlap_length(existing: str, arriving: str) -> int:
    """Characters of `arriving` that repeat the tail of `existing`.

    Zero when the two do not meet, which is the common case once the meeting is
    running smoothly and blocks arrive without loss.
    """
    if not existing or not arriving:
        return 0

    tail = normalise(existing[-MAX_OVERLAP_CHARS:])
    head = normalise(arriving[:MAX_OVERLAP_CHARS])
    limit = min(len(tail), len(head))

    # Longest first: the seam is the *longest* repetition, not any repetition.
    # Taking the shortest match would leave part of the stutter in place.
    for size in range(limit, MIN_OVERLAP_CHARS - 1, -1):
        if tail[-size:] == head[:size]:
            return size
    return 0


def stitch(existing: str, arriving: str) -> str:
    """Append `arriving` to `existing`, removing the repeated seam."""
    arriving = arriving.strip()
    if not arriving:
        return existing
    if not existing:
        return arriving

    repeated = overlap_length(existing, arriving)
    if repeated == 0:
        return f"{existing} {arriving}"

    # The overlap was measured on normalised text, which can be shorter than the
    # original (collapsed whitespace, decomposed accents). Walking the raw
    # string until its normalised prefix reaches the measured length is what
    # keeps the cut on a real character boundary.
    for cut in range(len(arriving) + 1):
        if len(normalise(arriving[:cut])) >= repeated:
            remainder = arriving[cut:].lstrip()
            return f"{existing} {remainder}".rstrip() if remainder else existing
    return existing


# --------------------------------------------------------------------------- #
# Cueing
# --------------------------------------------------------------------------- #

# Words of new transcript before an analysis is worth its cost. Roughly thirty
# seconds of speech: short enough that a decision surfaces while it still
# matters, long enough that a model sees a complete thought.
ANALYSIS_WORD_THRESHOLD = 70

# The floor. Below this there is not enough new material for a model to say
# anything a human could not, whatever else is true.
MIN_WORDS_TO_ANALYSE = 25

# Phrases that mean a commitment was just made. When one appears, the window is
# analysed early rather than at the word threshold — the sentence that assigns
# an action is exactly the one worth catching while people are still in the
# room.
_CUE_PHRASES: tuple[str, ...] = (
    "on decide",
    "on est d accord",
    "il faut que",
    "je m en occupe",
    "tu peux",
    "on valide",
    "a faire",
    "action item",
    "prochaine etape",
    "d ici",
    "avant vendredi",
    "avant lundi",
    "je reviens vers",
    "on se recale",
    "on tranche",
)

_SEPARATORS = re.compile("[\u2019'\\-_]+")


def _flatten(text: str) -> str:
    """Normalised, with apostrophes and hyphens flattened to spaces.

    Same treatment as the intent router (phase 3): dictation drops apostrophes,
    so `on décide` and `on d'écide` must both match. Matching on the raw string
    would make cue detection depend on the speech provider's punctuation.
    """
    return _WHITESPACE.sub(" ", _SEPARATORS.sub(" ", normalise(text))).strip()


def contains_cue(text: str) -> bool:
    """Whether the text contains a phrase that marks a commitment."""
    flat = _flatten(text)
    return any(phrase in flat for phrase in _CUE_PHRASES)


def word_count(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def should_analyse(
    *,
    pending: str,
    closing: bool = False,
) -> bool:
    """Whether the unanalysed tail justifies a model call.

    `closing` forces one last pass so a commitment made in the final thirty
    seconds is not lost — the most likely moment for one, since that is when
    people agree what happens next.
    """
    words = word_count(pending)
    if words == 0:
        return False
    if closing:
        return True
    if words < MIN_WORDS_TO_ANALYSE:
        return False
    return words >= ANALYSIS_WORD_THRESHOLD or contains_cue(pending)


# --------------------------------------------------------------------------- #
# Suggestions
# --------------------------------------------------------------------------- #
class SuggestionKind(StrEnum):
    ACTION = "action"
    DECISION = "decision"
    QUESTION = "question"

    @classmethod
    def parse(cls, value: str | None) -> SuggestionKind:
        """Unknown kinds become questions, not actions.

        The direction matters: an invented *action* asks somebody to do
        something nobody agreed to, while an invented *question* is merely
        noise. When a model returns a label we did not define, the harmless
        reading is the correct default.
        """
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.QUESTION

    @property
    def label(self) -> str:
        return {
            SuggestionKind.ACTION: "Action",
            SuggestionKind.DECISION: "Décision",
            SuggestionKind.QUESTION: "Question ouverte",
        }[self]


@dataclass(frozen=True, slots=True)
class Suggestion:
    """One thing the model noticed during the meeting. Provisional by nature."""

    kind: SuggestionKind
    text: str
    owner: str | None = None
    confidence: float = 0.5
    at_word: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def key(self) -> str:
        """Identity for deduplication: the normalised text, and nothing else.

        Not the owner: `Marie envoie le budget` and `envoyer le budget (Marie)`
        are the same commitment phrased twice, and showing both makes the list
        look like the model is guessing.
        """
        return _flatten(self.text)

    def to_json(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "text": self.text,
            "owner": self.owner,
            "confidence": self.confidence,
            "at_word": self.at_word,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> Suggestion | None:
        text = str(data.get("text") or "").strip()
        if not text:
            return None
        raw_created = data.get("created_at")
        created = datetime.now(UTC)
        if isinstance(raw_created, str):
            with contextlib.suppress(ValueError):
                created = datetime.fromisoformat(raw_created)
        raw_kind = data.get("kind")
        raw_confidence = data.get("confidence")
        raw_word = data.get("at_word")
        return cls(
            kind=SuggestionKind.parse(raw_kind if isinstance(raw_kind, str) else None),
            text=text,
            owner=(str(data["owner"]) if data.get("owner") else None),
            confidence=float(raw_confidence) if isinstance(raw_confidence, int | float) else 0.5,
            at_word=int(raw_word) if isinstance(raw_word, int | float) else 0,
            created_at=created,
        )


# A meeting that produces sixty suggestions has produced none: nobody reads to
# the end of that list. The cap keeps the newest, because a meeting's later
# commitments supersede its earlier ones more often than the reverse.
MAX_SUGGESTIONS = 40


def merge_suggestions(
    existing: list[Suggestion],
    arriving: list[Suggestion],
) -> list[Suggestion]:
    """Add what is new, keep what was already there, drop the repeats.

    An existing suggestion is never replaced by a later duplicate, so the
    timestamp on screen stays the moment the thing was *first* said. Watching a
    suggestion's time jump forward every thirty seconds reads as a bug.
    """
    merged = list(existing)
    seen = {item.key for item in merged}
    for candidate in arriving:
        if not candidate.text.strip():
            continue
        if candidate.key in seen:
            continue
        seen.add(candidate.key)
        merged.append(candidate)
    if len(merged) > MAX_SUGGESTIONS:
        merged = merged[-MAX_SUGGESTIONS:]
    return merged


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
class MeetingStatus(StrEnum):
    LIVE = "live"
    ENDED = "ended"
    ABANDONED = "abandoned"

    @property
    def is_open(self) -> bool:
        return self is MeetingStatus.LIVE


@dataclass(frozen=True, slots=True)
class MeetingWindow:
    """What has been said, and how much of it a model has looked at.

    `analysed_words` is a count rather than an offset into the string because
    stitching rewrites the tail of the transcript: an offset would point into
    the middle of a word after the seam is removed.
    """

    transcript: str = ""
    analysed_words: int = 0

    @property
    def pending(self) -> str:
        """The tail no model has seen yet."""
        words = self.transcript.split()
        return " ".join(words[self.analysed_words :])

    @property
    def total_words(self) -> int:
        return word_count(self.transcript)

    def append(self, arriving: str) -> MeetingWindow:
        return MeetingWindow(
            transcript=stitch(self.transcript, arriving),
            # Unchanged on purpose: appending does not make a model read.
            analysed_words=self.analysed_words,
        )

    def mark_analysed(self) -> MeetingWindow:
        return MeetingWindow(
            transcript=self.transcript,
            analysed_words=self.total_words,
        )

    def due(self, *, closing: bool = False) -> bool:
        return should_analyse(pending=self.pending, closing=closing)
