"""Stitching, cueing and deduplication — the three things that make a live
meeting affordable and readable.

All pure, so all testable without a microphone, a speech provider or
forty-five minutes. The cases below are the ones where being wrong is visible to
a person in a room:

* a bad stitch puts a stutter in the transcript, and every summary built on it
  inherits the stutter;
* a bad cue turns a meeting into two hundred model calls, or misses the sentence
  where somebody committed to something;
* a bad dedupe fills the panel with the same action six times, which is how a
  panel stops being read.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.meeting import (
    ANALYSIS_WORD_THRESHOLD,
    MAX_SUGGESTIONS,
    MIN_WORDS_TO_ANALYSE,
    MeetingWindow,
    Suggestion,
    SuggestionKind,
    contains_cue,
    merge_suggestions,
    overlap_length,
    should_analyse,
    stitch,
)


def _words(count: int, word: str = "mot") -> str:
    return " ".join([word] * count)


class TestStitching:
    def test_the_first_block_is_the_transcript(self) -> None:
        assert stitch("", "bonjour à tous") == "bonjour à tous"

    def test_blocks_that_do_not_overlap_are_joined(self) -> None:
        assert stitch("bonjour à tous", "commençons") == "bonjour à tous commençons"

    def test_the_repeated_seam_is_removed(self) -> None:
        # The failure this function exists for. Overlapping audio blocks are
        # transcribed twice at the seam (ADR-013).
        existing = "on parle du budget et on décide de reporter"
        arriving = "on décide de reporter au 12 janvier"

        assert stitch(existing, arriving) == (
            "on parle du budget et on décide de reporter au 12 janvier"
        )

    def test_the_longest_repetition_wins(self) -> None:
        # Taking any match rather than the longest would leave part of the
        # stutter in place, which is worse than not stitching at all.
        existing = "il faut relancer le fournisseur cette semaine"
        arriving = "relancer le fournisseur cette semaine et prévenir Marie"

        assert stitch(existing, arriving) == (
            "il faut relancer le fournisseur cette semaine et prévenir Marie"
        )

    def test_a_seam_is_matched_across_case_and_accents(self) -> None:
        # A speech provider is not consistent about capitals at a block
        # boundary, and comparing raw strings would miss the seam every time a
        # block happened to start a sentence.
        existing = "nous avons décidé de reporter la réunion"
        arriving = "Décidé de reporter la réunion à jeudi"

        assert stitch(existing, arriving) == ("nous avons décidé de reporter la réunion à jeudi")

    def test_a_short_coincidence_is_not_treated_as_a_seam(self) -> None:
        # "de" is a suffix of almost everything. Joining on it would delete a
        # real word from the transcript.
        existing = "on a beaucoup parlé de"
        arriving = "de toute façon il faudra trancher"

        assert stitch(existing, arriving) == (
            "on a beaucoup parlé de de toute façon il faudra trancher"
        )

    def test_an_identical_block_adds_nothing(self) -> None:
        # A retried request must not double the transcript.
        text = "le budget est validé pour le trimestre prochain"
        assert stitch(text, text) == text

    def test_an_empty_block_changes_nothing(self) -> None:
        assert stitch("bonjour", "") == "bonjour"
        assert stitch("bonjour", "   ") == "bonjour"

    def test_overlap_is_zero_when_the_blocks_do_not_meet(self) -> None:
        assert overlap_length("premier sujet", "deuxième sujet complètement autre") == 0

    def test_a_seam_below_the_floor_is_left_as_a_stutter(self) -> None:
        """The accepted cost of the floor, pinned so it stays a decision.

        `de reporter` is eleven characters — a genuine seam, and shorter than
        `MIN_OVERLAP_CHARS`. It is therefore not removed, and the transcript
        keeps a small repetition.

        That is the right direction to fail in. A stutter is visible, harmless
        and survivable by every downstream reader; a floor low enough to catch
        it would start deleting real words, which is invisible and wrong. Real
        blocks overlap by seconds of speech, so seams this short are rare.
        """
        assert overlap_length("on décide de reporter", "de reporter au 12") == 0
        assert stitch("on décide de reporter", "de reporter au 12") == (
            "on décide de reporter de reporter au 12"
        )


class TestCueing:
    def test_nothing_new_is_never_analysed(self) -> None:
        assert should_analyse(pending="") is False
        assert should_analyse(pending="   ") is False

    def test_a_short_window_waits(self) -> None:
        # Below the floor there is not enough material for a model to say
        # anything a human could not.
        assert should_analyse(pending=_words(MIN_WORDS_TO_ANALYSE - 1)) is False

    def test_a_long_window_is_analysed(self) -> None:
        assert should_analyse(pending=_words(ANALYSIS_WORD_THRESHOLD)) is True

    def test_a_middling_window_waits_unless_something_was_committed(self) -> None:
        middling = ANALYSIS_WORD_THRESHOLD - 10
        assert should_analyse(pending=_words(middling)) is False
        # The same length, with a commitment in it.
        assert should_analyse(pending=_words(middling) + " il faut que Marie relance") is True

    def test_closing_forces_one_last_pass(self) -> None:
        # The last thirty seconds are the most likely place for a commitment:
        # that is when people agree what happens next.
        assert should_analyse(pending="on se recale vendredi", closing=True) is True

    def test_closing_on_nothing_still_does_nothing(self) -> None:
        assert should_analyse(pending="", closing=True) is False

    @pytest.mark.parametrize(
        "text",
        [
            "bon, on décide de reporter",
            "on est d'accord pour lancer",
            "il faut que je relance le DAF",
            "je m'en occupe avant vendredi",
            "prochaine étape : le devis",
            "d'ici lundi on aura la réponse",
        ],
    )
    def test_commitment_phrases_are_recognised(self, text: str) -> None:
        assert contains_cue(text) is True

    def test_cues_survive_dictation_dropping_apostrophes(self) -> None:
        # A speech provider is not reliable about apostrophes, so matching on
        # the raw string would make cue detection depend on its punctuation.
        assert contains_cue("je m en occupe") is True
        assert contains_cue("on est d accord") is True

    def test_ordinary_discussion_is_not_a_cue(self) -> None:
        assert contains_cue("je pense que le marché est difficile en ce moment") is False


class TestSuggestions:
    def _suggestion(self, text: str, kind: SuggestionKind = SuggestionKind.ACTION) -> Suggestion:
        return Suggestion(kind=kind, text=text)

    def test_new_suggestions_are_added(self) -> None:
        merged = merge_suggestions([], [self._suggestion("relancer le DAF")])
        assert [item.text for item in merged] == ["relancer le DAF"]

    def test_the_same_suggestion_is_not_added_twice(self) -> None:
        # Incremental extraction re-proposes what it already proposed, because
        # the sentence is still in its window.
        existing = [self._suggestion("relancer le DAF")]
        merged = merge_suggestions(existing, [self._suggestion("Relancer le DAF")])
        assert len(merged) == 1

    def test_deduplication_ignores_punctuation_and_accents(self) -> None:
        existing = [self._suggestion("préparer l'ordre du jour")]
        merged = merge_suggestions(existing, [self._suggestion("Preparer l ordre du jour")])
        assert len(merged) == 1

    def test_the_first_sighting_keeps_its_timestamp(self) -> None:
        # Watching a suggestion's time jump forward every thirty seconds reads
        # as a bug, and hides when the thing was actually said.
        first = Suggestion(
            kind=SuggestionKind.ACTION,
            text="relancer le DAF",
            created_at=datetime(2026, 6, 10, 9, tzinfo=UTC),
        )
        later = Suggestion(
            kind=SuggestionKind.ACTION,
            text="relancer le DAF",
            created_at=datetime(2026, 6, 10, 10, tzinfo=UTC),
        )
        merged = merge_suggestions([first], [later])
        assert merged[0].created_at == datetime(2026, 6, 10, 9, tzinfo=UTC)

    def test_empty_suggestions_are_dropped(self) -> None:
        assert merge_suggestions([], [self._suggestion("   ")]) == []

    def test_the_list_is_capped_keeping_the_newest(self) -> None:
        # Sixty suggestions is zero suggestions: nobody reads to the end.
        existing = [self._suggestion(f"action {index}") for index in range(MAX_SUGGESTIONS)]
        merged = merge_suggestions(existing, [self._suggestion("la dernière")])

        assert len(merged) == MAX_SUGGESTIONS
        assert merged[-1].text == "la dernière"
        assert merged[0].text == "action 1"

    def test_an_unknown_kind_becomes_a_question_not_an_action(self) -> None:
        # The direction matters: an invented action asks somebody to do
        # something nobody agreed to.
        assert SuggestionKind.parse("todo") is SuggestionKind.QUESTION
        assert SuggestionKind.parse(None) is SuggestionKind.QUESTION
        assert SuggestionKind.parse("action") is SuggestionKind.ACTION

    def test_a_suggestion_round_trips_through_json(self) -> None:
        original = Suggestion(
            kind=SuggestionKind.DECISION,
            text="reporter au 12",
            owner="Marie",
            confidence=0.8,
            at_word=120,
        )
        restored = Suggestion.from_json(original.to_json())

        assert restored is not None
        assert restored.kind is SuggestionKind.DECISION
        assert restored.text == "reporter au 12"
        assert restored.owner == "Marie"
        assert restored.at_word == 120

    def test_a_row_without_text_is_dropped_rather_than_raising(self) -> None:
        # Stored JSON is not a schema. A row that lost its text must not take
        # the whole meeting screen down.
        assert Suggestion.from_json({"kind": "action"}) is None

    def test_a_row_with_a_broken_timestamp_still_loads(self) -> None:
        restored = Suggestion.from_json({"text": "relancer", "created_at": "pas une date"})
        assert restored is not None
        assert restored.text == "relancer"


class TestWindow:
    def test_appending_does_not_mark_anything_analysed(self) -> None:
        window = MeetingWindow().append("bonjour à tous")
        assert window.analysed_words == 0
        assert window.pending == "bonjour à tous"

    def test_marking_analysed_empties_the_pending_tail(self) -> None:
        window = MeetingWindow().append(_words(80)).mark_analysed()
        assert window.pending == ""
        assert window.due() is False

    def test_only_the_new_tail_is_pending_after_an_analysis(self) -> None:
        window = MeetingWindow().append(_words(80)).mark_analysed().append("une phrase de plus")
        assert window.pending == "une phrase de plus"

    def test_a_window_becomes_due_again_as_the_meeting_continues(self) -> None:
        window = MeetingWindow().append(_words(80)).mark_analysed()
        assert window.due() is False

        window = window.append(_words(ANALYSIS_WORD_THRESHOLD, "autre"))
        assert window.due() is True

    def test_the_pending_tail_survives_a_stitch(self) -> None:
        # The reason `analysed_words` is a count and not an offset: stitching
        # rewrites the tail, so an offset would point into the middle of a word.
        window = MeetingWindow(
            transcript="on parle du budget et on décide de reporter",
            analysed_words=5,
        )
        window = window.append("on décide de reporter au 12 janvier")

        assert window.transcript == ("on parle du budget et on décide de reporter au 12 janvier")
        # Five words were analysed; everything after them is still pending, and
        # the stitch did not move that boundary even though it rewrote the tail.
        assert window.pending == "on décide de reporter au 12 janvier"
