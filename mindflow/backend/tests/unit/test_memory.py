"""What the assistant is allowed to remember.

The threshold tests here look pedantic and are not. A wrong memory is not a
wrong answer — it is every future answer being subtly wrong, with no error, no
log line, and no way for the user to guess the cause.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.memory import (
    HALF_LIFE_DAYS,
    MemoryCandidate,
    MemoryExtraction,
    MemoryKind,
    decayed_weight,
    json_schema_for_llm,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _memory(statement: str, confidence: float = 0.9) -> MemoryCandidate:
    return MemoryCandidate(kind=MemoryKind.PROFILE, statement=statement, confidence=confidence)


class TestKinds:
    def test_the_four_kinds_have_labels(self) -> None:
        assert {kind.value for kind in MemoryKind} == {
            "profile",
            "preference",
            "relation",
            "routine",
        }
        assert MemoryKind.RELATION.label == "Relation"


class TestCandidate:
    def test_whitespace_is_flattened(self) -> None:
        assert _memory("Je  dirige\nle pôle forecast").statement == "Je dirige le pôle forecast"

    def test_a_statement_too_short_to_stand_alone_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _memory("ok")

    def test_the_dedupe_key_ignores_case(self) -> None:
        # A long conversation restates the same fact on several turns; storing
        # it once per turn is the common failure.
        assert _memory("Je dirige le pôle forecast").dedupe_key == (
            _memory("je dirige LE pôle forecast").dedupe_key
        )

    def test_the_same_sentence_under_two_kinds_is_two_memories(self) -> None:
        profile = MemoryCandidate(
            kind=MemoryKind.PROFILE, statement="Le point hebdo est le mardi", confidence=0.9
        )
        routine = MemoryCandidate(
            kind=MemoryKind.ROUTINE, statement="Le point hebdo est le mardi", confidence=0.9
        )
        assert profile.dedupe_key != routine.dedupe_key


class TestWorthKeeping:
    def test_nothing_is_the_normal_result(self) -> None:
        assert MemoryExtraction().worth_keeping() == []

    def test_the_bar_is_higher_than_anywhere_else_in_the_product(self) -> None:
        # 0.6 is good enough to show an extracted entity once. It is not good
        # enough to shape every future answer.
        extraction = MemoryExtraction(memories=[_memory("Je dirige le pôle forecast", 0.6)])
        assert extraction.worth_keeping() == []

    def test_a_confident_fact_is_kept(self) -> None:
        extraction = MemoryExtraction(memories=[_memory("Je dirige le pôle forecast", 0.95)])
        assert len(extraction.worth_keeping()) == 1

    def test_repeats_collapse(self) -> None:
        extraction = MemoryExtraction(
            memories=[
                _memory("Je dirige le pôle forecast", 0.95),
                _memory("je dirige le pôle forecast", 0.9),
            ]
        )
        assert len(extraction.worth_keeping()) == 1

    def test_the_list_is_capped(self) -> None:
        with pytest.raises(ValidationError):
            MemoryExtraction(memories=[_memory(f"Fait durable numero {i}") for i in range(20)])


class TestDecay:
    def test_a_memory_confirmed_now_is_fully_trusted(self) -> None:
        assert decayed_weight(NOW, now=NOW) == 1.0

    def test_trust_halves_over_the_half_life(self) -> None:
        confirmed = NOW - timedelta(days=HALF_LIFE_DAYS)
        assert decayed_weight(confirmed, now=NOW) == pytest.approx(0.5)

    def test_decay_is_gradual_not_a_cliff(self) -> None:
        # A hard expiry would make a memory vanish between two turns of one
        # conversation, which reads as amnesia mid-sentence.
        yesterday = decayed_weight(NOW - timedelta(days=1), now=NOW)
        assert 0.99 < yesterday < 1.0

    def test_an_old_memory_keeps_a_little_weight(self) -> None:
        ancient = decayed_weight(NOW - timedelta(days=HALF_LIFE_DAYS * 6), now=NOW)
        assert 0 < ancient < 0.02

    def test_a_clock_skewed_future_timestamp_does_not_exceed_full_trust(self) -> None:
        assert decayed_weight(NOW + timedelta(days=3), now=NOW) == 1.0


class TestSchema:
    def test_the_schema_is_strict(self) -> None:
        schema = json_schema_for_llm()
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
